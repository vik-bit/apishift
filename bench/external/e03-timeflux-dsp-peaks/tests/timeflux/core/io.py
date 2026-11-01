"""timeflux.core.io: lightweight i/o wrapper

Vendored from timeflux (MIT) for the APIShift benchmark. Port.set() is left out: it needs the
timeflux scheduler and the tests do not use it.
"""


class Port:
    def __init__(self, persistent=False):
        self.persistent = persistent
        self.clear()

    def clear(self):
        if not self.persistent:
            self.data = None
            self.meta = {}

    def ready(self):
        return self.data is not None and len(self.data) > 0
