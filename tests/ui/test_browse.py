from pricecharter.ui import queries
from pricecharter.ui.app import readonly_connect


def _search(path, **kw):
    conn = readonly_connect(path)
    try:
        return queries.search_games(conn, **kw)
    finally:
        conn.close()


def test_default_sort_is_current_price_desc(ui_db):
    rows, total = _search(ui_db)
    assert total == 240
    assert len(rows) == 50
    prices = [r["loose_cents"] for r in rows]
    assert prices == sorted(prices, reverse=True)
    # no snapshot prices in the synth DB, so "current" falls back to the last history month
    assert all(p is not None for p in prices)


def test_filters_and_name_search(ui_db):
    rows, total = _search(ui_db, q="mario", genre="RPG", console="pal-nes", per_page=500)
    assert total == len(rows) > 0
    assert all("Mario" in r["name"] and r["genre"] == "RPG" and r["console"] == "pal-nes" for r in rows)
    _, pal = _search(ui_db, region="pal")
    _, nes = _search(ui_db, platform="nes")
    assert (pal, nes) == (120, 240)


def test_sorts_and_pagination(ui_db):
    by_name, _ = _search(ui_db, sort="name", per_page=500)
    names = [r["name"] for r in by_name]
    assert names == sorted(names, key=str.lower)
    by_rank, _ = _search(ui_db, sort="rank", console="nes", per_page=10)
    assert [r["list_rank"] for r in by_rank] == list(range(1, 11))
    page2, _ = _search(ui_db, sort="rank", console="nes", per_page=10, page=2)
    assert page2[0]["list_rank"] == 11
    cib, _ = _search(ui_db, cond="cib", per_page=500)
    assert [r["cib_cents"] for r in cib if r["cib_cents"]] == sorted((r["cib_cents"] for r in cib if r["cib_cents"]),
                                                                    reverse=True)


def test_excess_sort_needs_analysis(ui_db, analyzed_db):
    rows, _ = _search(ui_db, sort="excess")
    assert all(r["excess_36m"] is None for r in rows)  # falls back to price order, no crash
    rows, _ = _search(analyzed_db, sort="excess", cond="loose")
    ex = [r["excess_36m"] for r in rows]
    assert ex == sorted(ex, reverse=True) and ex[0] is not None


def test_facets(ui_db):
    conn = readonly_connect(ui_db)
    f = queries.facets(conn)
    conn.close()
    assert f["genre"] == ["Action", "Puzzle", "RPG", "Sports"]
    assert f["console"] == ["nes", "pal-nes"]
    assert f["region"] == ["ntsc-u", "pal"]


def test_games_page(client):
    r = client.get("/games", params={"q": "mario", "genre": "RPG"})
    assert r.status_code == 200
    assert "<html" in r.text and "Super Mario" in r.text
    assert 'hx-get="/games"' in r.text


def test_games_htmx_partial(client):
    r = client.get("/games", params={"q": "Game 7"}, headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "<html" not in r.text
    assert 'href="/games/7"' in r.text


def test_games_bad_sort(client):
    assert client.get("/games", params={"sort": "drop table"}).status_code == 422
