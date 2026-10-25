import io

import pandas as pd


def regional_report(csv_text: str) -> str:
    sales = pd.read_csv(io.StringIO(csv_text))
    rows = []
    for region, group in sales.groupby("region"):
        amounts = group["amount"]
        rows.append({"region": region, "total": float(amounts.sum()),
                     "spread": round(float((amounts - amounts.mean()).abs().mean()), 2)})
    summary = pd.DataFrame(rows, columns=["region", "total", "spread"])
    widths = {name: int(col.astype(str).str.len().max()) for name, col in summary.items()}
    assert widths  # used by the printer
    out = io.StringIO()
    summary.to_csv(out, index=False, lineterminator="\n")
    return out.getvalue()
