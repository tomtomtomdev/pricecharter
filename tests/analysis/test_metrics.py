import numpy as np
import pandas as pd
import pytest

from pricecharter.analysis.index import console_index
from pricecharter.analysis.loader import load_games, load_history
from pricecharter.analysis.metrics import series_metrics

MONTHS = pd.date_range("2020-01-01", periods=48, freq="MS")


def _hist(series: dict[int, np.ndarray], condition="loose", console="nes"):
    rows = [
        (gid, console, condition, m, float(np.exp(lp)))
        for gid, logp in series.items()
        for m, lp in zip(MONTHS, logp, strict=True)
        if not np.isnan(lp)
    ]
    return pd.DataFrame(rows, columns=["game_id", "console", "condition", "month", "price_cents"])


@pytest.fixture
def toy():
    k = np.arange(48)
    flat = np.log(1000) + 0.0 * k
    riser = np.log(1000) + 0.02 * k              # +2%/month
    spiky = np.log(1000) + np.where(k == 30, 1.0, 0.0)  # one-month spike then back
    others = {10 + i: np.log(1000) + 0.005 * k for i in range(5)}  # market +0.5%/month
    h = _hist({1: flat, 2: riser, 3: spiky, **others})
    return h, console_index(h, min_games=3)


def test_returns_and_excess(toy):
    h, idx = toy
    m = series_metrics(h, idx).set_index("game_id")
    assert m.loc[2, "ret_36m"] == pytest.approx(0.72)
    assert m.loc[2, "ret_12m"] == pytest.approx(0.24)
    assert m.loc[2, "excess_36m"] == pytest.approx(0.72 - 36 * 0.005, abs=1e-9)
    assert m.loc[1, "excess_36m"] == pytest.approx(-0.18, abs=1e-9)
    assert np.isnan(m.loc[2, "ret_60m"])  # history is only 48 months
    assert m.loc[2, "ret_all"] == pytest.approx(0.94)


def test_slope_vol_drawdown_jump(toy):
    h, idx = toy
    m = series_metrics(h, idx).set_index("game_id")
    assert m.loc[2, "slope_36m"] == pytest.approx(0.24)  # log-units per year
    assert m.loc[2, "vol_36m"] == pytest.approx(0.0, abs=1e-9)
    assert m.loc[3, "max_drawdown"] == pytest.approx(np.exp(-1) - 1)
    assert m.loc[3, "jump_month"] == MONTHS[30]
    assert m.loc[3, "jump_size"] == pytest.approx(1.0)
    assert m.loc[2, "obs_36m"] == 37 and m.loc[2, "n_months"] == 48


def test_gap_tolerance():
    k = np.arange(48).astype(float)
    logp = np.log(1000) + 0.01 * k
    logp[47 - 36] = np.nan  # start month missing -> uses previous month (within 2)
    h = _hist({1: logp, **{10 + i: np.log(1000) + 0 * k for i in range(3)}})
    m = series_metrics(h, console_index(h, min_games=2)).set_index("game_id")
    assert m.loc[1, "ret_36m"] == pytest.approx(0.37)


def test_asof(toy):
    h, idx = toy
    m = series_metrics(h, idx, asof=MONTHS[23]).set_index("game_id")
    assert m.loc[2, "ret_12m"] == pytest.approx(0.24)
    assert np.isnan(m.loc[2, "ret_36m"])


def test_synthetic_rpg_outperforms(synth_db):
    h = load_history(synth_db)
    m = series_metrics(h, console_index(h))
    g = load_games(synth_db)
    m["genre"] = m["game_id"].map(g["genre"])
    loose = m[m["condition"] == "loose"]
    by = loose.groupby("genre")["excess_36m"].mean()
    assert by["RPG"] > by.drop("RPG").max() + 0.2
