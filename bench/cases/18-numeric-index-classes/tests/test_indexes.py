from indexes import make_ids, make_weights


def test_ids():
    idx = make_ids(3)
    assert list(idx) == [0, 1, 2] and idx.dtype == "int64" and idx.name == "id"


def test_weights():
    assert make_weights([1, 2]).dtype == "float64"
