import pandas as pd
from extend import extend


def test_extend():
    out = extend(pd.DataFrame({"v": [1]}, index=[5]), pd.DataFrame({"v": [2]}, index=[9]))
    assert out["v"].tolist() == [1, 2] and list(out.index) == [0, 1]
