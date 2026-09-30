import numpy as np
import pandas as pd
import pytest

from pricecharter.analysis.run import analyze
from pricecharter.analysis.watchlist import match_patterns, watchlist
from tests.analysis import synth


def test_match_patterns_scores_by_log_lower_lift():
    f = pd.DataFrame({
        "game_id": [1, 2, 3], "condition": "loose",
        "genre": ["RPG", "RPG", "Action"], "region": ["pal", "ntsc-u", "pal"],
    })
    p = pd.DataFrame({
        "condition": ["loose", "loose", "cib"],
        "items": ["genre=RPG & region=pal", "genre=RPG", "genre=Action"],
        "lift_lo": [3.0, 1.5, 9.0],
    })
    score, matched = match_patterns(f, p)
    assert score.tolist() == pytest.approx([np.log(3) + np.log(1.5), np.log(1.5), 0.0])
    assert matched[0] == ["genre=RPG & region=pal", "genre=RPG"] and matched[2] == []


@pytest.fixture(scope="module")
def res(tmp_path_factory):
    conn = synth.build(tmp_path_factory.mktemp("w") / "s.db")
    yield analyze(conn)
    conn.close()


def test_watchlist_prefers_planted_traits(res):
    w = watchlist(res, top=30)
    assert set(w["condition"]) == {"loose", "cib", "new"}
    loose = w[w["condition"] == "loose"]
    assert len(loose) == 30
    assert loose["score"].is_monotonic_decreasing
    planted = (loose["genre"] == "RPG") | (loose["publisher"] == "SmallCo")
    assert planted.mean() > 0.8
    assert {"name", "console", "price_cents", "pattern_score", "model_pred", "matched", "already_rising"} <= set(w)


def test_model_prediction_used_when_it_has_signal(res):
    assert res.model_summary["signal"]
    w = watchlist(res, top=10)
    assert w["model_pred"].notna().all()


def test_watchlist_without_model(tmp_path):
    conn = synth.build(tmp_path / "s.db", games_per_console=60)
    w = watchlist(analyze(conn, model=False), top=5)
    assert w["model_pred"].isna().all() and len(w) > 0


def test_titles_without_evidence_are_left_out(res):
    from dataclasses import replace

    bare = replace(res, patterns=res.patterns.iloc[0:0], model_summary={})
    assert watchlist(bare).empty
