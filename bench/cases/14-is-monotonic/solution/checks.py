import pandas as pd


def is_sorted_by_time(df: pd.DataFrame) -> bool:
    return bool(df["ts"].is_monotonic_increasing and df.index.is_monotonic_increasing)
