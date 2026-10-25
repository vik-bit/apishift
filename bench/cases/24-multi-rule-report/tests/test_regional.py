from regional import regional_report


def test_report():
    text = "region,amount\nnorth,10\nnorth,20\nsouth,5\n"
    assert regional_report(text) == "region,total,spread\nnorth,30.0,5.0\nsouth,5.0,0.0\n"
