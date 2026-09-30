import json
import re

import pytest

from pricecharter.analysis.report import render_report
from pricecharter.analysis.run import analyze
from tests.analysis import synth


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    conn = synth.build(tmp_path_factory.mktemp("r") / "s.db", games_per_console=60)
    yield analyze(conn)
    conn.close()


def test_report_sections(result, tmp_path):
    path = render_report(result, tmp_path / "out" / "report.html")
    html = path.read_text()
    for heading in ("Console price index", "Top rising factors", "Rising patterns", "Caveats"):
        assert heading in html
    assert "genre=RPG" in html
    assert "cdnjs.cloudflare.com/ajax/libs/plotly.js" in html
    assert "prefers-color-scheme: dark" in html


def test_pattern_examples_use_titles(result, tmp_path):
    html = render_report(result, tmp_path / "r.html").read_text()
    assert re.search(r"Game \d+", html)


def test_chart_data_is_valid_json(result, tmp_path):
    html = render_report(result, tmp_path / "r.html").read_text()
    blob = re.search(r'<script id="chart-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    data = json.loads(blob)
    assert set(data["index"]) == {"loose", "cib", "new"}
    first = data["index"]["loose"][0]
    assert {"name", "x", "y"} <= set(first) and len(first["x"]) == len(first["y"]) > 100


def test_escapes_titles(result, tmp_path):
    result.games.loc[result.games.index[0], "name"] = "<script>alert(1)</script>"
    html = render_report(result, tmp_path / "r.html").read_text()
    assert "<script>alert(1)</script>" not in html


def test_cli_report_flags():
    from pricecharter.cli import parse_args

    assert parse_args(["analyze"]).report is None and not parse_args(["analyze"]).no_report
    assert parse_args(["analyze", "--no-report"]).no_report
