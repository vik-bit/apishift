import pandas as pd


def score_spread(df: pd.DataFrame) -> dict:
    return df.groupby("team")["score"].agg(lambda s: (s - s.mean()).abs().mean()).round(3).to_dict()
