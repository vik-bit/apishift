import pandas as pd


def spread(s: pd.Series) -> float:
    return round(s.mad(), 4)


def frame_spread(df):
    return df.mad()
