import pandas as pd
from columns import column_totals, describe


def test_totals():
    assert column_totals(pd.DataFrame({"a": [1, 2], "b": [3, 4]})) == {"a": 3, "b": 7}


def test_describe():
    assert describe(pd.Series({"x": 1, "y": 2})) == ["x=1", "y=2"]
