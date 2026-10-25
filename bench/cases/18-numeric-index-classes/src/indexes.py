import pandas as pd


def make_ids(n):
    return pd.Int64Index(range(n), name="id")


def make_weights(values):
    return pd.Float64Index(values)
