import sqlite3

import pytest

from pricecharter.ui.app import create_app, readonly_connect


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "games": 240}


def test_layout_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>pricecharter" in r.text
    assert 'href="/games"' in r.text


def test_connection_is_read_only(ui_db):
    conn = readonly_connect(ui_db)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("UPDATE games SET name = 'x'")
    conn.close()


def test_missing_db_fails_fast(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_app(tmp_path / "nope.db")


def test_serve_args():
    from pricecharter.cli import parse_args

    args = parse_args(["serve"])
    assert (args.host, args.http_port) == ("127.0.0.1", 8000)
    assert parse_args(["serve", "--http-port", "9000"]).http_port == 9000
