import pandas as pd


def combine(jan: pd.DataFrame, feb: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([jan, feb])
