import pandas as pd
from quarters import stack_quarters


def test_stacks_all_quarters():
    q = [pd.DataFrame({"rev": [i]}) for i in range(4)]
    out = stack_quarters(q[0], q[1:])
    assert out["rev"].tolist() == [0, 1, 2, 3]
    assert list(out.index) == [0, 1, 2, 3]
