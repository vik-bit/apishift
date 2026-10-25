"""SARIF 2.1.0 output, so findings show up as GitHub code-scanning annotations on pull requests."""

from __future__ import annotations

from .. import __version__
from ..rules import RULES
from .scanner import Finding


def to_sarif(findings: list[Finding]) -> dict:
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "APIShift",
                "version": __version__,
                "informationUri": "https://github.com/vik-bit/apishift",
                "rules": [{
                    "id": r.id,
                    "name": r.title,
                    "shortDescription": {"text": f"{r.title} is {r.status} in pandas 2.2"},
                    "fullDescription": {"text": r.note},
                    "defaultConfiguration": {"level": "error" if r.status == "removed" else "warning"},
                } for r in RULES],
            }},
            "results": [{
                "ruleId": f.rule_id,
                "level": ("error" if f.rule.status == "removed" else "warning") if f.confidence == "certain" else "note",
                "message": {"text": f"{f.rule.title} ({f.rule.status} in pandas 2.2). {f.rule.note}"
                                    + ("" if f.confidence == "certain" else " The receiver's type could not be inferred.")},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": f.file},
                    "region": {"startLine": f.line, "startColumn": f.col + 1,
                               "endLine": f.end_line, "endColumn": f.end_col + 1},
                }}],
            } for f in findings],
        }],
    }
