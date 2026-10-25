import pandas as pd
from rename import standardise


def test_lowercases_columns():
    src = pd.DataFrame({"A": [1], "B": [2]})
    out = standardise(src)
    assert list(out.columns) == ["a", "b"]
    assert list(src.columns) == ["A", "B"]
