from store import Store, dump


def test_dump():
    s = Store()
    s.set("a", 1)
    s.set("b", 2)
    assert dump(s) == ["a=1", "b=2"]
