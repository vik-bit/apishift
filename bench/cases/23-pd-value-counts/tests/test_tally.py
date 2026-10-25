from tally import tally


def test_tally():
    assert tally(["a", "b", "a"]) == {"a": 2, "b": 1}
