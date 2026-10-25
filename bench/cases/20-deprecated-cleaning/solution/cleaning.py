import pandas as pd


def clean(df: pd.DataFrame) -> pd.DataFrame:
    out = df.map(lambda v: v.strip() if isinstance(v, str) else v)
    out = out.ffill()
    return out.bfill()
