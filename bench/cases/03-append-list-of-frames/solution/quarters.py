import pandas as pd


def stack_quarters(q1: pd.DataFrame, others: list) -> pd.DataFrame:
    return pd.concat([q1, *others], ignore_index=True)
