import pandas as pd


def add_batch(frame, batch):
    """Append a batch of rows (a DataFrame) to the running frame."""
    return pd.concat([frame, batch], ignore_index=True)


def empty_frame():
    return pd.DataFrame({"id": [0], "qty": [0]}).iloc[:0]
