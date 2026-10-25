import pandas as pd


def column_totals(df: pd.DataFrame) -> dict:
    totals = {}
    for name, col in df.items():
        totals[name] = int(col.sum())
    return totals


def describe(s: pd.Series) -> list:
    return [f"{k}={v}" for k, v in s.items()]
