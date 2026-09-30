"""Frequent factor combinations (<= 3 items) that predict 'rising', with redundancy pruning.

Level-wise search on a boolean item matrix: an itemset is only extended if it is at least as
likely to rise as the baseline, and it is only reported if its lift beats every sub-itemset's lift
by `min_gain` (so "RPG & PAL" isn't repeated as "RPG & PAL & anything").
"""

from itertools import combinations

import numpy as np
import pandas as pd

from .lift import wilson

SEP = " & "


def item_matrix(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    parts = {}
    for col in columns:
        for value in sorted(df[col].dropna().astype(str).unique()):
            if value == "unknown" or (col.startswith("kw_") and value == "no"):
                continue
            parts[f"{col}={value}"] = (df[col].astype(str) == value).to_numpy()
    return pd.DataFrame(parts, index=df.index).astype(bool)


def _factor(item: str) -> str:
    return item.split("=", 1)[0]


def _mine_one(grp: pd.DataFrame, columns, min_count, max_len, min_lift, min_gain, examples) -> list[dict]:
    X = item_matrix(grp, columns)
    y = grp["rising"].to_numpy().astype(bool)
    base = y.mean()
    if base == 0 or X.empty:
        return []
    cols = X.columns.tolist()
    M = X.to_numpy()
    lifts: dict[frozenset, float] = {}
    level = []
    for j, item in enumerate(cols):
        if M[:, j].sum() >= min_count:
            key = frozenset([item])
            level.append((key, M[:, j]))
    frequent_items = [(next(iter(k)), m) for k, m in level]
    found = []

    def record(key: frozenset, mask: np.ndarray):
        n = int(mask.sum())
        k = int(y[mask].sum())
        lift = (k / n) / base
        lifts[key] = lift
        subs = [lifts.get(frozenset(s), 0.0) for r in range(1, len(key)) for s in combinations(key, r)]
        if lift >= min_lift and all(lift >= s + min_gain for s in subs):
            lo, hi = wilson(k, n)
            members = grp.loc[mask & y]
            top = members.sort_values("excess_36m", ascending=False)["game_id"].head(examples) \
                if "excess_36m" in grp else members["game_id"].head(examples)
            found.append({
                "items": SEP.join(sorted(key)), "size": len(key), "n": n, "risers": k,
                "support": n / len(grp), "confidence": k / n, "lift": lift,
                "lift_lo": lo / base, "lift_hi": hi / base,
                "example_ids": ",".join(str(int(g)) for g in top),
            })
        return k / n >= base

    for key, mask in level:
        record(key, mask)
    for _size in range(2, max_len + 1):
        nxt, seen = [], set()
        for key, mask in level:
            if lifts.get(key, 0) < 1:
                continue
            used = {_factor(i) for i in key}
            for item, imask in frequent_items:
                if _factor(item) in used:
                    continue
                new = key | {item}
                if new in seen:
                    continue
                seen.add(new)
                m = mask & imask
                if m.sum() >= min_count:
                    record(new, m)
                    nxt.append((new, m))
        level = nxt
    return found


def mine_patterns(
    factors: pd.DataFrame, columns: list[str], min_count: int = 30, max_len: int = 3,
    min_lift: float = 1.5, min_gain: float = 0.1, examples: int = 5,
) -> pd.DataFrame:
    rows = []
    for cond, grp in factors.dropna(subset=["rising"]).groupby("condition"):
        for r in _mine_one(grp, columns, min_count, max_len, min_lift, min_gain, examples):
            rows.append({"condition": cond, **r})
    cols = ["condition", "items", "size", "n", "risers", "support", "confidence", "lift", "lift_lo", "lift_hi",
            "example_ids"]
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values(["condition", "lift_lo"], ascending=[True, False], ignore_index=True)
