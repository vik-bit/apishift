import pandas as pd


def build_orders(raw):
    """raw: list of (order_id, amount) tuples."""
    orders = pd.DataFrame(columns=["order_id", "amount"])
    for order_id, amount in raw:
        orders = orders.append({"order_id": order_id, "amount": amount}, ignore_index=True)
    return orders
