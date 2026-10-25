import pandas as pd


def standardise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.set_axis([c.lower() for c in df.columns], axis=1, inplace=True)
    return df
