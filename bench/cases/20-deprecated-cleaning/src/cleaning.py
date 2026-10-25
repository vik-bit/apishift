import pandas as pd


def clean(df: pd.DataFrame) -> pd.DataFrame:
    out = df.applymap(lambda v: v.strip() if isinstance(v, str) else v)
    out = out.fillna(method="ffill")
    return out.backfill()
