import pandas as pd


def stack_quarters(q1: pd.DataFrame, others: list) -> pd.DataFrame:
    return q1.append(others, ignore_index=True)
