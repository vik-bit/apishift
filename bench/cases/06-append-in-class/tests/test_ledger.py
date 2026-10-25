from ledger import Ledger


def test_ledger_tracks_entries_and_history():
    led = Ledger()
    led.add("pen", 2.5)
    led.add("book", 10.0)
    assert led.total() == 12.5
    assert led.entries["item"].tolist() == ["pen", "book"]
    assert led.history == ["added pen", "added book"]
