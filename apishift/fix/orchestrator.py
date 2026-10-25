"""The whole flow in one place. Start reading the code here.

    scan ──► codemods (safe, free) ──► tests ──► LLM per remaining file ──► tests ──► accept / retry / revert
                                                       ▲                       │
                                                       └── pytest failure ◄────┘

Plain English: find the old APIs, fix the easy ones mechanically, check nothing broke, then let
the AI handle the rest one file at a time. Every AI change must survive the test suite; if it
doesn't, the AI sees the error and tries again (up to 3 times). Anything still failing is put back
the way it was and listed for a human.
"""

from __future__ import annotations

import difflib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..analysis.scanner import Finding, python_files, scan_source
from .codemods import Applied, apply_codemods
from .llm import LLMError, Provider
from .llm_fixer import attempt_fix
from .verifier import TestRun, Workspace, acceptable

Log = Callable[[str], None]


@dataclass
class FileResult:
    path: str
    original: str
    final: str
    findings: list[Finding]
    codemods: list[Applied] = field(default_factory=list)
    llm_attempts: int = 0
    llm_accepted: bool = False
    status: str = "unchanged"  # fixed | partially-fixed | needs-human | unchanged | not-pandas
    reason: str = ""

    @property
    def changed(self) -> bool:
        return self.final != self.original

    def diff(self) -> str:
        return "".join(difflib.unified_diff(self.original.splitlines(True), self.final.splitlines(True),
                                            fromfile=f"a/{self.path}", tofile=f"b/{self.path}"))


@dataclass
class Options:
    use_codemods: bool = True
    naive_append: bool = False  # baseline only: rewrite every append as pd.concat([x, y])
    use_llm: bool = True
    max_attempts: int = 3
    verify: bool = True  # run tests to accept/reject LLM attempts
    strict: bool = False  # deprecations (FutureWarning) count as failures
    include_possible: bool = True  # send "possible" findings to the LLM


@dataclass
class MigrationResult:
    repo: str
    files: list[FileResult]
    before: TestRun | None
    after: TestRun | None
    provider: str
    model: str
    llm_calls: int = 0
    tokens: int = 0
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def changed_files(self) -> list[FileResult]:
        return [f for f in self.files if f.changed]

    @property
    def needs_human(self) -> list[FileResult]:
        return [f for f in self.files if f.status in ("needs-human", "partially-fixed")]


