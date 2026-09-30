from fastapi.testclient import TestClient

from pricecharter.ui import queries
from pricecharter.ui.app import create_app, readonly_connect


def _wl(path, **kw):
    conn = readonly_connect(path)
    try:
        return queries.watchlist(conn, **kw)
    finally:
        conn.close()


def test_watchlist_query(analyzed_db):
    rows = _wl(analyzed_db, cond="cib")
    assert rows and all(r["condition"] == "cib" for r in rows)
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(r["patterns"], list) and r["patterns"] for r in rows)
    pal = _wl(analyzed_db, cond="cib", console="pal-nes")
    assert pal and all(r["console"] == "pal-nes" for r in pal)
    by_price = [r["price_cents"] for r in _wl(analyzed_db, cond="cib", sort="price")]
    assert by_price == sorted(by_price, reverse=True)


def test_watchlist_absent(ui_db):
    assert _wl(ui_db) is None


def test_watchlist_page(analyzed_db):
    with TestClient(create_app(analyzed_db)) as c:
        r = c.get("/watchlist", params={"cond": "loose", "sort": "name"})
        bad = c.get("/watchlist", params={"sort": "; drop"})
    assert r.status_code == 200 and "Watchlist" in r.text
    assert 'href="/games/' in r.text and "genre=RPG" in r.text
    assert 'href="/watchlist"' in r.text  # nav
    assert bad.status_code == 422


def test_watchlist_page_without_analysis(client):
    r = client.get("/watchlist")
    assert r.status_code == 200 and "No analysis yet" in r.text
