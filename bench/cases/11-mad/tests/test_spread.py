import pandas as pd
from spread import frame_spread, spread


def test_series_mad():
    assert spread(pd.Series([1.0, 2.0, 3.0, 4.0])) == 1.0


def test_frame_mad_per_column():
    out = frame_spread(pd.DataFrame({"a": [1.0, 3.0], "b": [2.0, 2.0]}))
    assert out.to_dict() == {"a": 1.0, "b": 0.0}
