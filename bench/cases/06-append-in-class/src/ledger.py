import pandas as pd


class Ledger:
    def __init__(self):
        self.entries = pd.DataFrame({"item": pd.Series(dtype=str), "cost": pd.Series(dtype=float)})
        self.history = []

    def add(self, item, cost):
        self.entries = self.entries.append({"item": item, "cost": cost}, ignore_index=True)
        self.history.append(f"added {item}")

    def total(self):
        return float(self.entries["cost"].sum())
