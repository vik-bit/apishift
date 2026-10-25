"""The full migrate() loop with a scripted LLM: retries, gates, reverts and negative cases."""

import textwrap
from pathlib import Path

from apishift.fix.llm import ScriptedProvider
from apishift.fix.orchestrator import Options, migrate
from apishift.fix.verifier import TestRun, acceptable

SRC = textwrap.dedent('''\
    import pandas as pd


    def add_row(df: pd.DataFrame, row: dict) -> pd.DataFrame:
        return df.append(row, ignore_index=True)


    def names(df: pd.DataFrame) -> list:
        return [k for k, _ in df.iteritems()]
''')
TEST = textwrap.dedent('''\
    import pandas as pd
    from shop import add_row, names


    def test_add_row():
        out = add_row(pd.DataFrame({"a": [1]}), {"a": 2})
        assert out["a"].tolist() == [1, 2]


    def test_names():
        assert names(pd.DataFrame({"a": [1], "b": [2]})) == ["a", "b"]
''')
WRONG = "```python\n" + SRC.replace("df.append(row, ignore_index=True)", "pd.concat([df, row], ignore_index=True)").replace("iteritems", "items") + "```"
RIGHT = "```python\n" + SRC.replace("df.append(row, ignore_index=True)", "pd.concat([df, pd.DataFrame([row])], ignore_index=True)").replace("iteritems", "items") + "```"
STILL_OLD = "```python\n" + SRC.replace("iteritems", "items") + "```"


def make_repo(tmp_path: Path, src: str = SRC) -> Path:
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "shop.py").write_text(src)
    (repo / "tests" / "test_shop.py").write_text(TEST)
    return repo


def test_codemod_then_llm_with_one_retry(tmp_path):
    repo = make_repo(tmp_path)
    llm = ScriptedProvider([WRONG, RIGHT])
    res = migrate(repo, llm, Options(), log=lambda m: None)
    [f] = res.files
    assert f.status == "fixed" and f.llm_attempts == 2
    assert [c.rule_id for c in f.codemods] == ["PD002"]  # iteritems needed no LLM
    assert "pd.DataFrame([row])" in f.final and ".items()" in f.final
    assert res.before.failed and res.after.passed
    # the retry prompt carried the real pytest failure back to the model
    retry_prompt = llm.prompts[1][1]
    assert "previous attempt was rejected" in retry_prompt and "test_add_row" in retry_prompt
    # the user's files are untouched until they ask to write
    assert (repo / "src" / "shop.py").read_text() == SRC


def test_gate_rejects_output_that_still_uses_the_api(tmp_path):
    llm = ScriptedProvider([STILL_OLD, RIGHT])
    res = migrate(make_repo(tmp_path), llm, Options(), log=lambda m: None)
    assert res.files[0].status == "fixed" and llm.usage.calls == 2
    assert "still used" in llm.prompts[1][1]


def test_gives_up_and_reverts_after_max_attempts(tmp_path):
    llm = ScriptedProvider([WRONG, WRONG, WRONG])
    res = migrate(make_repo(tmp_path), llm, Options(max_attempts=3), log=lambda m: None)
    [f] = res.files
    assert f.status == "partially-fixed" and "after 3 tries" in f.reason
    assert ".items()" in f.final and "df.append(row" in f.final  # codemod kept, LLM change reverted


def test_possible_only_file_left_unchanged_when_model_says_not_pandas(tmp_path):
    src = "import pandas as pd\n\n\ndef collect(items, x):\n    items.append(x)\n    return items\n"
    repo = tmp_path / "p"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "c.py").write_text(src)
    llm = ScriptedProvider(["```python\n" + src + "```"])
    res = migrate(repo, llm, Options(), log=lambda m: None)
    assert res.files[0].status == "not-pandas" and not res.files[0].changed


def test_codemods_only_without_a_provider(tmp_path):
    res = migrate(make_repo(tmp_path), None, Options(use_llm=False), log=lambda m: None)
    [f] = res.files
    assert f.status == "partially-fixed" and ".items()" in f.final and "needs the LLM" in f.reason


def test_acceptance_rule():
    before = TestRun(1, {"tests/test_a.py::t1"}, "", 0.1)
    fixed = TestRun(0, set(), "1 passed", 0.1)
    broke = TestRun(1, {"tests/test_a.py::t2"}, "", 0.1)
    still = TestRun(1, {"tests/test_a.py::t1"}, "src/shop.py:5: in add_row\nE AttributeError", 0.1)
    assert acceptable(before, fixed, "src/shop.py")[0]
    assert not acceptable(before, broke, "src/shop.py")[0]
    assert not acceptable(before, still, "src/shop.py")[0]


def test_failure_in_test_file_does_not_count_as_pointing_at_source():
    run = TestRun(1, {"tests/test_shop.py::t"}, "tests/test_shop.py:9: in test_x\nE assert 1 == 2", 0.1)
    assert not run.mentions("src/shop.py") and not run.mentions("shop.py")
