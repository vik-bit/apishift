import io

import pandas as pd


def to_csv_text(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False, line_terminator="\n")
    return buf.getvalue()
