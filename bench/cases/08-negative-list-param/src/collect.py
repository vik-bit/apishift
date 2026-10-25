import pandas as pd


def collect(items, value):
    items.append(value)
    return items


def to_frame(items):
    return pd.DataFrame({"value": items})
