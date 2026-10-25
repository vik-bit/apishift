import pandas as pd


def build_orders(raw):
    """raw: list of (order_id, amount) tuples."""
    rows = [{"order_id": order_id, "amount": amount} for order_id, amount in raw]
    return pd.DataFrame(rows, columns=["order_id", "amount"])
