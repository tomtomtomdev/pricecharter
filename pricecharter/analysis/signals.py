"""What changed in the months before the biggest jumps?

A breakout is a month whose next `horizon`-month excess return is in the top `top` share for its
condition (first month of each run, at most one per 12 months per series). Controls are ordinary
months far from any breakout of the same series. Each pre-signal uses only data up to that month.
"""

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from .loader import to_panel

SIGNALS = ["trend_12m", "acceleration", "volatility_12m", "drawdown_24m", "cib_loose_change_12m"]
DESCRIPTIONS = {
    "trend_12m": "excess return over the prior 12 months",
    "acceleration": "last-3-month pace (annualized) minus 12-month trend",
    "volatility_12m": "std of monthly excess moves, prior 12 months",
    "drawdown_24m": "distance below the prior 24-month high",
    "cib_loose_change_12m": "change in log(CIB/Loose) over the prior 12 months",
}


def _excess_panel(hist: pd.DataFrame, level: pd.Series) -> pd.DataFrame:
    panel = to_panel(hist)
    return panel.sub(level.reindex(panel.index).ffill().fillna(0), axis=0)


def _long(frame: pd.DataFrame, name: str) -> pd.Series:
    return frame.stack().rename(name)


def pre_features(history: pd.DataFrame, index: pd.DataFrame, horizon: int = 6) -> pd.DataFrame:
    parts = []
    for (console, cond), hist in history.groupby(["console", "condition"]):
        lvl = index[(index["console"] == console) & (index["condition"] == cond)].set_index("month")["level"]
        e = _excess_panel(hist, lvl)
        trend = e - e.shift(12)
        cols = {
            "trend_12m": trend,
            "acceleration": (e - e.shift(3)) * 4 - trend,
            "volatility_12m": e.diff().rolling(12, min_periods=8).std(),
            "drawdown_24m": e - e.rolling(24, min_periods=12).max(),
            "fwd": e.shift(-horizon) - e,
        }
        df = pd.concat([_long(f, k) for k, f in cols.items()], axis=1)
        df.index.names = ["month", "game_id"]
        parts.append(df.reset_index().assign(console=console, condition=cond))
    feats = pd.concat(parts, ignore_index=True)

    ratio = []
    for _console, hist in history.groupby("console"):
        loose, cib = hist[hist["condition"] == "loose"], hist[hist["condition"] == "cib"]
        if loose.empty or cib.empty:
            continue
        lp, cp = to_panel(loose), to_panel(cib)
        months = lp.index.union(cp.index)
        gap = cp.reindex(months) - lp.reindex(index=months, columns=cp.columns)
        change = (gap - gap.shift(12)).stack().rename("cib_loose_change_12m")
        change.index.names = ["month", "game_id"]
        ratio.append(change.reset_index())
    if ratio:
        feats = feats.merge(pd.concat(ratio, ignore_index=True), on=["month", "game_id"], how="left")
    else:
        feats["cib_loose_change_12m"] = np.nan
    return feats


def _label(feats: pd.DataFrame, top: float, gap: int, controls_per: int, seed: int) -> pd.DataFrame:
    f = feats.dropna(subset=["fwd"]).sort_values(["game_id", "condition", "month"])
    threshold = f["fwd"].quantile(1 - top)
    hot = f[f["fwd"] >= threshold]
    kept = []
    for _, g in hot.groupby(["game_id", "condition"]):
        last = None
        for m in g["month"]:
            if last is None or m >= last + pd.DateOffset(months=gap):
                kept.append((g["game_id"].iloc[0], g["condition"].iloc[0], m))
                last = m
    breaks = pd.DataFrame(kept, columns=["game_id", "condition", "month"])
    # controls: ordinary months (below-median forward move) more than `gap` months from any breakout
    near = f.merge(breaks.rename(columns={"month": "bm"}), on=["game_id", "condition"], how="left")
    near["dist"] = (near["month"] - near["bm"]).abs().dt.days
    too_close = near[near["dist"] <= gap * 31][["game_id", "condition", "month"]].drop_duplicates()
    pool = f.merge(too_close, how="left", indicator=True)
    pool = pool[pool["_merge"] == "left_only"].drop(columns="_merge")
    pool = pool[pool["fwd"] < f["fwd"].median()]
    n_ctrl = min(len(pool), max(1, len(breaks)) * controls_per)
    ctrl = pool.sample(n=n_ctrl, random_state=seed) if n_ctrl else pool
    b = f.merge(breaks, on=["game_id", "condition", "month"])
    return pd.concat([b.assign(breakout=True), ctrl.assign(breakout=False)], ignore_index=True)


def compare(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rows = []
    for col in columns:
        a = df.loc[df["breakout"], col].dropna()
        b = df.loc[~df["breakout"], col].dropna()
        if len(a) < 10 or len(b) < 10:
            continue
        pooled = np.sqrt(((len(a) - 1) * a.var() + (len(b) - 1) * b.var()) / (len(a) + len(b) - 2))
        rows.append({
            "signal": col, "breakout_mean": a.mean(), "control_mean": b.mean(), "diff": a.mean() - b.mean(),
            "cohens_d": (a.mean() - b.mean()) / pooled if pooled else 0.0,
            "p_value": float(mannwhitneyu(a, b).pvalue), "n_breakout": len(a), "n_control": len(b),
        })
    cols = ["signal", "breakout_mean", "control_mean", "diff", "cohens_d", "p_value", "n_breakout", "n_control"]
    return pd.DataFrame(rows, columns=cols)


def pre_breakout_signals(
    history: pd.DataFrame, index: pd.DataFrame, horizon: int = 6, top: float = 0.05,
    conditions: list[str] | None = None, gap: int = 12, controls_per: int = 3, seed: int = 0,
) -> pd.DataFrame:
    feats = pre_features(history, index, horizon)
    out = []
    for cond, f in feats.groupby("condition"):
        if conditions and cond not in conditions:
            continue
        table = compare(_label(f, top, gap, controls_per, seed), SIGNALS)
        out.append(table.assign(condition=cond))
    if not out:
        return compare(pd.DataFrame(columns=[*SIGNALS, "breakout"]), []).assign(condition=[])
    res = pd.concat(out, ignore_index=True)
    res["description"] = res["signal"].map(DESCRIPTIONS)
    return res.sort_values(["condition", "cohens_d"], key=lambda s: s.abs() if s.name == "cohens_d" else s,
                           ascending=[True, False], ignore_index=True)
