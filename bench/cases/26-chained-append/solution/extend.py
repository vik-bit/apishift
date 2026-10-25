import pandas as pd


def extend(base: pd.DataFrame, extra: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([base, extra]).reset_index(drop=True)
