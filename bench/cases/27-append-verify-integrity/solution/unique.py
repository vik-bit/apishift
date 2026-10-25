import pandas as pd


def strict_union(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([a, b], verify_integrity=True)
