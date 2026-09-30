import json
import re
import shutil
import sqlite3

from fastapi.testclient import TestClient

from pricecharter.ui.app import create_app


def _json(html, id_):
    return json.loads(re.search(rf'<script type="application/json" id="{id_}">(.*?)</script>', html, re.S).group(1))


def test_insights_sections(analyzed_db):
    with TestClient(create_app(analyzed_db)) as c:
        r = c.get("/insights", params={"cond": "cib"})
    assert r.status_code == 200
    for h in ("Top rising factors", "Rising patterns", "Curve shapes", "Before the breakout"):
        assert h in r.text
    assert "genre=RPG" in r.text
    assert re.search(r'href="/games/\d+"', r.text)  # pattern examples link to titles
    bars = _json(r.text, "factor-bars")
    assert bars["labels"] and len(bars["labels"]) == len(bars["lift"])
    assert _json(r.text, "cluster-lines")
    assert 'href="/report"' in r.text


def test_insights_bad_cond(analyzed_db):
    with TestClient(create_app(analyzed_db)) as c:
        assert c.get("/insights", params={"cond": "boxed"}).status_code == 422


def test_insights_without_analysis(client):
    r = client.get("/insights")
    assert r.status_code == 200 and "No analysis yet" in r.text
    assert client.get("/report").status_code == 404


def test_full_report(analyzed_db):
    with TestClient(create_app(analyzed_db)) as c:
        r = c.get("/report")
    assert r.status_code == 200
    assert "Console price index" in r.text and "Caveats" in r.text


def test_cache_refreshes_on_new_run(analyzed_db, tmp_path):
    path = tmp_path / "copy.db"
    shutil.copy(analyzed_db, path)
    with TestClient(create_app(path)) as c:
        assert "2026-09-01" in c.get("/insights").text
        w = sqlite3.connect(path)
        w.execute("INSERT INTO analysis_runs (asof, window, top, consoles, conditions, min_support, n_series,"
                  " n_labeled, base_rate) SELECT '2031-01-01', window, top, consoles, conditions, min_support,"
                  " n_series, n_labeled, base_rate FROM analysis_runs ORDER BY id DESC LIMIT 1")
        w.commit()
        w.close()
        assert "2031-01-01" in c.get("/insights").text
