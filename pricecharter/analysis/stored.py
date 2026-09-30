"""Rebuild the latest AnalysisResult from the tables `persist` wrote (for the web UI and re-rendering)."""

import sqlite3

import pandas as pd

from .loader import load_games
from .run import OPTIONAL_TABLES, TABLES, AnalysisResult

PARAMS = ["asof", "window", "top", "consoles", "conditions", "min_support", "n_series", "n_labeled", "base_rate"]
DATE_COLUMNS = {"console_index": ["month"], "series_metrics": ["first_month", "last_month", "jump_month", "asof"]}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _read(conn: sqlite3.Connection, name: str) -> pd.DataFrame:
    df = pd.read_sql_query(f"SELECT * FROM {name}", conn)
    for col in DATE_COLUMNS.get(name, []):
        df[col] = pd.to_datetime(df[col])
    return df


def _model_summary(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM model_summary LIMIT 1").fetchone()
    cols = [d[0] for d in conn.execute("SELECT * FROM model_summary LIMIT 0").description]
    out = dict(zip(cols, row, strict=True)) if row else {}
    if "signal" in out:  # persist writes bools as text
        out["signal"] = out["signal"] == "True"
    return out


def load_stored(conn: sqlite3.Connection) -> AnalysisResult | None:
    have = _tables(conn)
    if "analysis_runs" not in have or not set(TABLES) <= have:
        return None
    run = conn.execute(f"SELECT {', '.join(PARAMS)} FROM analysis_runs ORDER BY id DESC LIMIT 1").fetchone()
    if run is None:
        return None
    frames = {name: _read(conn, name) for name in TABLES}
    res = AnalysisResult(
        dict(zip(PARAMS, run, strict=True)), frames["console_index"], frames["series_metrics"],
        factors=pd.DataFrame(), factor_lift=frames["factor_lift"], patterns=frames["patterns"],
        games=load_games(conn), history=pd.DataFrame(),
    )
    for name in OPTIONAL_TABLES:
        if name in have:
            setattr(res, name, _read(conn, name))
    if "model_summary" in have:
        res.model_summary = _model_summary(conn)
    return res
