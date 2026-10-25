import pandas as pd


def extend(base: pd.DataFrame, extra: pd.DataFrame) -> pd.DataFrame:
    return base.append(extra).reset_index(drop=True)
