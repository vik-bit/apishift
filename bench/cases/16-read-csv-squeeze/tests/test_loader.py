import pandas as pd
from loader import load_ids


def test_single_column_becomes_series(tmp_path):
    p = tmp_path / "ids.csv"
    p.write_text("id\n7\n8\n")
    out = load_ids(p)
    assert isinstance(out, pd.Series)
    assert out.tolist() == [7, 8]
