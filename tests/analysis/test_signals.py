import numpy as np
import pandas as pd
import pytest

from pricecharter.analysis.index import console_index
from pricecharter.analysis.loader import load_history
from pricecharter.analysis.signals import SIGNALS, compare, pre_breakout_signals, pre_features

MONTHS = pd.date_range("2012-01-01", periods=120, freq="MS")


def _planted(n=150, seed=1):
    """Loose jumps +60% at a random month; CIB/Loose ratio widens during the 12 months before."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n):
        jump = int(rng.integers(30, 100))
        loose = np.log(2000) + np.cumsum(rng.normal(0, 0.01, 120))
        loose[jump:] += 0.6
        cib = loose + np.log(2) + np.clip((np.arange(120) - (jump - 12)) / 12, 0, 1) * 0.4
        for i, m in enumerate(MONTHS):
            rows.append((g, "nes", "loose", m, float(np.exp(loose[i]))))
            rows.append((g, "nes", "cib", m, float(np.exp(cib[i]))))
    return pd.DataFrame(rows, columns=["game_id", "console", "condition", "month", "price_cents"])


def test_pre_features_have_no_lookahead():
    h = _planted(20)
    idx = console_index(h, min_games=3)
    cut = MONTHS[60]
    a = pre_features(h, idx)
    changed = h.copy()
    changed.loc[changed["month"] > cut, "price_cents"] *= 3
    b = pre_features(changed, console_index(changed, min_games=3))
    cols = [c for c in SIGNALS if c in a]
    at_cut = lambda f: f[f["month"] == cut].set_index(["game_id", "condition"])[cols].sort_index()  # noqa: E731
    pd.testing.assert_frame_equal(at_cut(a), at_cut(b))


def test_planted_cib_gap_signal_is_found():
    h = _planted()
    out = pre_breakout_signals(h, console_index(h, min_games=3), conditions=["loose"])
    r = out.set_index("signal").loc["cib_loose_change_12m"]
    assert r["cohens_d"] > 0.8 and r["p_value"] < 1e-6
    assert r["n_breakout"] >= 100


def test_compare_statistics():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"x": np.r_[rng.normal(1, 1, 200), rng.normal(0, 1, 600)],
                       "breakout": np.r_[np.ones(200), np.zeros(600)].astype(bool)})
    r = compare(df, ["x"]).iloc[0]
    assert r["cohens_d"] == pytest.approx(1.0, abs=0.2)
    assert r["breakout_mean"] > r["control_mean"]


def test_runs_on_synth(synth_db):
    h = load_history(synth_db)
    out = pre_breakout_signals(h, console_index(h))
    assert set(out["signal"]) <= set(SIGNALS)
    assert out["n_breakout"].gt(0).all()
