import pandas as pd
import pytest
from unique import strict_union


def test_union():
    out = strict_union(pd.DataFrame({"v": [1]}, index=["a"]), pd.DataFrame({"v": [2]}, index=["b"]))
    assert list(out.index) == ["a", "b"]


def test_duplicate_labels_rejected():
    with pytest.raises(ValueError):
        strict_union(pd.DataFrame({"v": [1]}, index=["a"]), pd.DataFrame({"v": [2]}, index=["a"]))
