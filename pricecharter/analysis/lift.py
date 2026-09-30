"""Factor lift: how much more often titles with a factor value are 'rising' than the baseline."""

import math

import pandas as pd

Z = 1.96


def wilson(k: int, n: int, z: float = Z) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def factor_lift(factors: pd.DataFrame, columns: list[str], min_support: int = 30) -> pd.DataFrame:
    rows = []
    labeled = factors.dropna(subset=["rising"])
    for cond, grp in labeled.groupby("condition"):
        base = grp["rising"].mean()
        if not base:
            continue
        for col in columns:
            stats = grp.groupby(col)["rising"].agg(n="size", risers="sum")
            for value, s in stats.iterrows():
                if s["n"] < min_support or (col.startswith("kw_") and value == "no"):
                    continue
                n, k = int(s["n"]), int(s["risers"])
                lo, hi = wilson(k, n)
                rows.append({
                    "condition": cond, "factor": col, "value": str(value), "n": n, "risers": k,
                    "rate": k / n, "base_rate": base, "lift": (k / n) / base,
                    "rate_lo": lo, "rate_hi": hi, "lift_lo": lo / base, "lift_hi": hi / base,
                })
    cols = ["condition", "factor", "value", "n", "risers", "rate", "base_rate", "lift",
            "rate_lo", "rate_hi", "lift_lo", "lift_hi"]
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values(["condition", "lift"], ascending=[True, False], ignore_index=True)
