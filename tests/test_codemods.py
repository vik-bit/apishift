"""Codemods must change exactly the intended characters and nothing else."""

import ast

import pytest

from apishift.fix.codemods import apply_codemods


@pytest.mark.parametrize("before, after", [
    ("df.iteritems()", "df.items()"),
    ("df['a'].is_monotonic", "df['a'].is_monotonic_increasing"),
    ("df.applymap(str)", "df.map(str)"),
    ("df.backfill()", "df.bfill()"),
    ("df.pad(limit=1)", "df.ffill(limit=1)"),
    ("df.to_csv(b, index=False, line_terminator='\\n')", "df.to_csv(b, index=False, lineterminator='\\n')"),
    ("pd.read_csv(p, squeeze=True)", "pd.read_csv(p).squeeze(\"columns\")"),
    ("pd.read_csv(p, squeeze=True, sep=';')", "pd.read_csv(p, sep=';').squeeze(\"columns\")"),
    ("df.fillna(method='ffill')", "df.ffill()"),
    ("df.fillna(method='bfill', limit=2)", "df.bfill(limit=2)"),
    ("df.mad()", "(df - df.mean()).abs().mean()"),
    ("pd.Int64Index([1, 2], name='i')", "pd.Index([1, 2], dtype=\"int64\", name='i')"),
    ("pd.Float64Index(values)", "pd.Index(values, dtype=\"float64\")"),
])
def test_single_codemods(before, after):
    src = f"import pandas as pd\ndf = pd.DataFrame()\nx = {before}  # keep me\n"
    new, applied = apply_codemods(src)
    assert new == f"import pandas as pd\ndf = pd.DataFrame()\nx = {after}  # keep me\n"
    assert len(applied) == 1


def test_pd_np_adds_numpy_import_once():
    src = "import pandas as pd\na = pd.np.zeros(1)\nb = pd.np.ones(1)\n"
    new, _ = apply_codemods(src)
    assert new == "import pandas as pd\nimport numpy as np\na = np.zeros(1)\nb = np.ones(1)\n"


def test_pd_datetime_reuses_existing_import():
    src = "from datetime import datetime\nimport pandas as pd\nt = pd.datetime(2024, 1, 1)\n"
    new, _ = apply_codemods(src)
    assert new.endswith("t = datetime(2024, 1, 1)\n") and new.count("import") == 2


def test_overlapping_fixes_are_applied_over_several_passes():
    src = "import pandas as pd\ndf = pd.DataFrame()\nout = df.applymap(str).fillna(method='ffill').backfill()\n"
    new, applied = apply_codemods(src)
    assert new.endswith("out = df.map(str).ffill().bfill()\n")
    assert sorted(a.rule_id for a in applied) == ["PD101", "PD102", "PD103"]


def test_non_ascii_positions_are_handled():
    src = "import pandas as pd\ndf = pd.DataFrame()\nlabel = 'café ☕'; s = df.iteritems()\n"
    new, _ = apply_codemods(src)
    assert new.endswith("label = 'café ☕'; s = df.items()\n")


def test_judgement_cases_are_left_for_the_llm():
    src = ("import pandas as pd\ndf = pd.DataFrame()\n"
           "a = df.append({'x': 1}, ignore_index=True)\n"
           "b = df.mad(axis=1)\n"
           "c = isinstance(df.index, pd.Int64Index)\n")
    new, applied = apply_codemods(src)
    assert new == src and applied == []


def test_naive_append_baseline_is_opt_in():
    src = "import pandas as pd\ndf = pd.DataFrame()\nb = pd.DataFrame()\nc = df.append(b, ignore_index=True)\n"
    assert apply_codemods(src)[0] == src
    new, _ = apply_codemods(src, naive_append=True)
    assert new.endswith("c = pd.concat([df, b], ignore_index=True)\n")


def test_output_always_parses():
    src = "import pandas as pd\ndf = pd.DataFrame()\nfor k, v in df.iteritems():\n    print(v.mad(), df.pad())\n"
    ast.parse(apply_codemods(src)[0])
