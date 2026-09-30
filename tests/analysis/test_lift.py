import pandas as pd
import pytest

from pricecharter.analysis.factors import build_factors
from pricecharter.analysis.index import console_index
from pricecharter.analysis.label import label_rising
from pricecharter.analysis.lift import factor_lift, wilson
from pricecharter.analysis.loader import load_games, load_history, load_sales
from pricecharter.analysis.metrics import series_metrics


def test_wilson_interval():
    lo, hi = wilson(20, 100)
    assert lo == pytest.approx(0.1334, abs=1e-3) and hi == pytest.approx(0.2888, abs=1e-3)
    assert wilson(0, 0) == (0.0, 1.0)


def _toy():
    rows = [("a", 1)] * 30 + [("a", 0)] * 10 + [("b", 1)] * 10 + [("b", 0)] * 50 + [("c", 1)] * 2
    df = pd.DataFrame(rows, columns=["genre", "rising"])
    df["condition"] = "loose"
    df["kw_limited"] = ["yes"] * 40 + ["no"] * 62
    return df


def test_lift_table():
    t = factor_lift(_toy(), ["genre"], min_support=5).set_index("value")
    base = 42 / 102
    assert t.loc["a", "n"] == 40 and t.loc["a", "risers"] == 30
    assert t.loc["a", "lift"] == pytest.approx(0.75 / base)
    assert t.loc["b", "lift"] == pytest.approx((10 / 60) / base)
    assert "c" not in t.index  # below min_support
    assert t.loc["a", "lift_lo"] > 1 > t.loc["b", "lift_hi"]
    assert list(t.index) == ["a", "b"]  # sorted by lift


def test_keyword_no_values_skipped_and_unlabeled_ignored():
    df = _toy()
    df.loc[0, "rising"] = float("nan")
    t = factor_lift(df, ["kw_limited"], min_support=5)
    assert t["value"].tolist() == ["yes"] and t["n"].iloc[0] == 39


def test_per_condition():
    df = pd.concat([_toy(), _toy().assign(condition="cib")])
    t = factor_lift(df, ["genre"], min_support=5)
    assert set(t["condition"]) == {"loose", "cib"}


def test_synthetic_planted_factors_surface(synth_db):
    h = load_history(synth_db)
    f = build_factors(label_rising(series_metrics(h, console_index(h))), load_games(synth_db), h, load_sales(synth_db))
    t = factor_lift(f, ["genre", "publisher"], min_support=20)
    loose = t[t["condition"] == "loose"].set_index(["factor", "value"])
    assert loose.loc[("genre", "RPG"), "lift_lo"] > 1.3
    assert loose.loc[("publisher", "SmallCo"), "lift"] > 1.2
    assert loose.loc[("genre", "Sports"), "lift"] < 1
