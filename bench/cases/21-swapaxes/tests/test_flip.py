import pandas as pd
from flip import flip


def test_flip():
    out = flip(pd.DataFrame({"a": [1, 2]}, index=["x", "y"]))
    assert list(out.index) == ["a"] and list(out.columns) == ["x", "y"]
