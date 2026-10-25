import pandas as pd


def merge_readings(a: pd.Series, b: pd.Series) -> pd.Series:
    return pd.concat([a, b], ignore_index=True)
