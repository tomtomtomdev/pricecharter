"""Console price index: median monthly log-return across a console's titles, per condition."""

import numpy as np
import pandas as pd

KEYS = ["console", "condition"]


def monthly_returns(history: pd.DataFrame) -> pd.DataFrame:
    """Log-return per game/condition between consecutive calendar months (gaps break the chain)."""
    h = history.sort_values(["game_id", "condition", "month"]).copy()
    h["logp"] = np.log(h["price_cents"].astype(float))
    g = h.groupby(["game_id", "condition"], sort=False)
    prev_month = g["month"].shift()
    consecutive = prev_month + pd.DateOffset(months=1) == h["month"]
    h["ret"] = (h["logp"] - g["logp"].shift()).where(consecutive)
    return h.dropna(subset=["ret"])[["game_id", "console", "condition", "month", "ret"]]


def console_index(history: pd.DataFrame, min_games: int = 5) -> pd.DataFrame:
    """Columns: console, condition, month, ret (median, NaN if < min_games), n, level (cumulative log)."""
    r = monthly_returns(history)
    agg = r.groupby([*KEYS, "month"])["ret"].agg(ret="median", n="size").reset_index()
    out = []
    for (console, cond), grp in history.groupby(KEYS):
        months = pd.date_range(grp["month"].min(), grp["month"].max(), freq="MS")
        frame = pd.DataFrame({"console": console, "condition": cond, "month": months})
        frame = frame.merge(agg, on=[*KEYS, "month"], how="left")
        frame["n"] = frame["n"].fillna(0).astype(int)
        frame.loc[frame["n"] < min_games, "ret"] = np.nan
        frame["level"] = frame["ret"].fillna(0).cumsum()
        out.append(frame)
    return pd.concat(out, ignore_index=True)
