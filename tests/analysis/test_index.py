import numpy as np
import pandas as pd

from pricecharter.analysis.index import console_index, monthly_returns
from pricecharter.analysis.loader import load_history


def test_monthly_returns_only_between_consecutive_observed_months():
    h = pd.DataFrame({
        "game_id": [1, 1, 1, 1],
        "console": ["nes"] * 4,
        "condition": ["loose"] * 4,
        "month": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-04-01", "2020-05-01"]),
        "price_cents": [100, 110, 121, 121],
    })
    r = monthly_returns(h)
    got = dict(zip(r["month"].dt.strftime("%Y-%m"), r["ret"].round(6), strict=True))
    # 2020-03 missing -> no return for 03 or 04
    assert got == {"2020-02": round(np.log(1.1), 6), "2020-05": 0.0}


def test_median_ignores_outliers():
    months = pd.date_range("2020-01-01", periods=3, freq="MS")
    rows = []
    for gid, growth in [(1, 0.01), (2, 0.01), (3, 0.01), (4, 0.01), (5, 0.9)]:
        for k, m in enumerate(months):
            rows.append((gid, "nes", "loose", m, 100 * np.exp(growth * k)))
    h = pd.DataFrame(rows, columns=["game_id", "console", "condition", "month", "price_cents"])
    idx = console_index(h, min_games=3)
    assert np.allclose(idx["ret"].dropna(), 0.01)
    assert list(idx["level"].round(4)) == [0.0, 0.01, 0.02]
    assert list(idx["n"]) == [0, 5, 5]


def test_min_games_blanks_thin_months():
    months = pd.date_range("2020-01-01", periods=2, freq="MS")
    h = pd.DataFrame(
        [(1, "nes", "loose", m, 100) for m in months],
        columns=["game_id", "console", "condition", "month", "price_cents"],
    )
    idx = console_index(h, min_games=5)
    assert idx["ret"].isna().all() and (idx["level"] == 0).all()


def test_recovers_synthetic_market(synth_db):
    idx = console_index(load_history(synth_db))
    assert set(idx["console"]) == {"nes", "pal-nes"} and set(idx["condition"]) == {"loose", "cib", "new"}
    before = idx[(idx["month"] < "2019-01-01") & idx["ret"].notna()]
    # shared drift is 0.3%/month; noise and the planted boosts are idiosyncratic
    assert 0.001 < before["ret"].median() < 0.006
