import pandas as pd


def weekend_flags(dates):
    s = pd.Series(pd.to_datetime(dates))
    return pd.np.where(s.dt.dayofweek >= 5, 1, 0).tolist()


def start_of_2024():
    return pd.datetime(2024, 1, 1)
