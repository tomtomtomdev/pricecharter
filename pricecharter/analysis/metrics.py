"""Per game x condition price-series metrics, measured against the console index."""

import numpy as np
import pandas as pd

from .loader import to_panel

WINDOWS = (12, 36, 60)
TREND_WINDOW = 36
GAP_TOLERANCE = 2  # months a missing start/end point may borrow from the previous observation


def _slope_per_year(block: pd.DataFrame) -> pd.Series:
    """OLS slope of each column against time (years), ignoring NaNs; needs >= 12 points."""
    t = np.arange(len(block)) / 12.0
    y = block.to_numpy()
    mask = ~np.isnan(y)
    n = mask.sum(axis=0)
    tt = np.where(mask, t[:, None], 0.0)
    yy = np.where(mask, y, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        t_mean = tt.sum(0) / n
        y_mean = yy.sum(0) / n
        cov = (np.where(mask, (t[:, None] - t_mean) * (y - y_mean), 0.0)).sum(0)
        var = (np.where(mask, (t[:, None] - t_mean) ** 2, 0.0)).sum(0)
        slope = cov / var
    return pd.Series(np.where(n >= 12, slope, np.nan), index=block.columns)


def _one_condition(hist: pd.DataFrame, level: pd.Series, asof: pd.Timestamp) -> pd.DataFrame:
    """hist: one console+condition; level: that index's cumulative log level by month."""
    panel = to_panel(hist)
    filled = panel.ffill(limit=GAP_TOLERANCE)
    lvl = level.reindex(panel.index).ffill()
    out = pd.DataFrame(index=panel.columns)
    out.index.name = "game_id"

    def at(month: pd.Timestamp) -> pd.Series:
        if month < panel.index[0] or month > panel.index[-1]:
            return pd.Series(np.nan, index=panel.columns)
        return filled.loc[month]

    def lvl_at(month: pd.Timestamp) -> float:
        return float(lvl.loc[month]) if panel.index[0] <= month <= panel.index[-1] else np.nan

    end = at(asof)
    for w in WINDOWS:
        start_m = asof - pd.DateOffset(months=w)
        out[f"ret_{w}m"] = end - at(start_m)
        out[f"excess_{w}m"] = out[f"ret_{w}m"] - (lvl_at(asof) - lvl_at(start_m))

    upto = panel.loc[:asof]
    first_m = upto.apply(pd.Series.first_valid_index)
    last_m = upto.apply(pd.Series.last_valid_index)
    first_p = pd.Series({g: upto.at[m, g] if m is not None else np.nan for g, m in first_m.items()})
    last_p = pd.Series({g: upto.at[m, g] if m is not None else np.nan for g, m in last_m.items()})
    out["ret_all"] = last_p - first_p
    out["excess_all"] = out["ret_all"] - (
        last_m.map(lambda m: lvl.get(m, np.nan)) - first_m.map(lambda m: lvl.get(m, np.nan))
    ).astype(float)

    win = upto.loc[asof - pd.DateOffset(months=TREND_WINDOW) : asof]
    out[f"slope_{TREND_WINDOW}m"] = _slope_per_year(win)
    rets = win.diff()
    out[f"vol_{TREND_WINDOW}m"] = rets.std(ddof=0) * np.sqrt(12)
    out[f"obs_{TREND_WINDOW}m"] = win.notna().sum()

    out["n_months"] = upto.notna().sum()
    out["first_month"] = first_m
    out["last_month"] = last_m
    out["max_drawdown"] = np.exp(upto - upto.cummax()).min() - 1
    jumps = upto - upto.shift(3)
    out["jump_size"] = jumps.max()
    out["jump_month"] = jumps.idxmax().where(jumps.notna().any())
    return out[out["n_months"] > 0]


def series_metrics(history: pd.DataFrame, index: pd.DataFrame, asof: pd.Timestamp | None = None) -> pd.DataFrame:
    asof = pd.Timestamp(asof) if asof is not None else history["month"].max()
    parts = []
    for (console, cond), hist in history.groupby(["console", "condition"]):
        lvl = index[(index["console"] == console) & (index["condition"] == cond)].set_index("month")["level"]
        m = _one_condition(hist, lvl, asof).reset_index()
        m.insert(1, "console", console)
        m.insert(2, "condition", cond)
        parts.append(m)
    out = pd.concat(parts, ignore_index=True)
    out["asof"] = asof
    return out
