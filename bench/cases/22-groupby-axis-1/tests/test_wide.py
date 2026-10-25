import pandas as pd
from wide import sum_column_groups


def test_sums_column_groups():
    df = pd.DataFrame({"q1": [1, 2], "q2": [3, 4], "h2": [10, 20]})
    out = sum_column_groups(df, {"q1": "H1", "q2": "H1", "h2": "H2"})
    assert list(out.columns) == ["H1", "H2"]
    assert out["H1"].tolist() == [4, 6] and out["H2"].tolist() == [10, 20]
