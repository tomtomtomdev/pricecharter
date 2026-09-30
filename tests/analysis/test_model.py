import numpy as np
import pandas as pd
import pytest

from pricecharter.analysis.index import console_index
from pricecharter.analysis.loader import load_games, load_history
from pricecharter.analysis.model import build_samples, fit_model, split_by_time
from tests.analysis import synth


def test_build_samples_target_and_momentum():
    months = pd.date_range("2010-01-01", periods=120, freq="MS")
    k = np.arange(120)
    rows = [(1, "nes", "loose", m, float(np.exp(np.log(1000) + 0.02 * i))) for i, m in zip(k, months, strict=True)]
    rows += [(g, "nes", "loose", m, 1000.0) for g in (2, 3, 4) for m in months]
    h = pd.DataFrame(rows, columns=["game_id", "console", "condition", "month", "price_cents"])
    games = pd.DataFrame({
        "console": "nes", "platform": "nes", "region": "ntsc-u", "name": ["A", "B", "C", "D"],
        "genre": "RPG", "publisher": "X", "developer": None, "esrb": None,
        "release_date": pd.to_datetime("1990-01-01"),
    }, index=[1, 2, 3, 4])
    s = build_samples(h, console_index(h, min_games=2), games, window=36)
    r = s[(s["game_id"] == 1) & (s["t0"] == pd.Timestamp("2012-01-01"))].iloc[0]
    assert r["target"] == pytest.approx(0.72)        # index is flat (median of 4 = 0)
    assert r["momentum_12m"] == pytest.approx(0.24)
    assert r["log_price_t0"] == pytest.approx(np.log(1000) + 0.02 * 24)
    assert s["t0"].dt.month.eq(1).all()
    assert s["t0"].max() + pd.DateOffset(months=36) <= months[-1]


def test_split_has_no_overlap():
    t0s = pd.Series(pd.date_range("2010-01-01", "2023-01-01", freq="YS"))
    s = pd.DataFrame({"t0": t0s})
    train, test = split_by_time(s, window=36, test_periods=2)
    assert test["t0"].min() == pd.Timestamp("2022-01-01")
    assert train["t0"].max() + pd.DateOffset(months=36) <= test["t0"].min()


@pytest.fixture(scope="module")
def planted(tmp_path_factory):
    conn = synth.build(tmp_path_factory.mktemp("m") / "s.db")
    h = load_history(conn)
    yield h, console_index(h), load_games(conn)
    conn.close()


def test_model_finds_planted_signal(planted):
    h, idx, games = planted
    res = fit_model(build_samples(h, idx, games, window=36))
    assert res.summary["status"] == "ok"
    assert res.summary["signal"] is True
    assert res.summary["spearman"] > 0.2
    assert res.summary["r2"] > res.summary["r2_baseline"]
    top = res.importance.head(4)["feature"].tolist()
    assert "genre" in top


def test_model_reports_no_signal_on_noise(tmp_path):
    conn = synth.build(tmp_path / "n.db", signal=False)
    h = load_history(conn)
    res = fit_model(build_samples(h, console_index(h), load_games(conn), window=36))
    assert res.summary["signal"] is False
    assert abs(res.summary["spearman"]) < 0.15


def test_insufficient_data():
    res = fit_model(pd.DataFrame(columns=["t0", "target"]))
    assert res.summary["status"] == "insufficient data" and res.importance.empty


def test_constant_features_dropped(planted):
    h, idx, games = planted
    one = h[(h["condition"] == "cib") & (h["console"] == "pal-nes")]
    res = fit_model(build_samples(one, idx, games, window=36))
    assert res.summary["status"] == "ok"
    assert "condition" not in res.importance["feature"].tolist()
