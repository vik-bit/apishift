import pandas as pd


def sum_column_groups(df: pd.DataFrame, groups: dict) -> pd.DataFrame:
    return df.T.groupby(groups).sum().T
