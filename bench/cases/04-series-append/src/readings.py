import pandas as pd


def merge_readings(a: pd.Series, b: pd.Series) -> pd.Series:
    return a.append(b, ignore_index=True)
