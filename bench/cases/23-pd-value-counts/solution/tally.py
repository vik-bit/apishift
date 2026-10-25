import pandas as pd


def tally(values):
    return pd.Series(values).value_counts().to_dict()
