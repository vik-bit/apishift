import pandas as pd
from checks import is_sorted_by_time


def test_sorted():
    assert is_sorted_by_time(pd.DataFrame({"ts": [1, 2, 3]}))


def test_unsorted():
    assert not is_sorted_by_time(pd.DataFrame({"ts": [3, 1, 2]}))
