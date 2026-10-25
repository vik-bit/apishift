from buffer import buffer_rows


def test_buffers_rows():
    df = buffer_rows([{"a": 1}, {"a": 2}])
    assert df["a"].tolist() == [1, 2]
