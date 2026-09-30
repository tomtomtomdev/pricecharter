import json
import math
import re

import pytest
from fastapi.testclient import TestClient

from pricecharter.ui import queries
from pricecharter.ui.app import create_app, readonly_connect, templates


def _one(path, sql):
    conn = readonly_connect(path)
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def test_logpct_filter():
    f = templates.env.filters["logpct"]
    assert f(math.log(1.5)) == "+50%"
    assert f(math.log(0.8)) == "−20%"
    assert f(None) == ""


def test_game_analysis_absent_without_tables(ui_db):
    conn = readonly_connect(ui_db)
    assert queries.game_analysis(conn, 1) is None
    conn.close()


def test_game_analysis(analyzed_db):
    gid = _one(analyzed_db, "SELECT game_id FROM series_metrics WHERE rising = 1 AND condition = 'loose' LIMIT 1")
    conn = readonly_connect(analyzed_db)
    a = queries.game_analysis(conn, gid)
    hist = queries.history(conn, gid)
    conn.close()
    loose = next(m for m in a["metrics"] if m["condition"] == "loose")
    assert loose["rising"] == 1 and loose["shape"]
    idx = next(s for s in a["index"] if s["cond"] == "loose")
    # rebased: starts at the title's first loose price, same months as its history (up to asof)
    first_month, first_cents = hist["loose"][0]
    assert idx["x"][0] == first_month and idx["y"][0] == pytest.approx(first_cents / 100)
    assert len(idx["x"]) == len(set(idx["x"])) and idx["x"] == sorted(idx["x"])


def test_game_page_with_analysis(analyzed_db):
    gid = _one(analyzed_db, "SELECT game_id FROM series_metrics WHERE rising = 1 AND condition = 'loose' LIMIT 1")
    wl = _one(analyzed_db, "SELECT game_id FROM watchlist LIMIT 1")
    with TestClient(create_app(analyzed_db)) as c:
        r = c.get(f"/games/{gid}")
        w = c.get(f"/games/{wl}")
    assert "Rising" in r.text and "vs console index" in r.text
    m = re.search(r'<script type="application/json" id="index-data">(.*?)</script>', r.text, re.S)
    assert {s["cond"] for s in json.loads(m.group(1))} >= {"loose"}
    assert "On the watchlist" in w.text


def test_game_page_without_analysis(client):
    r = client.get("/games/1")
    assert "index-data" not in r.text and "Rising" not in r.text
    assert "run <code>./run.sh analyze</code>" in r.text


def test_browse_excess_shown_as_percent(analyzed_db):
    ex = _one(analyzed_db, "SELECT max(excess_36m) FROM series_metrics WHERE condition = 'loose'")
    with TestClient(create_app(analyzed_db)) as c:
        r = c.get("/games", params={"sort": "excess"})
    assert f"+{math.exp(ex) - 1:.0%}" in r.text


def test_pct_filter_no_negative_zero():
    assert templates.env.filters["pct"](-0.004) == "0%"
    assert templates.env.filters["pct"](0.126) == "+13%"
