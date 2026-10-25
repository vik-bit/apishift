from collect import collect, to_frame


def test_collect_appends_to_list():
    assert collect([1], 2) == [1, 2]


def test_to_frame():
    assert to_frame([1, 2])["value"].tolist() == [1, 2]
