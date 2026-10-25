import pandas as pd
from scoreboard import add_player


def test_adds_a_row():
    board = pd.DataFrame({"name": ["ann"], "score": [10]})
    out = add_player(board, "bob", 7)
    assert out["name"].tolist() == ["ann", "bob"]
    assert out["score"].tolist() == [10, 7]
    assert len(board) == 1  # the original is not modified
