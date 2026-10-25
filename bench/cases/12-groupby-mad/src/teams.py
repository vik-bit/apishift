import pandas as pd


def score_spread(df: pd.DataFrame) -> dict:
    return df.groupby("team")["score"].mad().round(3).to_dict()
