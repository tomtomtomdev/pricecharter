import numpy as np
import pandas as pd

from pricecharter.analysis.index import console_index
from pricecharter.analysis.label import label_rising
from pricecharter.analysis.loader import load_games, load_history
from pricecharter.analysis.metrics import series_metrics


def _metrics(n, console="nes", condition="loose", n_months=40):
    return pd.DataFrame({
        "game_id": range(n), "console": console, "condition": condition,
        "excess_36m": np.linspace(-1, 1, n), "n_months": n_months,
    })


def test_top_fraction_is_rising():
    m = label_rising(_metrics(10), top=0.2)
    assert m["rising"].tolist() == [0] * 8 + [1] * 2


def test_groups_are_independent():
    m = label_rising(pd.concat([_metrics(10), _metrics(10, console="pal-nes").assign(excess_36m=5.0)]), top=0.2)
    assert m.groupby("console")["rising"].sum().to_dict() == {"nes": 2, "pal-nes": 10}  # ties at threshold


def test_ineligible_and_small_groups_are_nan():
    m = _metrics(12)
    m.loc[0, "n_months"] = 10          # too short
    m.loc[1, "excess_36m"] = np.nan    # no window
    out = label_rising(pd.concat([m, _metrics(5, console="famicom")]), min_group=10)
    assert np.isnan(out.loc[(out["console"] == "nes") & (out["game_id"].isin([0, 1])), "rising"]).all()
    assert out.loc[out["console"] == "famicom", "rising"].isna().all()
    assert out.loc[(out["console"] == "nes"), "rising"].notna().sum() == 10


def test_window_parameter():
    m = _metrics(10).rename(columns={"excess_36m": "excess_12m"})
    assert label_rising(m, window=12)["rising"].sum() == 2


def test_synthetic_rpg_overrepresented(synth_db):
    h = load_history(synth_db)
    m = label_rising(series_metrics(h, console_index(h)))
    m["genre"] = m["game_id"].map(load_games(synth_db)["genre"])
    lab = m.dropna(subset=["rising"])
    base = lab["rising"].mean()
    assert abs(base - 0.2) < 0.03
    assert lab.loc[lab["genre"] == "RPG", "rising"].mean() > 2 * base