def migrate(repo: Path, provider: Provider | None, options: Options | None = None, log: Log = print,
            timeout: int = 300) -> MigrationResult:
    opts = options or Options()
    t0 = time.perf_counter()
    repo = repo.resolve()
    ws = Workspace(repo, strict=opts.strict, timeout=timeout)
    try:
        results: list[FileResult] = []
        for p in python_files(ws.root):
            rel = p.relative_to(ws.root).as_posix()
            src = p.read_text(encoding="utf-8")
            try:
                found = scan_source(src, rel)
            except SyntaxError:
                continue
            if found:
                results.append(FileResult(rel, src, src, found))
        log(f"Scanned: {sum(len(r.findings) for r in results)} findings in {len(results)} files")
        if not results:
            return MigrationResult(str(repo), [], None, None, getattr(provider, "name", "none"),
                                   getattr(provider, "model", "none"), seconds=time.perf_counter() - t0)

        before = ws.run_tests() if opts.verify else None
        if before is not None:
            log(f"Tests before: {len(before.failed)} failing" + (" (no tests found)" if before.no_tests else ""))

        # 1. codemods: safe, deterministic, free
        if opts.use_codemods:
            for r in results:
                new, applied = apply_codemods(r.final, r.path, naive_append=opts.naive_append)
                if applied:
                    r.final, r.codemods = new, applied
                    ws.write(r.path, new)
                    log(f"  codemod {r.path}: {len(applied)} fixes")
        state = ws.run_tests() if opts.verify else None
        if opts.verify and before is not None and state is not None:
            broken = state.failed - before.failed
            for r in results:  # a codemod that broke a test is undone; the LLM gets the file instead
                if r.codemods and broken and state.mentions(r.path):
                    log(f"  codemod in {r.path} broke tests; reverting it")
                    r.final, r.codemods = r.original, []
                    ws.write(r.path, r.original)
            if broken:
                state = ws.run_tests()

        # 2. LLM for whatever the codemods couldn't fix
        for r in results:
            remaining = [f for f in scan_source(r.final, r.path)
                         if f.confidence == "certain" or (opts.include_possible and f.confidence == "possible")]
            if not remaining:
                r.status = "fixed" if r.changed else "unchanged"
                continue
            if not opts.use_llm or provider is None:
                certain = [f for f in remaining if f.confidence == "certain"]
                r.status = ("partially-fixed" if r.changed else "needs-human") if certain else ("fixed" if r.changed else "unchanged")
                r.reason = "needs the LLM; no provider configured" if certain else ""
                continue
            _llm_fix(r, remaining, provider, ws, opts, state, log)
            if opts.verify and r.llm_accepted:
                state = ws.run_tests()

        after = ws.run_tests() if opts.verify else None
        if after is not None:
            log(f"Tests after: {len(after.failed)} failing")
        usage = getattr(provider, "usage", None)
        return MigrationResult(str(repo), results, before, after, getattr(provider, "name", "none"),
                               getattr(provider, "model", "none"), llm_calls=getattr(usage, "calls", 0),
                               tokens=getattr(usage, "total", 0), seconds=time.perf_counter() - t0)
    finally:
        ws.cleanup()


def _llm_fix(r: FileResult, remaining: list[Finding], provider: Provider, ws: Workspace, opts: Options,
             state: TestRun | None, log: Log) -> None:
    start = r.final  # codemod output (or original)
    feedback, previous = "", ""
    for attempt in range(1, opts.max_attempts + 1):
        r.llm_attempts = attempt
        try:
            a = attempt_fix(provider, r.path, start, remaining, feedback, previous, gates=opts.verify)
        except LLMError as exc:
            r.status, r.reason = ("partially-fixed" if r.changed else "needs-human"), str(exc)
            log(f"  LLM {r.path}: {exc}")
            return
        if a.source is None or a.problem:
            feedback, previous = a.problem, a.source or ""
            log(f"  LLM {r.path} attempt {attempt}: rejected before tests ({a.problem.splitlines()[0][:80]})")
            continue
        if a.source == start:
            only_possible = all(f.confidence == "possible" for f in remaining)
            r.status = ("fixed" if r.changed else "not-pandas") if only_possible else "needs-human"
            r.reason = "the model judged the flagged object is not pandas" if only_possible else "the model returned the file unchanged"
            log(f"  LLM {r.path}: left unchanged ({r.reason})")
            r.llm_accepted = only_possible
            return
        if not opts.verify:  # one-shot baseline: take the first parsable answer
            r.final, r.llm_accepted, r.status = a.source, True, "fixed"
            ws.write(r.path, a.source)
            return
        ws.write(r.path, a.source)
        run = ws.run_tests()
        ok, why = acceptable(state, run, r.path) if state is not None else (True, "")
        if ok:
            r.final, r.llm_accepted, r.status = a.source, True, "fixed"
            log(f"  LLM {r.path} attempt {attempt}: accepted ({len(run.failed)} failing tests remain overall)")
            return
        log(f"  LLM {r.path} attempt {attempt}: tests rejected it ({why[:80]})")
        feedback = why + "\n\n" + run.failure_excerpt(r.path)
        previous = a.source
        ws.write(r.path, start)  # back to the last good version before the next try
    r.final = start
    r.status = "partially-fixed" if r.changed else "needs-human"
    r.reason = f"no attempt passed the tests after {opts.max_attempts} tries"
