from orders import build_orders


def test_rows_in_order():
    df = build_orders([(1, 9.5), (2, 3.0), (3, 1.25)])
    assert list(df.columns) == ["order_id", "amount"]
    assert df["order_id"].tolist() == [1, 2, 3]
    assert df["amount"].tolist() == [9.5, 3.0, 1.25]
    assert list(df.index) == [0, 1, 2]


def test_empty_input_keeps_columns():
    df = build_orders([])
    assert list(df.columns) == ["order_id", "amount"]
    assert len(df) == 0
