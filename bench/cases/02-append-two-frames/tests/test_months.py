import pandas as pd
from months import combine


def test_keeps_rows_and_index():
    jan = pd.DataFrame({"sales": [1, 2]}, index=["a", "b"])
    feb = pd.DataFrame({"sales": [3]}, index=["c"])
    out = combine(jan, feb)
    assert out["sales"].tolist() == [1, 2, 3]
    assert list(out.index) == ["a", "b", "c"]
