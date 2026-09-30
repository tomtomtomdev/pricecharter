import numpy as np
import pandas as pd
import pytest

from pricecharter.analysis.factors import (
    CATEGORICAL,
    build_factors,
    franchise,
    game_factors,
    keywords,
    lifecycle,
    price_factors,
    top_n,
)
from pricecharter.analysis.index import console_index
from pricecharter.analysis.label import label_rising
from pricecharter.analysis.loader import load_games, load_history, load_sales
from pricecharter.analysis.metrics import series_metrics


@pytest.mark.parametrize("name, expected", [
    ("Super Mario Bros 3", "mario"),
    ("Legend of Zelda: Link's Awakening", "zelda"),
    ("Pokemon Emerald", "pokemon"),
    ("Mega Man X", "mega man"),
    ("Rockman 2", "mega man"),
    ("Dragon Warrior IV", "dragon quest"),
    ("Biohazard 2", "resident evil"),
    ("Tetris", "none"),
])
def test_franchise(name, expected):
    assert franchise(name) == expected


def test_keywords():
    kw = keywords("Nintendo World Championship Gold [Not for Resale] Collector's Edition")
    assert kw["kw_competition"] == kw["kw_promo"] == kw["kw_collector"] == "yes"
    assert kw["kw_budget_reprint"] == "no"
    assert keywords("Final Fantasy VII [Greatest Hits]")["kw_budget_reprint"] == "yes"


def test_top_n_groups_rare_values():
    s = pd.Series(["A"] * 5 + ["B"] * 3 + ["C"] + [None])
    assert top_n(s, 2).tolist() == ["A"] * 5 + ["B"] * 3 + ["other", "unknown"]


def test_lifecycle_position():
    g = pd.DataFrame({
        "console": ["nes"] * 3 + ["snes"],
        "release_date": pd.to_datetime(["1985-01-01", "1990-01-01", "1995-01-01", "1992-01-01"]),
    })
    pos = lifecycle(g)
    assert pos.iloc[:3].round(2).tolist() == [0.0, 0.5, 1.0]
    assert np.isnan(pos.iloc[3])  # single-title console has no span


def test_game_factors_buckets():
    g = pd.DataFrame({
        "console": ["nes"] * 3, "platform": ["nes"] * 3, "region": ["ntsc-u", "pal", None],
        "name": ["Zelda", "Tetris [Limited]", "X"], "genre": ["RPG", None, "Puzzle"],
        "publisher": ["Nintendo"] * 3, "developer": [None] * 3, "esrb": [None] * 3,
        "release_date": pd.to_datetime(["1986-02-21", "1989-06-01", "1994-12-01"]),
    }, index=[1, 2, 3])
    f = game_factors(g)
    assert f.loc[1, "franchise"] == "zelda" and f.loc[2, "kw_limited"] == "yes"
    assert f["lifecycle"].tolist() == ["early", "mid", "late"]
    assert f["release_era"].tolist() == ["1985-1989", "1985-1989", "1990-1994"]
    assert f.loc[3, "region"] == "unknown" and f.loc[2, "genre"] == "unknown"


def test_price_factors_at_start():
    h = pd.DataFrame({
        "game_id": [1, 1, 1, 2], "console": "nes", "condition": ["loose", "cib", "new", "loose"],
        "month": pd.to_datetime(["2023-01-01", "2022-12-01", "2022-06-01", "2023-01-01"]),
        "price_cents": [1500, 4000, 90000, 60000],
    })
    p = price_factors(h, pd.Timestamp("2023-01-01")).set_index(["game_id", "condition"])
    assert p.loc[(1, "loose"), "price_bucket"] == "<$20"
    assert p.loc[(1, "cib"), "price_bucket"] == "$20-100"
    assert (1, "new") not in p.index  # new price is older than the 2-month tolerance
    assert p.loc[(1, "loose"), "cib_loose"] == "1.5-3x"
    assert p.loc[(2, "loose"), "price_bucket"] == "$500+"
    assert p.loc[(2, "loose"), "cib_loose"] == "unknown"


def test_build_factors_on_synth(synth_db):
    h = load_history(synth_db)
    lab = label_rising(series_metrics(h, console_index(h)))
    f = build_factors(lab, load_games(synth_db), h, load_sales(synth_db))
    assert len(f) == len(lab)
    assert set(CATEGORICAL) <= set(f.columns)
    assert not f[CATEGORICAL].isna().any().any()
    assert set(f["region"]) == {"ntsc-u", "pal"}
    assert (f["age_years"] > 20).all()
    assert f["liquidity"].isin(["0", "1-4", "5-14", "15+"]).all()
