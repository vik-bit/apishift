"""The inspector: run the project's tests and decide whether a change is acceptable.

Plain English: tests are the judge. We copy the project to a temporary folder, apply the change
there (never in your real folder until it's accepted), and run the test suite. A change is
accepted only if nothing that passed before now fails, and no remaining failure points at the file
we just changed.

Collection errors (a test module that can't even import because of an AttributeError) count as
failures, so a broken import can't hide.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..analysis.scanner import SKIP_DIRS

_FAIL_RE = re.compile(r"^(FAILED|ERROR) (\S+?)(?: - |$)", re.M)


@dataclass
class TestRun:
    __test__ = False  # not a pytest test class, despite the name

    returncode: int
    failed: set[str]
    output: str
    seconds: float
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.returncode in (0, 5) and not self.failed  # 5 = no tests collected

    @property
    def no_tests(self) -> bool:
        return self.returncode == 5

    def mentions(self, rel_path: str) -> bool:
        """Does any failure's traceback point inside this file (e.g. `src/report.py:12`)?"""
        if self.passed:
            return False
        needle = re.escape(rel_path.replace("\\", "/"))
        return re.search(rf"(^|[\s/\"']){needle}(:\d+|\", line \d+)", self.output.replace("\\", "/"), re.M) is not None

    def failure_excerpt(self, rel_path: str | None = None, max_lines: int = 80) -> str:
        """The part of the pytest output a model needs to fix the problem."""
        lines = self.output.splitlines()
        start = next((i for i, l in enumerate(lines) if l.startswith(("=", "_")) and ("FAILURES" in l or "ERRORS" in l)), 0)
        body = lines[start:]
        if rel_path:  # put the lines about this file first
            name = Path(rel_path).name
            body = [l for l in body if name in l or "Error" in l or l.startswith(("E ", ">"))] or body
        return "\n".join(body[-max_lines:])


@dataclass
class Workspace:
    """A throwaway copy of the project where candidate changes are tested."""

    repo: Path
    test_cmd: list[str] = field(default_factory=lambda: [sys.executable, "-m", "pytest"])
    strict: bool = False  # treat FutureWarning (deprecations) as errors
    timeout: int = 300
    root: Path = field(init=False)

    def __post_init__(self) -> None:
        self.repo = self.repo.resolve()
        self._tmp = tempfile.mkdtemp(prefix="apishift-")
        self.root = Path(self._tmp) / self.repo.name
        shutil.copytree(self.repo, self.root, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).write_text(text, encoding="utf-8", newline="")

    def run_tests(self) -> TestRun:
        cmd = [*self.test_cmd, "-q", "-rfE", "--tb=short", "-p", "no:cacheprovider", "--color=no"]
        if self.strict:
            cmd += ["-W", "error::FutureWarning"]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        paths = [str(self.root)] + ([str(self.root / "src")] if (self.root / "src").is_dir() else [])
        env["PYTHONPATH"] = os.pathsep.join(paths + [env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        t0 = time.perf_counter()
        try:
            p = subprocess.run(cmd, cwd=self.root, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            return TestRun(-1, {"<timeout>"}, out + f"\nTimed out after {self.timeout}s", time.perf_counter() - t0, True)
        out = p.stdout + p.stderr
        failed = {m[1] for m in _FAIL_RE.findall(out)}
        if p.returncode not in (0, 5) and not failed:
            failed = {"<pytest exited %d>" % p.returncode}
        return TestRun(p.returncode, failed, out, time.perf_counter() - t0)

    def cleanup(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)


def acceptable(before: TestRun, after: TestRun, rel_path: str) -> tuple[bool, str]:
    """Accept iff no new failures and no remaining failure points at the changed file."""
    if after.timed_out:
        return False, "The test suite timed out."
    new = after.failed - before.failed
    if new:
        return False, "These tests passed before your change and fail now: " + ", ".join(sorted(new))
    if after.mentions(rel_path):
        return False, f"Tests still fail inside {rel_path}."
    return True, ""
