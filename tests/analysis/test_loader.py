import pandas as pd

from pricecharter.analysis.loader import load_games, load_history, to_panel
from tests.analysis import synth


def test_load_history_types_and_filters(synth_db):
    h = load_history(synth_db)
    assert list(h.columns) == ["game_id", "console", "condition", "month", "price_cents"]
    assert pd.api.types.is_datetime64_any_dtype(h["month"])
    assert set(h["condition"]) == {"loose", "cib", "new"}
    assert set(h["console"]) == set(synth.CONSOLES)

    only = load_history(synth_db, consoles=["pal-nes"], conditions=["cib"])
    assert set(only["console"]) == {"pal-nes"} and set(only["condition"]) == {"cib"}
    assert 0 < len(only) < len(h)


def test_load_games(synth_db):
    g = load_games(synth_db)
    assert g.index.name == "id"
    assert {"console", "platform", "region", "name", "genre", "publisher", "release_date"} <= set(g.columns)
    assert len(g) == 240
    assert pd.api.types.is_datetime64_any_dtype(g["release_date"])


def test_to_panel_is_monthly_log_price(synth_db):
    h = load_history(synth_db, conditions=["loose"])
    panel = to_panel(h)
    assert panel.index.freqstr == "MS"
    assert panel.index[0] == synth.MONTHS[0] and panel.index[-1] == synth.MONTHS[-1]
    assert panel.shape[1] == h["game_id"].nunique()
    gid = h["game_id"].iloc[0]
    first = h[h["game_id"] == gid].iloc[0]
    assert abs(panel.loc[first["month"], gid] - __import__("math").log(first["price_cents"])) < 1e-9
