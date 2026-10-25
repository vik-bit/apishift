class Store:
    """A tiny ordered key-value store that kept a Python 2 style API."""

    def __init__(self):
        self._data = {}

    def set(self, key, value):
        self._data[key] = value

    def iteritems(self):
        return iter(self._data.items())


def dump(store):
    lines = []
    for k, v in store.iteritems():
        lines.append(f"{k}={v}")
    return lines
