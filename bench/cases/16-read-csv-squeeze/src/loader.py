import pandas as pd


def load_ids(path):
    return pd.read_csv(path, squeeze=True)
