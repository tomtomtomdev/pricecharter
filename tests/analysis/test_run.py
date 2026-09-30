import sqlite3

import pytest

from pricecharter.analysis.run import TABLES, analyze, persist
from tests.analysis import synth


@pytest.fixture
def db(tmp_path):
    conn = synth.build(tmp_path / "s.db", games_per_console=60)
    yield conn
    conn.close()


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_analyze_and_persist(db):
    res = analyze(db)
    assert {"console_index", "series_metrics", "factors", "factor_lift", "patterns"} <= set(vars(res))
    persist(db, res)
    for t in TABLES:
        assert _count(db, t) > 0, t
    run = db.execute("SELECT * FROM analysis_runs").fetchone()
    assert run["window"] == 36 and run["top"] == 0.2 and run["n_labeled"] > 0
    assert run["asof"] == "2026-09-01"


def test_rerun_replaces_results_but_logs_runs(db):
    persist(db, analyze(db))
    n = _count(db, "series_metrics")
    persist(db, analyze(db, window=12))
    assert _count(db, "series_metrics") == n
    assert _count(db, "analysis_runs") == 2
    assert db.execute("SELECT window FROM analysis_runs ORDER BY id DESC").fetchone()[0] == 12


def test_filters(db):
    res = analyze(db, consoles=["pal-nes"], conditions=["cib"])
    assert set(res.series_metrics["console"]) == {"pal-nes"}
    assert set(res.series_metrics["condition"]) == {"cib"}


def test_empty_db_is_graceful(tmp_path):
    from pricecharter import db as dbm

    conn = dbm.connect(tmp_path / "e.db")
    with pytest.raises(ValueError, match="no price history"):
        analyze(conn)


def test_cli_analyze_args():
    from pricecharter.cli import parse_args

    a = parse_args(["analyze", "--window", "12", "--top", "0.1", "--condition", "cib", "new"])
    assert (a.stage, a.window, a.top, a.condition) == ("analyze", 12, 0.1, ["cib", "new"])


def test_dates_stored_as_iso(db):
    persist(db, analyze(db))
    v = db.execute("SELECT month FROM console_index LIMIT 1").fetchone()[0]
    assert isinstance(v, str) and len(v) == 10
    assert isinstance(db, sqlite3.Connection)
