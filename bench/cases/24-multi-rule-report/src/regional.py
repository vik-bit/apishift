import io

import pandas as pd


def regional_report(csv_text: str) -> str:
    sales = pd.read_csv(io.StringIO(csv_text))
    summary = pd.DataFrame({"region": pd.Series(dtype=str), "total": pd.Series(dtype=float),
                            "spread": pd.Series(dtype=float)})
    for region, group in sales.groupby("region"):
        amounts = group["amount"]
        summary = summary.append({"region": region, "total": float(amounts.sum()),
                                  "spread": round(float(amounts.mad()), 2)}, ignore_index=True)
    widths = {name: int(col.astype(str).str.len().max()) for name, col in summary.iteritems()}
    assert widths  # used by the printer
    out = io.StringIO()
    summary.to_csv(out, index=False, line_terminator="\n")
    return out.getvalue()
