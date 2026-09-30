"""Titles that look like past risers *today*: current factors matched against the rising patterns,
plus the model's forecast when the model passed its out-of-sample check."""

import numpy as np
import pandas as pd

from .factors import build_factors
from .model import build_samples, predict
from .patterns import SEP


def match_patterns(factors: pd.DataFrame, patterns: pd.DataFrame) -> tuple[pd.Series, list[list[str]]]:
    """Per row: sum of log(lower-bound lift) over matched rules of its condition, and the rules."""
    score = pd.Series(0.0, index=factors.index)
    matched: list[list[str]] = [[] for _ in range(len(factors))]
    pos = {ix: i for i, ix in enumerate(factors.index)}
    for rule in patterns[patterns["lift_lo"] > 1].itertuples():
        mask = factors["condition"] == rule.condition
        for item in rule.items.split(SEP):
            col, val = item.split("=", 1)
            if col not in factors:
                mask &= False
                break
            mask &= factors[col].astype(str) == val
        score[mask] += np.log(rule.lift_lo)
        for ix in factors.index[mask]:
            matched[pos[ix]].append(rule.items)
    return score, matched


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd else s * 0


def watchlist(res, top: int = 50) -> pd.DataFrame:
    """`res` is an AnalysisResult. Factors are re-measured at the as-of month (window start = now)."""
    window = res.params["window"]
    asof = pd.Timestamp(res.params["asof"])
    current = build_factors(res.series_metrics, res.games, res.history, _sales(res), window=window, start=asof)
    score, matched = match_patterns(current, res.patterns)
    current["pattern_score"] = score.to_numpy()
    current["matched"] = [" | ".join(m[:3]) for m in matched]
    current["model_pred"] = np.nan
    fitted = getattr(res, "model_fit", None)
    if fitted is not None and res.model_summary.get("signal"):
        rows = build_samples(res.history, res.console_index, res.games, window=window, t0s=[asof], with_target=False)
        if not rows.empty:
            rows["model_pred"] = predict(fitted, rows)
            current = current.drop(columns="model_pred").merge(
                rows[["game_id", "condition", "model_pred"]], on=["game_id", "condition"], how="left")
    current["already_rising"] = current["rising"] == 1
    last = res.history.sort_values("month").groupby(["game_id", "condition"])["price_cents"].last()
    current["price_cents"] = [last.get((g, c)) for g, c in zip(current["game_id"], current["condition"], strict=True)]
    current["name"] = current["game_id"].map(res.games["name"])
    current = current[(current["pattern_score"] > 0) | current["model_pred"].notna()]  # nothing to say otherwise
    out = []
    for _cond, g in current.groupby("condition"):
        g = g.copy()
        g["score"] = _zscore(g["pattern_score"])
        if g["model_pred"].notna().any():
            g["score"] = g["score"] + _zscore(g["model_pred"].fillna(g["model_pred"].median()))
        out.append(g.sort_values("score", ascending=False).head(top))
    cols = ["condition", "game_id", "name", "console", "price_cents", "score", "pattern_score", "model_pred",
            "matched", "already_rising", "genre", "publisher", "region", "platform"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def _sales(res) -> pd.DataFrame:
    s = getattr(res, "sales", None)
    return s if s is not None else pd.DataFrame(columns=["game_id", "condition", "sale_date", "price_cents"])
