import pandas as pd
from batches import add_batch


def test_adds_batch():
    a = pd.DataFrame({"id": [1, 2], "qty": [5, 6]})
    b = pd.DataFrame({"id": [3], "qty": [7]})
    out = add_batch(a, b)
    assert out["id"].tolist() == [1, 2, 3]
    assert list(out.index) == [0, 1, 2]
