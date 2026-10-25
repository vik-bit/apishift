"""Type inference decides what gets flagged. These pin down the cases that matter."""

from apishift.analysis import scan_source


def rules(src: str, confidence: str | None = None) -> list[tuple[str, int]]:
    return [(f.rule_id, f.line) for f in scan_source(src) if confidence is None or f.confidence == confidence]


def test_list_append_is_never_flagged():
    src = "import pandas as pd\nrows = []\nrows.append(1)\nparts = 'a,b'.split(',')\nparts.append('c')\n"
    assert rules(src) == []


def test_dataframe_append_is_certain():
    src = "import pandas as pd\ndf = pd.read_csv('x')\ndf = df.append(df)\n"
    assert rules(src, "certain") == [("PD001", 3)]


def test_unannotated_parameter_is_possible():
    src = "import pandas as pd\ndef f(frame):\n    frame.append(1)\n"
    assert rules(src, "possible") == [("PD001", 3)]


def test_annotations_decide_both_ways():
    src = ("import pandas as pd\n"
           "def f(a: pd.DataFrame, b: list):\n    a.append(a)\n    b.append(1)\n")
    assert rules(src) == [("PD001", 3)]


def test_self_attributes_are_tracked_per_class():
    src = ("import pandas as pd\nclass L:\n    def __init__(self):\n        self.df = pd.DataFrame()\n"
           "        self.log = []\n    def add(self, r):\n        self.df = self.df.append(r)\n        self.log.append(r)\n")
    assert rules(src) == [("PD001", 7)]


def test_self_attribute_from_annotated_parameter():
    # Found on the demo repo: self.sales = sales must carry the parameter's annotation into other methods.
    src = ("import pandas as pd\nclass R:\n    def __init__(self, sales: pd.DataFrame):\n        self.sales = sales\n"
           "    def build(self):\n        for region, group in self.sales.groupby('region'):\n"
           "            amounts = group['amount']\n            amounts.mad()\n")
    [f] = scan_source(src)
    assert (f.rule_id, f.line, f.receiver_kind) == ("PD003", 8, "Pandas")


def test_return_types_flow_between_functions():
    src = "import pandas as pd\ndef load():\n    return pd.read_csv('x')\ndef main():\n    d = load()\n    d.append(d)\n"
    assert rules(src, "certain") == [("PD001", 6)]


def test_loop_targets_and_groupby_groups():
    src = ("import pandas as pd\ndf = pd.DataFrame()\n"
           "for name, col in df.items():\n    col.mad()\n"
           "for key, g in df.groupby('k'):\n    g['v'].mad()\n")
    found = scan_source(src)
    assert [(f.rule_id, f.line, f.receiver_kind) for f in found] == [("PD003", 4, "Series"), ("PD003", 6, "Pandas")]


def test_groupby_mad_is_its_own_rule():
    assert rules("import pandas as pd\ndf = pd.DataFrame()\ndf.groupby('k')['v'].mad()\n") == [("PD004", 3)]


def test_local_class_instances_are_not_pandas():
    src = ("import pandas as pd\nclass Buf:\n    def append(self, x):\n        pass\n"
           "b = Buf()\nb.append(1)\n")
    assert rules(src) == []


def test_files_without_pandas_are_left_alone():
    assert rules("class S:\n    def iteritems(self):\n        return iter(())\nfor k in S().iteritems():\n    pass\n") == []


def test_module_attributes_and_aliases():
    src = "import pandas as P\nfrom pandas import Int64Index as I64\nx = P.np.zeros(1)\nidx = I64([1])\n"
    assert sorted(rules(src)) == [("PD010", 2), ("PD010", 4), ("PD012", 3)]


def test_keyword_rules_match_only_the_bad_value():
    src = ("import pandas as pd\ndf = pd.DataFrame()\n"
           "pd.read_csv('a', squeeze=True)\npd.read_csv('a', squeeze=False)\n"
           "df.groupby('k', axis=1).sum()\ndf.groupby('k', axis=0).sum()\n")
    assert rules(src) == [("PD008", 3), ("PD105", 5)]


def test_property_vs_call():
    src = "import pandas as pd\ns = pd.Series([1])\ns.is_monotonic\n"
    assert rules(src) == [("PD006", 3)]


def test_parse_errors_are_reported_not_hidden(tmp_path):
    from apishift.analysis import scan_path

    (tmp_path / "bad.py").write_text("def (:\n")
    (tmp_path / "ok.py").write_text("import pandas as pd\npd.np\n")
    res = scan_path(tmp_path)
    assert [f.rule_id for f in res.findings] == ["PD012"]
    assert len(res.errors) == 1 and "bad.py" in res.errors[0]
