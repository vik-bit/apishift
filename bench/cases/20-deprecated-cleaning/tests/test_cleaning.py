import numpy as np
import pandas as pd
from cleaning import clean


def test_clean():
    df = pd.DataFrame({"name": [" a", None, "c "], "n": [np.nan, 2.0, np.nan]})
    out = clean(df)
    assert out["name"].tolist() == ["a", "a", "c"]
    assert out["n"].tolist() == [2.0, 2.0, 2.0]
