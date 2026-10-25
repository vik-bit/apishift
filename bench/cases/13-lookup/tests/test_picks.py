import pandas as pd
from picks import picked_values


def test_picks_each_rows_column():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [10, 20, 30], "pick": ["a", "b", "a"]}, index=["x", "y", "z"])
    assert picked_values(df) == [1, 20, 3]
