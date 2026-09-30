"""Does anything known at t0 predict the next `window` months of excess return?

Samples are (game, condition, t0) for every January t0 with a full target window. Features are
only what was known at t0. Train/test split is by time with no overlap between the train targets
and the test period, so the score is an honest out-of-sample check.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import r2_score
from threadpoolctl import threadpool_limits

from .factors import game_factors, price_factors
from .loader import to_panel

CATEGORICAL = ["condition", "region", "platform", "genre", "publisher", "esrb", "lifecycle", "franchise",
               "release_era", "kw_budget_reprint", "kw_limited", "kw_collector"]
NUMERIC = ["log_price_t0", "momentum_12m", "cib_loose_ratio", "age_years", "lifecycle_pos", "release_year"]
FEATURES = CATEGORICAL + NUMERIC
MIN_TRAIN, MIN_TEST = 200, 50
THREADS = 4  # all-core OpenMP oversubscribes on small data (10x slower on Apple silicon)
SIGNAL_SPEARMAN = 0.1
GAP = 2  # month gap tolerance, as in metrics


def build_samples(
    history: pd.DataFrame, index: pd.DataFrame, games: pd.DataFrame, window: int = 36
) -> pd.DataFrame:
    parts = []
    last = history["month"].max()
    for (console, cond), hist in history.groupby(["console", "condition"]):
        panel = to_panel(hist).ffill(limit=GAP)
        lvl = index[(index["console"] == console) & (index["condition"] == cond)].set_index("month")["level"]
        lvl = lvl.reindex(panel.index).ffill()
        for t0 in panel.index[panel.index.month == 1]:
            t1 = t0 + pd.DateOffset(months=window)
            if t1 > min(last, panel.index[-1]):
                break
            p0, p1 = panel.loc[t0], panel.loc[t1]
            ok = p0.notna() & p1.notna()
            if not ok.any():
                continue
            tm = t0 - pd.DateOffset(months=12)
            if tm >= panel.index[0]:
                momentum = (p0 - panel.loc[tm]) - (lvl[t0] - lvl[tm])
            else:
                momentum = pd.Series(np.nan, index=panel.columns)
            df = pd.DataFrame({
                "game_id": panel.columns[ok], "console": console, "condition": cond, "t0": t0,
                "log_price_t0": p0[ok].to_numpy(), "momentum_12m": momentum[ok].to_numpy(),
                "target": ((p1 - p0) - (lvl[t1] - lvl[t0]))[ok].to_numpy(),
            })
            parts.append(df)
    if not parts:
        return pd.DataFrame(columns=["game_id", "console", "condition", "t0", "target", *FEATURES])
    s = pd.concat(parts, ignore_index=True)
    ratios = []
    for t0 in s["t0"].unique():
        pf = price_factors(history, pd.Timestamp(t0))
        ratios.append(pf[["game_id"]].assign(t0=t0, cib_loose_ratio=pf["cib_loose_ratio"]).drop_duplicates("game_id"))
    s = s.merge(pd.concat(ratios), on=["game_id", "t0"], how="left")
    gf = game_factors(games)
    s = s.merge(gf, left_on="game_id", right_index=True, how="left")
    s["age_years"] = (s["t0"] - s["game_id"].map(games["release_date"])).dt.days / 365.25
    return s


def split_by_time(samples: pd.DataFrame, window: int, test_periods: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    t0s = sorted(samples["t0"].unique())
    test_start = pd.Timestamp(t0s[-test_periods]) if len(t0s) >= test_periods else pd.Timestamp(t0s[0])
    train_cut = test_start - pd.DateOffset(months=window)
    return samples[samples["t0"] <= train_cut], samples[samples["t0"] >= test_start]


def _matrix(df: pd.DataFrame) -> pd.DataFrame:
    X = df[FEATURES].copy()
    for c in CATEGORICAL:
        X[c] = X[c].fillna("unknown").astype(str).astype("category")
    for c in NUMERIC:
        X[c] = pd.to_numeric(X[c], errors="coerce").astype(float)
    return X


@dataclass
class ModelResult:
    summary: dict
    importance: pd.DataFrame
    model: HistGradientBoostingRegressor | None = None


def fit_model(samples: pd.DataFrame, window: int = 36, seed: int = 0) -> ModelResult:
    with threadpool_limits(THREADS):
        return _fit(samples, window, seed)


def _fit(samples: pd.DataFrame, window: int, seed: int) -> ModelResult:
    empty = pd.DataFrame(columns=["feature", "importance", "importance_std"])
    if samples.empty:
        return ModelResult({"status": "insufficient data", "signal": False}, empty)
    train, test = split_by_time(samples, window)
    if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
        return ModelResult({"status": "insufficient data", "signal": False,
                            "n_train": len(train), "n_test": len(test)}, empty)
    Xtr, Xte = _matrix(train), _matrix(test)
    used = [f for f in FEATURES if Xtr[f].nunique(dropna=True) > 1]  # constant columns break HistGB binning
    Xtr, Xte = Xtr[used], Xte[used]
    # align category levels so test values unseen in training map consistently
    for c in [c for c in CATEGORICAL if c in used]:
        cats = Xtr[c].cat.categories.union(Xte[c].cat.categories)
        Xtr[c] = Xtr[c].cat.set_categories(cats)
        Xte[c] = Xte[c].cat.set_categories(cats)
    model = HistGradientBoostingRegressor(
        categorical_features="from_dtype", max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
        min_samples_leaf=40, l2_regularization=1.0, random_state=seed,
    )
    model.fit(Xtr, train["target"])
    pred = model.predict(Xte)
    y = test["target"].to_numpy()
    rho = float(spearmanr(pred, y).statistic)
    r2 = float(r2_score(y, pred))
    r2_base = float(r2_score(y, np.full_like(y, train["target"].median())))
    # top-quintile precision within each condition: how often predicted top 20% really were top 20%
    t = test.assign(pred=pred)
    hits = []
    for _, g in t.groupby("condition"):
        if len(g) >= 25:
            top_pred = g["pred"] >= g["pred"].quantile(0.8)
            top_true = g["target"] >= g["target"].quantile(0.8)
            hits.append((top_pred & top_true).sum() / max(top_pred.sum(), 1))
    perm = permutation_importance(model, Xte, y, n_repeats=5, random_state=seed, scoring="r2")
    importance = pd.DataFrame({
        "feature": used, "importance": perm.importances_mean, "importance_std": perm.importances_std,
    }).sort_values("importance", ascending=False, ignore_index=True)
    summary = {
        "status": "ok", "n_train": len(train), "n_test": len(test),
        "train_t0": f"{train['t0'].min():%Y}-{train['t0'].max():%Y}",
        "test_t0": f"{test['t0'].min():%Y}-{test['t0'].max():%Y}",
        "spearman": rho, "r2": r2, "r2_baseline": r2_base,
        "top_quintile_precision": float(np.mean(hits)) if hits else None,
        "signal": bool(rho > SIGNAL_SPEARMAN and r2 > r2_base),
    }
    return ModelResult(summary, importance, model)
