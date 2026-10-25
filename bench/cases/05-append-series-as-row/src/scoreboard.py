import pandas as pd


def add_player(board: pd.DataFrame, name: str, score: int) -> pd.DataFrame:
    row = pd.Series({"name": name, "score": score})
    return board.append(row, ignore_index=True)
