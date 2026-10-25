import pandas as pd


class Ledger:
    def __init__(self):
        self.entries = pd.DataFrame({"item": pd.Series(dtype=str), "cost": pd.Series(dtype=float)})
        self.history = []

    def add(self, item, cost):
        row = pd.DataFrame([{"item": item, "cost": cost}])
        self.entries = row if self.entries.empty else pd.concat([self.entries, row], ignore_index=True)
        self.history.append(f"added {item}")

    def total(self):
        return float(self.entries["cost"].sum())
