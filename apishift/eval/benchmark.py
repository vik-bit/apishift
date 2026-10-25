"""The benchmark: small projects that break on pandas 2.2, with tests and a reference fix.

Plain English: each case is a tiny project with old pandas code, tests describing what the code
must do, and a hand-written correct fix. `check()` proves each case is fair: the tests fail on the
old code and pass on the reference fix. `run()` scores a migration method: did the tests pass
afterwards, and were the "leave this alone" cases left alone?

Everything runs in strict mode (deprecation warnings are errors), so a fix must also be ready for
pandas 3.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from ..analysis.scanner import scan_source
from ..config import PROJECT_ROOT
from ..fix.llm import Provider
from ..fix.orchestrator import Options, migrate
from ..fix.verifier import Workspace

CASES_DIR = PROJECT_ROOT / "bench" / "cases"


@dataclass
class Case:
    dir: Path
    id: str
    module: str
    rules: list[str]
    description: str
    kind: str  # "positive" or "negative"
    strict: bool  # True when only deprecations are involved (passes on 2.2 unless warnings are errors)
    difficulty: str

    @property
    def source_rel(self) -> str:
        return f"src/{self.module}.py"


def load_cases(root: Path = CASES_DIR, only: str | None = None) -> list[Case]:
    cases = []
    for d in sorted(p for p in root.iterdir() if (p / "case.json").is_file()):
        meta = json.loads((d / "case.json").read_text(encoding="utf-8"))
        if only and only not in meta["id"]:
            continue
        cases.append(Case(dir=d, **meta))
    return cases


def make_project(case: Case, use_solution: bool = False) -> Path:
    """A clean copy of the case (src/ + tests/ only) in a temporary folder."""
    root = Path(tempfile.mkdtemp(prefix=f"apishift-{case.id}-")) / case.id
    shutil.copytree(case.dir / "src", root / "src")
    shutil.copytree(case.dir / "tests", root / "tests")
    if use_solution:
        for f in (case.dir / "solution").glob("*.py"):
            shutil.copy(f, root / "src" / f.name)
    return root


def _tests_pass(project: Path) -> tuple[bool, str]:
    ws = Workspace(project, strict=True, timeout=120)
    try:
        r = ws.run_tests()
        return r.passed, r.output
    finally:
        ws.cleanup()


@dataclass
class CheckResult:
    case: str
    ok: bool
    problems: list[str] = field(default_factory=list)


def check(cases: list[Case]) -> list[CheckResult]:
    """Prove every case is fair, without any LLM."""
    out = []
    for c in cases:
        problems = []
        orig = make_project(c)
        try:
            passed, _ = _tests_pass(orig)
            if c.kind == "positive" and passed:
                problems.append("tests pass on the original code, so the case tests nothing")
            if c.kind == "negative" and not passed:
                problems.append("negative case: tests should pass on the original code")
            src = (orig / c.source_rel).read_text(encoding="utf-8")
            found = {f.rule_id for f in scan_source(src, c.source_rel)}
            certain = [f for f in scan_source(src, c.source_rel) if f.confidence == "certain"]
            missing = set(c.rules) - found
            if missing:
                problems.append(f"scanner missed {sorted(missing)}")
            if c.kind == "negative" and certain:
                problems.append(f"scanner wrongly flags {[f.rule_id + ':' + str(f.line) for f in certain]}")
        finally:
            shutil.rmtree(orig.parent, ignore_errors=True)
        if c.kind == "positive":
            sol = make_project(c, use_solution=True)
            try:
                passed, output = _tests_pass(sol)
                if not passed:
                    problems.append("reference solution fails its own tests:\n" + output[-800:])
            finally:
                shutil.rmtree(sol.parent, ignore_errors=True)
        out.append(CheckResult(c.id, not problems, problems))
    return out


MODES: dict[str, Options] = {
    # What a find-and-replace codemod tool achieves: deterministic rules + naive append rewrite.
    "codemod": Options(use_codemods=True, naive_append=True, use_llm=False, verify=False, strict=True),
    # The LLM alone, one attempt per file, no test feedback.
    "llm-one-shot": Options(use_codemods=False, use_llm=True, max_attempts=1, verify=False, strict=True),
    # APIShift: codemods first, then the LLM with test-verified retries.
    "apishift": Options(use_codemods=True, use_llm=True, max_attempts=3, verify=True, strict=True),
}


@dataclass
class CaseScore:
    case: str
    kind: str
    difficulty: str
    mode: str
    success: bool
    tests_pass: bool
    changed: bool
    remaining: list[str]
    llm_calls: int
    tokens: int
    llm_attempts: int
    seconds: float
    error: str = ""


def run_case(case: Case, mode: str, provider: Provider | None, log: Callable[[str], None] = lambda m: None) -> CaseScore:
    opts = MODES[mode]
    project = make_project(case)
    t0 = time.perf_counter()
    calls0 = provider.usage.calls if provider else 0
    tokens0 = provider.usage.total if provider else 0
    try:
        try:
            res = migrate(project, provider if opts.use_llm else None, opts, log=log, timeout=120)
        except Exception as exc:  # a crash is a failure of the method, not of the benchmark
            return CaseScore(case.id, case.kind, case.difficulty, mode, False, False, False, [], 0, 0, 0,
                             time.perf_counter() - t0, error=f"{type(exc).__name__}: {exc}")
        for f in res.files:  # write the method's final answer, then judge it independently
            (project / f.path).write_text(f.final, encoding="utf-8", newline="")
        passed, _ = _tests_pass(project)
        src = (project / case.source_rel).read_text(encoding="utf-8")
        try:
            remaining = [f"{f.rule_id}:{f.line}" for f in scan_source(src, case.source_rel) if f.confidence == "certain"]
        except SyntaxError:
            remaining = ["<does not parse>"]
        changed = any(f.changed for f in res.files)
        success = passed and not remaining and (not changed if case.kind == "negative" else True)
        attempts = max((f.llm_attempts for f in res.files), default=0)
        return CaseScore(case.id, case.kind, case.difficulty, mode, success, passed, changed, remaining,
                         (provider.usage.calls - calls0) if provider else 0,
                         (provider.usage.total - tokens0) if provider else 0,
                         attempts, round(time.perf_counter() - t0, 1))
    finally:
        shutil.rmtree(project.parent, ignore_errors=True)


def summarise(scores: list[CaseScore]) -> dict:
    pos = [s for s in scores if s.kind == "positive"]
    neg = [s for s in scores if s.kind == "negative"]
    hard = [s for s in pos if s.difficulty == "hard"]
    fixed_first = [s for s in pos if s.success and s.llm_attempts <= 1]
    return {
        "cases": len(scores),
        "fixed": sum(s.success for s in pos), "positive": len(pos),
        "hard_fixed": sum(s.success for s in hard), "hard": len(hard),
        "negatives_untouched": sum(s.success for s in neg), "negative": len(neg),
        "needed_retry": sum(1 for s in pos if s.success and s.llm_attempts > 1),
        "fixed_first_try": len(fixed_first),
        "llm_calls": sum(s.llm_calls for s in scores), "tokens": sum(s.tokens for s in scores),
        "seconds": round(sum(s.seconds for s in scores)),
        "errors": [f"{s.case}: {s.error}" for s in scores if s.error],
    }


def to_json(scores: list[CaseScore]) -> list[dict]:
    return [asdict(s) for s in scores]
