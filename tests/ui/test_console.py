import json
import re

from fastapi.testclient import TestClient

from pricecharter.ui import queries
from pricecharter.ui.app import create_app, readonly_connect


def _json(html, id_):
    return json.loads(re.search(rf'<script type="application/json" id="{id_}">(.*?)</script>', html, re.S).group(1))


def test_movers(analyzed_db):
    conn = readonly_connect(analyzed_db)
    up = queries.movers(conn, "nes", "loose", n=5)
    down = queries.movers(conn, "nes", "loose", n=5, rising=False)
    conn.close()
    assert len(up) == 5 and all(r["console"] == "nes" for r in up)
    ex = [r["excess_36m"] for r in up]
    assert ex == sorted(ex, reverse=True)
    assert [r["excess_36m"] for r in down] == sorted(r["excess_36m"] for r in down)
    assert down[0]["excess_36m"] < up[-1]["excess_36m"]


def test_console_index_series(analyzed_db):
    conn = readonly_connect(analyzed_db)
    s = queries.console_index_series(conn, "pal-nes")
    conn.close()
    assert [x["cond"] for x in s] == ["loose", "cib", "new"]
    assert s[0]["y"][0] == 0.0  # % since the index start


def test_console_page_with_analysis(analyzed_db):
    with TestClient(create_app(analyzed_db)) as c:
        r = c.get("/consoles/nes", params={"cond": "cib"})
    assert r.status_code == 200
    assert "<h1>nes</h1>" in r.text and "Biggest risers" in r.text and "Biggest fallers" in r.text
    assert _json(r.text, "index-series")[0]["cond"] == "loose"
    assert 'data-chart="index"' in r.text
    assert r.text.count('href="/games/') >= 20


def test_console_page_without_analysis(client):
    r = client.get("/consoles/pal-nes")
    assert r.status_code == 200
    assert "No analysis yet" in r.text and "120" in r.text
    assert 'href="/games?console=pal-nes"' in r.text


def test_console_404(client):
    assert client.get("/consoles/dreamcast").status_code == 404


def test_dashboard_links_consoles(client):
    assert 'href="/consoles/nes"' in client.get("/").text
