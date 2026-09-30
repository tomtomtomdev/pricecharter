import json
import re

from fastapi.testclient import TestClient

from pricecharter import db
from pricecharter.ui import queries
from pricecharter.ui.app import create_app, readonly_connect


def _chart_data(html):
    m = re.search(r'<script type="application/json" id="price-data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def test_game_queries(ui_db):
    conn = readonly_connect(ui_db)
    g = queries.game(conn, 1)
    assert g["name"] == "Game 1" and g["loose_cents"] > 0
    h = queries.history(conn, 1)
    assert set(h) <= {"loose", "cib", "new"} and "loose" in h
    months = [m for m, _ in h["loose"]]
    assert months == sorted(months) and months[-1] == "2026-09-01"
    sales = queries.sales(conn, 1)
    assert [s["sale_date"] for s in sales] == sorted((s["sale_date"] for s in sales), reverse=True)
    assert queries.game(conn, 99999) is None
    conn.close()


def test_game_page(client):
    r = client.get("/games/1")
    assert r.status_code == 200
    assert "<h1>Game 1</h1>" in r.text
    assert 'href="https://www.pricecharting.com/game/nes/game-1"' in r.text
    data = _chart_data(r.text)
    assert [s["cond"] for s in data] == [c for c in ("loose", "cib", "new") if c in {s["cond"] for s in data}]
    assert data[0]["x"][-1] == "2026-09-01"
    assert all(isinstance(v, float) for v in data[0]["y"])  # dollars, not cents
    assert 'id="price-chart"' in r.text and "/static/charts.js" in r.text
    assert "Monthly prices (table)" in r.text


def test_game_not_found(client):
    assert client.get("/games/99999").status_code == 404
    assert client.get("/games/abc").status_code == 422


def test_game_without_history_or_sales(tmp_path):
    conn = db.connect(tmp_path / "e.db")
    db.upsert_list_game(conn, {"id": 5, "console": "famicom", "slug": "x", "name": "<Zelda & co>",
                               "image_url": None, "loose_cents": 1234}, 1, "2026-09-01")
    conn.commit()
    conn.close()
    with TestClient(create_app(tmp_path / "e.db")) as c:
        r = c.get("/games/5")
    assert r.status_code == 200
    assert "&lt;Zelda &amp; co&gt;" in r.text  # escaped
    assert "No price history yet" in r.text and "No recorded sales" in r.text
    assert "$12.34" in r.text
