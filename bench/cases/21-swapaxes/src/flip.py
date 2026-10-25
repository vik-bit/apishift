import pandas as pd


def flip(df: pd.DataFrame) -> pd.DataFrame:
    return df.swapaxes(0, 1)
