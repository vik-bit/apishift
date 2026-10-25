from totals import with_total_row


def test_total_row():
    out = with_total_row("name,value\na,1\nb,2\n")
    assert out["name"].tolist() == ["a", "b", "TOTAL"]
    assert out["value"].tolist() == [1, 2, 3]
