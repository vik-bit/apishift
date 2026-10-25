import pandas as pd


def tally(values):
    return pd.value_counts(values).to_dict()
