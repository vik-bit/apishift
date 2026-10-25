import io

import pandas as pd


def load(text):
    return pd.read_csv(io.StringIO(text))


def with_total_row(text):
    df = load(text)
    total = {"name": "TOTAL", "value": df["value"].sum()}
    return df.append(total, ignore_index=True)
