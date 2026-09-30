"""End-to-end analysis: load -> index -> metrics -> label -> factors -> lift -> patterns, then persist."""

import json
import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from .clusters import cluster_curves, curve_matrix, profile_clusters
from .factors import CATEGORICAL, build_factors
from .index import console_index
from .label import label_rising
from .lift import factor_lift
from .loader import load_games, load_history, load_sales
from .metrics import series_metrics
from .model import build_samples, fit_model
from .patterns import mine_patterns
from .signals import pre_breakout_signals
from .watchlist import watchlist

TABLES = ["console_index", "series_metrics", "factor_lift", "patterns"]
OPTIONAL_TABLES = ["model_importance", "curve_clusters", "cluster_summary", "cluster_profile", "pre_breakout",
                   "watchlist"]
PATTERN_FACTORS = [c for c in CATEGORICAL if c not in ("developer",)]


@dataclass
class AnalysisResult:
    params: dict
    console_index: pd.DataFrame
    series_metrics: pd.DataFrame
    factors: pd.DataFrame
    factor_lift: pd.DataFrame
    patterns: pd.DataFrame
    games: pd.DataFrame = field(repr=False)
    history: pd.DataFrame = field(repr=False)
    model_summary: dict = field(default_factory=dict)
    model_importance: pd.DataFrame = field(default_factory=pd.DataFrame)
    curve_clusters: pd.DataFrame = field(default_factory=pd.DataFrame)
    cluster_summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    cluster_profile: pd.DataFrame = field(default_factory=pd.DataFrame)
    pre_breakout: pd.DataFrame = field(default_factory=pd.DataFrame)
    sales: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)
    model_fit: object = field(default=None, repr=False)
    watchlist: pd.DataFrame = field(default_factory=pd.DataFrame)


def analyze(
    conn: sqlite3.Connection, consoles: list[str] | None = None, conditions: list[str] | None = None,
    window: int = 36, top: float = 0.2, asof: str | None = None, min_support: int = 30, model: bool = True,
    clusters: int = 5,
) -> AnalysisResult:
    history = load_history(conn, consoles, conditions)
    if history.empty:
        raise ValueError("no price history for the selected consoles/conditions; run the details crawl first")
    games = load_games(conn)
    idx = console_index(history)
    metrics = label_rising(series_metrics(history, idx, asof=asof), window=window, top=top)
    sales = load_sales(conn)
    factors = build_factors(metrics, games, history, sales, window=window)
    support = max(5, min(min_support, int(factors["rising"].notna().sum() * 0.02)))
    lift = factor_lift(factors, CATEGORICAL, min_support=support)
    patterns = mine_patterns(factors, PATTERN_FACTORS, min_count=support)
    params = {
        "asof": metrics["asof"].iloc[0].date().isoformat(), "window": window, "top": top,
        "consoles": json.dumps(sorted(history["console"].unique().tolist())),
        "conditions": json.dumps(sorted(history["condition"].unique().tolist())),
        "min_support": support, "n_series": len(metrics), "n_labeled": int(metrics["rising"].notna().sum()),
        "base_rate": float(metrics["rising"].mean()) if metrics["rising"].notna().any() else None,
    }
    res = AnalysisResult(params, idx, metrics, factors, lift, patterns, games, history, sales=sales)
    res.curve_clusters, res.cluster_summary = cluster_curves(curve_matrix(history, idx), k=clusters)
    if not res.curve_clusters.empty:
        res.cluster_profile = profile_clusters(res.curve_clusters, factors, CATEGORICAL, min_support=support)
    res.pre_breakout = pre_breakout_signals(history, idx)
    if model:
        fitted = fit_model(build_samples(history, idx, games, window=window), window=window)
        res.model_summary, res.model_importance, res.model_fit = fitted.summary, fitted.importance, fitted
    res.watchlist = watchlist(res)
    return res


def _for_sql(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    return out


def persist(conn: sqlite3.Connection, res: AnalysisResult) -> int:
    for name in TABLES:
        _for_sql(getattr(res, name)).to_sql(name, conn, if_exists="replace", index=False)
    for name in OPTIONAL_TABLES:
        df = getattr(res, name)
        if not df.empty:
            _for_sql(df).to_sql(name, conn, if_exists="replace", index=False)
    if res.model_summary:
        pd.DataFrame([{k: (str(v) if isinstance(v, bool) else v) for k, v in res.model_summary.items()}]).to_sql(
            "model_summary", conn, if_exists="replace", index=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS analysis_runs (
            id INTEGER PRIMARY KEY, ran_at TEXT NOT NULL DEFAULT (datetime('now')), asof TEXT, window INTEGER,
            top REAL, consoles TEXT, conditions TEXT, min_support INTEGER, n_series INTEGER, n_labeled INTEGER,
            base_rate REAL)"""
    )
    cols = list(res.params)
    cur = conn.execute(
        f"INSERT INTO analysis_runs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        [res.params[c] for c in cols],
    )
    conn.commit()
    return cur.lastrowid
