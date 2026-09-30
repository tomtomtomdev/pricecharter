import pytest

from pricecharter import db
from pricecharter.analysis.report import render_report
from pricecharter.analysis.run import analyze, persist
from pricecharter.analysis.stored import load_stored
from tests.analysis import synth


@pytest.fixture(scope="module")
def persisted(tmp_path_factory):
    conn = synth.build(tmp_path_factory.mktemp("st") / "s.db", games_per_console=60)
    res = analyze(conn)
    persist(conn, res)
    yield conn, res
    conn.close()


def test_report_from_stored_tables_matches_in_memory(persisted, tmp_path):
    conn, res = persisted
    stored = load_stored(conn)
    assert stored.params["asof"] == res.params["asof"]
    live = render_report(res, tmp_path / "live.html").read_text()
    again = render_report(stored, tmp_path / "stored.html").read_text()
    assert again == live


def test_model_summary_types_survive(persisted):
    conn, res = persisted
    m = load_stored(conn).model_summary
    assert m.keys() == res.model_summary.keys()
    assert type(m["signal"]) is bool and m["signal"] == res.model_summary["signal"]


def test_none_before_first_analysis(tmp_path):
    conn = db.connect(tmp_path / "empty.db")
    assert load_stored(conn) is None
    conn.close()
