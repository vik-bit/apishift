"""timeflux.helpers.clock

Vendored from timeflux (MIT) for the APIShift benchmark: now() only.
"""

from time import time

import numpy as np


def now():
    """Return the current time as `np.datetime64['us']`."""
    return np.datetime64(int(time() * 1e6), "us")
