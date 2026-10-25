"""Providers (against a fake HTTP API), SARIF output, the PR body, and the benchmark's fairness."""

import json

import groq
import httpx

from apishift.analysis import scan_source
from apishift.analysis.sarif import to_sarif
from apishift.eval.benchmark import check, load_cases
from apishift.fix.llm import GroqProvider
from apishift.fix.llm_fixer import extract_code, mark_lines
from apishift.rules import RULES, rules_markdown


def test_groq_provider_request_and_usage():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "openai/gpt-oss-120b",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "```python\nx = 1\n```"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

    client = groq.Groq(api_key="k", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    p = GroqProvider("openai/gpt-oss-120b", "medium", client=client)
    assert p.complete("sys", "user") == "```python\nx = 1\n```"
    assert seen[0]["reasoning_effort"] == "medium" and seen[0]["messages"][0]["role"] == "system"
    assert p.usage.calls == 1 and p.usage.total == 15


def test_markers_are_added_for_the_llm_and_stripped_from_its_answer():
    src = "import pandas as pd\ndf = pd.DataFrame()\ny = df.append(df)\n"
    marked = mark_lines(src, scan_source(src))
    assert "y = df.append(df)  # <<< APISHIFT PD001" in marked
    assert extract_code("Sure:\n```python\n" + marked + "```") == src


def test_sarif_is_well_formed():
    s = to_sarif(scan_source("import pandas as pd\nx = pd.np.zeros(1)\n", "a.py"))
    run = s["runs"][0]
    assert s["version"] == "2.1.0" and len(run["tool"]["driver"]["rules"]) == len(RULES)
    assert run["results"][0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 2


def test_rules_doc_lists_every_rule():
    md = rules_markdown()
    assert all(f"| {r.id} |" in md for r in RULES)


def test_every_benchmark_case_is_fair():
    """Tests fail on the old code, pass on the reference fix; the scanner sees the right rules."""
    results = check(load_cases())
    assert len(results) >= 28
    assert [r.case for r in results if not r.ok] == []
