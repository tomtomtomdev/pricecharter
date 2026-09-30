import numpy as np
import pandas as pd

from pricecharter.analysis.factors import build_factors
from pricecharter.analysis.index import console_index
from pricecharter.analysis.label import label_rising
from pricecharter.analysis.loader import load_games, load_history, load_sales
from pricecharter.analysis.metrics import series_metrics
from pricecharter.analysis.patterns import item_matrix, mine_patterns


def _toy(seed=0):
    rng = np.random.default_rng(seed)
    n = 2000
    df = pd.DataFrame({
        "game_id": range(n), "condition": "loose",
        "genre": rng.choice(["RPG", "Action"], n),
        "region": rng.choice(["pal", "ntsc-u"], n),
        "kw_limited": rng.choice(["yes", "no"], n, p=[0.1, 0.9]),
        "excess_36m": rng.normal(size=n),
    })
    both = (df["genre"] == "RPG") & (df["region"] == "pal")
    p = np.where(both, 0.6, 0.1)  # only the combination matters
    df["rising"] = (rng.random(n) < p).astype(float)
    return df


def test_item_matrix_skips_unknown_and_kw_no():
    df = pd.DataFrame({"genre": ["RPG", "unknown"], "kw_limited": ["yes", "no"]})
    X = item_matrix(df, ["genre", "kw_limited"])
    assert list(X.columns) == ["genre=RPG", "kw_limited=yes"]
    assert X.dtypes.eq(bool).all()


def test_finds_interaction_and_ranks_it_first():
    p = mine_patterns(_toy(), ["genre", "region", "kw_limited"], min_count=50, min_lift=1.2)
    top = p.iloc[0]
    assert top["items"] == "genre=RPG & region=pal"
    assert top["size"] == 2 and top["lift"] > 2
    assert top["n"] == top["n"]  # int count present
    assert set(p["condition"]) == {"loose"}


def test_redundant_supersets_pruned():
    p = mine_patterns(_toy(), ["genre", "region", "kw_limited"], min_count=20, min_lift=1.2, min_gain=0.1)
    # adding kw_limited to the real interaction doesn't add lift -> not reported
    assert not p["items"].str.contains("genre=RPG & kw_limited=yes & region=pal").any()


def test_no_two_values_of_same_factor():
    p = mine_patterns(_toy(), ["genre", "region"], min_count=10, min_lift=0.0)
    assert not p["items"].str.contains("genre=.*genre=").any()


def test_examples_are_top_rising_members():
    df = _toy()
    p = mine_patterns(df, ["genre", "region"], min_count=50, min_lift=1.2)
    ids = [int(x) for x in p.iloc[0]["example_ids"].split(",")]
    members = df.set_index("game_id").loc[ids]
    assert (members["rising"] == 1).all() and len(ids) <= 5
    assert members["excess_36m"].is_monotonic_decreasing


def test_synthetic_combo(synth_db):
    h = load_history(synth_db)
    f = build_factors(label_rising(series_metrics(h, console_index(h))), load_games(synth_db), h, load_sales(synth_db))
    p = mine_patterns(f, ["genre", "publisher", "lifecycle", "franchise"], min_count=10, min_lift=1.5)
    loose = p[p["condition"] == "loose"]
    assert loose["items"].str.contains("genre=RPG").any()
    assert loose["lift"].max() > 2.5
