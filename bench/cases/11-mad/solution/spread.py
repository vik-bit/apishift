import pandas as pd


def spread(s: pd.Series) -> float:
    return round((s - s.mean()).abs().mean(), 4)


def frame_spread(df):
    return (df - df.mean()).abs().mean()
