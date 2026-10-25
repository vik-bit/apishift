"""The pull-request description: what changed, how, and what the tests say."""

from __future__ import annotations

from .fix.orchestrator import MigrationResult
from .rules import BY_ID

_STATUS = {"fixed": "✅ fixed", "partially-fixed": "⚠️ partly fixed", "needs-human": "❌ needs a human",
           "not-pandas": "➖ not pandas (left as is)", "unchanged": "➖ no change"}


def pr_body(res: MigrationResult) -> str:
    lines = ["## Migrate removed pandas APIs to pandas 2.x", ""]
    changed = res.changed_files
    n_codemods = sum(len(f.codemods) for f in res.files)
    n_llm = sum(1 for f in res.files if f.llm_accepted and f.changed)
    lines.append(f"APIShift changed **{len(changed)} file(s)**: {n_codemods} deterministic rewrite(s)"
                 f" and {n_llm} file(s) fixed by an LLM ({res.model}) and verified by the test suite.")
    lines.append("")
    if res.before is not None and res.after is not None:
        if res.before.no_tests:
            lines += ["> **No tests were found**, so these changes are **not verified**. Review every line.", ""]
        else:
            lines += [f"**Tests:** {len(res.before.failed)} failing before → **{len(res.after.failed)} failing after**.", ""]

    lines += ["| File | Line | Rule | Fix | Status |", "|---|---|---|---|---|"]
    for f in res.files:
        status = _STATUS.get(f.status, f.status)
        for c in f.codemods:
            lines.append(f"| `{f.path}` | {c.line} | {c.rule_id} {BY_ID[c.rule_id].title} | codemod: {c.description} | {status} |")
        done = {(c.rule_id, c.line) for c in f.codemods}
        for fd in f.findings:
            if (fd.rule_id, fd.line) in done:
                continue
            how = (f"LLM, {f.llm_attempts} attempt(s)" if f.llm_attempts else "-")
            note = " (possible)" if fd.confidence == "possible" else ""
            lines.append(f"| `{f.path}` | {fd.line} | {fd.rule_id} {fd.rule.title}{note} | {how} | {status} |")
    if res.needs_human:
        lines += ["", "### Needs a human", ""]
        lines += [f"- `{f.path}`: {f.reason}" for f in res.needs_human]
    lines += ["", "<details><summary>How these changes were checked</summary>", "",
              "- Unambiguous renames were done with exact AST-position edits; nothing else in those lines changed.",
              "- LLM changes were accepted only if no previously passing test failed and no remaining failure pointed "
              "at the changed file. Failed attempts were retried with the test output (max 3), then reverted.",
              "- Each rule links to the pandas 2.0 release notes: "
              "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html#removal-of-prior-version-deprecations-changes",
              "", "</details>", "", "_Opened by [APIShift](https://github.com/vik-bit/apishift)._"]
    return "\n".join(lines) + "\n"
