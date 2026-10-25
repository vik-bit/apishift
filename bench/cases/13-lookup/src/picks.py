import pandas as pd


def picked_values(df: pd.DataFrame) -> list:
    return df.lookup(df.index, df["pick"]).tolist()
