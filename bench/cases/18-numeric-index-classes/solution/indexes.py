import pandas as pd


def make_ids(n):
    return pd.Index(range(n), dtype="int64", name="id")


def make_weights(values):
    return pd.Index(values, dtype="float64")
