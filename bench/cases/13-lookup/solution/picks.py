import pandas as pd


def picked_values(df: pd.DataFrame) -> list:
    return [df.at[row, col] for row, col in zip(df.index, df["pick"])]
