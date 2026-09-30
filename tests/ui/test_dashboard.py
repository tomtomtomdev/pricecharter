from fastapi.testclient import TestClient

from pricecharter import db
from pricecharter.ui import queries
from pricecharter.ui.app import create_app, readonly_connect


def _game(conn, gid, console, fetched_days_ago=None):
    g = {"id": gid, "console": console, "slug": f"g{gid}", "name": f"G{gid}", "image_url": None}
    db.upsert_list_game(conn, g, gid, "2026-09-01")
    if fetched_days_ago is not None:
        conn.execute("UPDATE games SET last_detail_at = datetime('now', ?) WHERE id = ?",
                     (f"-{fetched_days_ago} days", gid))


def _crafted(path):
    conn = db.connect(path)
    _game(conn, 1, "nes", fetched_days_ago=1)
    _game(conn, 2, "nes", fetched_days_ago=10)
    _game(conn, 3, "nes")
    _game(conn, 4, "pal-super-nintendo", fetched_days_ago=0)
    conn.execute("INSERT INTO price_history VALUES (1, 'loose', '2026-01-01', 500)")
    conn.execute("INSERT INTO price_history VALUES (1, 'cib', '2026-01-01', 900)")
    run = db.start_run(conn, "details", "nes")
    db.finish_run(conn, run, ok=2, failed=1, error="cloudflare timeout")
    conn.commit()
    conn.close()
    return path


def test_coverage_counts(tmp_path):
    conn = readonly_connect(_crafted(tmp_path / "c.db"))
    rows = {r["console"]: r for r in queries.coverage(conn, stale_days=7)}
    nes = rows["nes"]
    assert (nes["listed"], nes["fetched"], nes["stale"], nes["never"], nes["with_history"]) == (3, 2, 1, 1, 1)
    assert (nes["platform"], nes["region"]) == ("nes", "ntsc-u")
    assert rows["pal-super-nintendo"]["region"] == "pal"
    assert queries.last_analysis(conn) is None
    conn.close()


def test_dashboard_without_analysis(tmp_path):
    with TestClient(create_app(_crafted(tmp_path / "c.db"))) as c:
        r = c.get("/")
    assert r.status_code == 200
    assert "pal-super-nintendo" in r.text
    assert "cloudflare timeout" in r.text
    assert "No analysis yet" in r.text


def test_dashboard_stale_days_setting(tmp_path):
    with TestClient(create_app(_crafted(tmp_path / "c.db"), stale_days=30)) as c:
        assert c.app.state.stale_days == 30
        assert c.get("/").status_code == 200


def test_dashboard_with_analysis(analyzed_db):
    conn = readonly_connect(analyzed_db)
    last = queries.last_analysis(conn)
    conn.close()
    assert last["asof"] == "2026-09-01"
    with TestClient(create_app(analyzed_db)) as c:
        r = c.get("/")
    assert "No analysis yet" not in r.text
    assert "2026-09-01" in r.text
