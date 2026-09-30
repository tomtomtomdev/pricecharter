"""SQLite -> pandas."""

import sqlite3

import numpy as np
import pandas as pd


def _in(column: str, values: list[str] | None) -> tuple[str, list]:
    if not values:
        return "", []
    return f" AND {column} IN ({','.join('?' * len(values))})", list(values)


def load_history(
    conn: sqlite3.Connection, consoles: list[str] | None = None, conditions: list[str] | None = None
) -> pd.DataFrame:
    c_sql, c_args = _in("g.console", consoles)
    k_sql, k_args = _in("h.condition", conditions)
    df = pd.read_sql_query(
        f"""
        SELECT h.game_id, g.console, h.condition, h.month, h.price_cents
        FROM price_history h JOIN games g ON g.id = h.game_id
        WHERE h.price_cents > 0{c_sql}{k_sql}
        ORDER BY h.game_id, h.condition, h.month
        """,
        conn,
        params=c_args + k_args,
    )
    df["month"] = pd.to_datetime(df["month"])
    return df


def load_games(conn: sqlite3.Connection) -> pd.DataFrame:
    g = pd.read_sql_query("SELECT * FROM games", conn).set_index("id")
    g["release_date"] = pd.to_datetime(g["release_date"], errors="coerce")
    return g


def load_sales(conn: sqlite3.Connection) -> pd.DataFrame:
    s = pd.read_sql_query("SELECT game_id, condition, sale_date, price_cents, source FROM sales", conn)
    s["sale_date"] = pd.to_datetime(s["sale_date"], errors="coerce")
    return s


def to_panel(history: pd.DataFrame) -> pd.DataFrame:
    """One condition's history -> month x game_id log-price matrix on a full monthly index (gaps = NaN)."""
    wide = history.pivot_table(index="month", columns="game_id", values="price_cents", aggfunc="last")
    full = pd.date_range(wide.index.min(), wide.index.max(), freq="MS")
    return np.log(wide.reindex(full))
