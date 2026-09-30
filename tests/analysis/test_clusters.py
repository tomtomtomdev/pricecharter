import numpy as np
import pandas as pd
import pytest

from pricecharter.analysis.clusters import cluster_curves, curve_matrix, name_shape, profile_clusters
from pricecharter.analysis.factors import build_factors
from pricecharter.analysis.index import console_index
from pricecharter.analysis.label import label_rising
from pricecharter.analysis.loader import load_games, load_history, load_sales
from pricecharter.analysis.metrics import series_metrics

T = np.linspace(0, 1, 24)


@pytest.mark.parametrize("curve, name", [
    (0.0 * T, "flat"),
    (0.8 * T, "steady climber"),
    (np.where(T < 0.66, 0.0, (T - 0.66) * 3), "late surge"),
    (np.exp(-((T - 0.45) ** 2) / 0.01), "spike & fade"),
    (-0.6 * T, "decliner"),
])
def test_name_shape(curve, name):
    assert name_shape(curve) == name


def test_curve_matrix_resamples_and_anchors():
    months = pd.date_range("2020-01-01", periods=48, freq="MS")
    rows = [(g, "nes", "loose", m, float(np.exp(7 + 0.01 * g * i))) for g in (1, 2, 3) for i, m in enumerate(months)]
    rows += [(9, "nes", "loose", m, 100.0) for m in months[:10]]  # too short
    h = pd.DataFrame(rows, columns=["game_id", "console", "condition", "month", "price_cents"])
    idx = console_index(h, min_games=99)  # blank index -> curves are raw log price
    X = curve_matrix(h, idx, points=12, horizon=36, min_months=24)
    assert X.shape == (3, 12)
    assert list(X.index.get_level_values("game_id")) == [1, 2, 3]
    assert np.allclose(X.iloc[:, 0], 0)                       # anchored at start
    assert X.loc[(3, "loose")].iloc[-1] == pytest.approx(0.03 * 36)


def test_cluster_recovers_planted_shapes():
    rng = np.random.default_rng(0)
    shapes = {"flat": 0 * T, "steady climber": 0.8 * T, "late surge": np.where(T < 0.66, 0, (T - 0.66) * 3),
              "decliner": -0.6 * T}
    rows, truth = [], []
    for name, base in shapes.items():
        for _ in range(40):
            rows.append(base + rng.normal(0, 0.03, len(T)))
            truth.append(name)
    X = pd.DataFrame(rows, index=pd.MultiIndex.from_arrays([range(len(rows)), ["loose"] * len(rows)],
                                                           names=["game_id", "condition"]))
    assign, summary = cluster_curves(X, k=4)
    assign["truth"] = truth
    purity = assign.groupby("cluster")["truth"].agg(lambda s: s.value_counts().iloc[0] / len(s))
    assert (purity > 0.9).all()
    assert set(summary["shape"]) == set(shapes)


def test_profile_on_synth(synth_db):
    h = load_history(synth_db)
    idx = console_index(h)
    f = build_factors(label_rising(series_metrics(h, idx)), load_games(synth_db), h, load_sales(synth_db))
    assign, summary = cluster_curves(curve_matrix(h, idx), k=4)
    prof = profile_clusters(assign, f, ["genre", "publisher"], min_support=10)
    best = summary.sort_values("end_value").iloc[-1]["cluster"]
    top = prof[prof["cluster"] == best]
    assert "genre=RPG" in (top["factor"] + "=" + top["value"]).tolist()


def test_duplicate_shapes_named_by_strength():
    from pricecharter.analysis.clusters import _names

    names = _names(np.array([0.3 * T, 1.2 * T, 0.7 * T, -0.6 * T]))
    assert names == {0: "mild steady climber", 1: "strong steady climber", 2: "moderate steady climber",
                     3: "decliner"}
