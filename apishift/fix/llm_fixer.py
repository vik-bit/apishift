"""The AI engineer: rewrite one file to remove the flagged APIs.

Plain English: the model gets the file with the problem lines marked, the official migration note
for each problem, and strict instructions: change as little as possible, keep behaviour identical,
and don't touch `.append` on lists. It returns the whole updated file. If the tests then fail, it
gets the error output and its previous attempt, and tries again.

Before any test runs, the output must pass cheap gates: it parses, and none of the flagged pandas
APIs remain. A file that only had *possible* findings may come back unchanged; that's the model
saying "this isn't pandas".
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from ..analysis.scanner import Finding, scan_source
from ..rules import BY_ID
from .llm import Provider

MARKER = "# <<< APISHIFT"
_MARKER_RE = re.compile(r"[ \t]*# <<< APISHIFT[^\n]*")
_BLOCK_RE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.S)

SYSTEM = """\
You are a senior Python engineer migrating code from pandas 1.x to pandas 2.2.

Rules:
- Fix only the lines marked with "# <<< APISHIFT". Leave every other line exactly as it is:
  same names, comments, formatting and order.
- Keep the behaviour identical to what the code did on pandas 1.x (same values, index, column order and dtypes).
- A marker that says "possible" means the scanner could not tell whether the object is a pandas object. Read the
  surrounding code. If it is a list or another non-pandas object, leave that line unchanged.
- Add an import only if the fix needs it.
- Do not add explanations or comments about the migration.
- Return the complete updated file in a single ```python code block and nothing else."""


@dataclass
class Attempt:
    source: str | None  # None when the reply couldn't be used
    problem: str = ""  # why the gates rejected it, fed back on the next attempt
    raw: str = ""


def mark_lines(source: str, findings: list[Finding]) -> str:
    lines = source.splitlines()
    notes: dict[int, list[str]] = {}
    for f in findings:
        label = f"{f.rule_id} {f.rule.title}" + (" (possible: decide whether this is pandas)" if f.confidence == "possible" else "")
        notes.setdefault(f.line, []).append(label)
    for line_no, labels in notes.items():
        lines[line_no - 1] = f"{lines[line_no - 1]}  {MARKER} {'; '.join(labels)}"
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def build_prompt(path: str, source: str, findings: list[Finding], feedback: str = "", previous: str = "") -> str:
    rules = sorted({f.rule_id for f in findings})
    notes = "\n".join(f"- {r} ({BY_ID[r].title}): {BY_ID[r].note}" for r in rules)
    sites = "\n".join(f"- line {f.line}: {f.rule_id} [{f.confidence}, receiver: {f.receiver_kind}] `{f.snippet}`" for f in findings)
    parts = [
        f"File: `{path}`",
        f"Migration notes:\n{notes}",
        f"Flagged lines:\n{sites}",
        f"```python\n{mark_lines(source, findings)}```",
    ]
    if feedback:
        parts += [
            "Your previous attempt was rejected. Fix the problem below and return the complete file again.",
            f"Problem:\n```\n{feedback}\n```",
        ]
        if previous:
            parts.append(f"Your previous attempt:\n```python\n{previous}```")
    return "\n\n".join(parts)


def extract_code(reply: str) -> str | None:
    blocks = _BLOCK_RE.findall(reply)
    if not blocks:
        return None
    code = max(blocks, key=len)  # the file, not a short snippet the model also showed
    code = _MARKER_RE.sub("", code)
    return code if code.endswith("\n") else code + "\n"


def check_output(code: str, original_findings: list[Finding], path: str) -> str:
    """Return "" if the rewrite passes the gates, else a description of what's wrong."""
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return f"The file does not parse: line {exc.lineno}: {exc.msg}"
    targeted = {(f.rule_id) for f in original_findings if f.confidence == "certain"}
    left = [f for f in scan_source(code, path) if f.confidence == "certain" and f.rule_id in targeted]
    if left:
        return "These pandas APIs are still used:\n" + "\n".join(f"line {f.line}: {f.rule_id} {f.rule.title}: {f.snippet}" for f in left)
    return ""


def attempt_fix(provider: Provider, path: str, source: str, findings: list[Finding],
                feedback: str = "", previous: str = "", gates: bool = True) -> Attempt:
    reply = provider.complete(SYSTEM, build_prompt(path, source, findings, feedback, previous))
    code = extract_code(reply)
    if code is None:
        return Attempt(None, "Your reply did not contain a ```python code block with the complete file.", reply)
    if gates:
        problem = check_output(code, findings, path)
        if problem:
            return Attempt(None, problem, reply) if "does not parse" in problem else Attempt(code, problem, reply)
    return Attempt(code, "", reply)
