import pandas as pd
from readings import merge_readings


def test_merges_in_order():
    out = merge_readings(pd.Series([1.5, 2.0]), pd.Series([3.0]))
    assert isinstance(out, pd.Series)
    assert out.tolist() == [1.5, 2.0, 3.0]
    assert list(out.index) == [0, 1, 2]
