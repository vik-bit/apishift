import pandas as pd


def add_player(board: pd.DataFrame, name: str, score: int) -> pd.DataFrame:
    row = pd.Series({"name": name, "score": score})
    return pd.concat([board, row.to_frame().T], ignore_index=True)
