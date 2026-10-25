import pandas as pd
from export import to_csv_text


def test_unix_line_endings():
    assert to_csv_text(pd.DataFrame({"a": [1, 2]})) == "a\n1\n2\n"
