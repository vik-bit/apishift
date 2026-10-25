import pandas as pd


class RowBuffer:
    def __init__(self):
        self._rows = []

    def append(self, row):
        self._rows.append(row)
        return self

    def to_frame(self):
        return pd.DataFrame(self._rows)


def buffer_rows(rows):
    buf = RowBuffer()
    for r in rows:
        buf.append(r)
    return buf.to_frame()
