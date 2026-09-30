import json
import math
import re

import pytest

from pricecharter.ui import queries
from pricecharter.ui.app import readonly_connect


def _cmp(path, ids, **kw):
    conn = readonly_connect(path)
    try:
        return queries.compare_series(conn, ids, **kw)
    finally:
        conn.close()


def test_raw(ui_db):
    s = _cmp(ui_db, [1, 2])
    assert [x["id"] for x in s] == [1, 2]
    conn = readonly_connect(ui_db)
    h = queries.history(conn, 1)["loose"]
    conn.close()
    assert s[0]["x"][0] == h[0][0] and s[0]["y"][0] == h[0][1] / 100


def test_rebased_starts_at_100_on_common_month(ui_db):
    s = _cmp(ui_db, [1, 2, 3], mode="rebased")
    starts = {x["x"][0] for x in s}
    assert len(starts) == 1
    assert all(x["y"][0] == 100 for x in s)


def test_vs_index(analyzed_db):
    s = _cmp(analyzed_db, [10, 89], mode="index")
    assert all(x["y"][0] == pytest.approx(100) for x in s)
    conn = readonly_connect(analyzed_db)
    ex = {gid: conn.execute("SELECT excess_36m FROM series_metrics WHERE game_id = ? AND condition = 'loose'",
                            (gid,)).fetchone()[0] for gid in (10, 89)}
    conn.close()
    # the endpoint over the last 36 months matches the analysis' excess return
    for x in s:
        i = x["x"].index("2023-09-01")
        assert math.log(x["y"][-1] / x["y"][i]) == pytest.approx(ex[x["id"]], abs=1e-3)


def test_index_mode_needs_analysis(ui_db):
    assert _cmp(ui_db, [1], mode="index") == []


def test_page(client):
    r = client.get("/compare", params={"ids": "1,2", "mode": "rebased"})
    assert r.status_code == 200
    data = json.loads(re.search(r'id="compare-data">(.*?)</script>', r.text, re.S).group(1))
    assert [d["name"] for d in data] == ["Game 1", "Game 2"]
    assert 'href="/compare?ids=2' in r.text  # remove Game 1 link keeps the rest


def test_page_repeated_ids_and_cap(client):
    r = client.get("/compare?ids=1&ids=2&ids=3&ids=4&ids=5&ids=6&ids=7&ids=1")
    data = json.loads(re.search(r'id="compare-data">(.*?)</script>', r.text, re.S).group(1))
    assert [d["id"] for d in data] == [1, 2, 3, 4, 5, 6]
    assert client.get("/compare", params={"ids": "x"}).status_code == 422


def test_empty_page_and_suggest(client):
    assert "Pick up to 6 titles" in client.get("/compare").text
    r = client.get("/compare/suggest", params={"q": "Game 12", "ids": "1"})
    assert 'href="/compare?ids=1%2C12' in r.text or 'href="/compare?ids=1,12' in r.text


def test_entry_points(client):
    assert 'href="/compare?ids=5"' in client.get("/games/5").text
    assert 'action="/compare"' in client.get("/games").text


def test_color_slot_follows_title(client):
    # synth game 1 has no "new" history: games 2 and 3 must keep their chip colors (slots 2, 3), not shift up
    r = client.get("/compare", params={"ids": "1,2,3", "cond": "new"})
    data = json.loads(re.search(r'id="compare-data">(.*?)</script>', r.text, re.S).group(1))
    assert {d["id"]: d["slot"] for d in data} == {2: 2, 3: 3}
    assert "No new history for: Game 1" in r.text
