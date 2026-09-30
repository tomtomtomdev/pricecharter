"""Curve shapes: cluster each title's recent excess-price path and describe who ends up in each shape."""

import json

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from threadpoolctl import threadpool_limits

from .lift import factor_lift
from .loader import to_panel

POINTS = 24
HORIZON = 60
MIN_MONTHS = 36


def curve_matrix(
    history: pd.DataFrame, index: pd.DataFrame, points: int = POINTS, horizon: int = HORIZON,
    min_months: int = MIN_MONTHS,
) -> pd.DataFrame:
    """Rows (game_id, condition); columns 0..points-1: excess log price over the last `horizon`
    months, linearly resampled and anchored so every curve starts at 0."""
    asof = history["month"].max()
    start = asof - pd.DateOffset(months=horizon)
    grid = np.linspace(0, 1, points)
    rows, keys = [], []
    for (console, cond), hist in history.groupby(["console", "condition"]):
        panel = to_panel(hist).loc[start:asof]
        lvl = index[(index["console"] == console) & (index["condition"] == cond)].set_index("month")["level"]
        excess = panel.sub(lvl.reindex(panel.index).ffill().fillna(0), axis=0)
        t = (panel.index - panel.index[0]).days.to_numpy(dtype=float)
        t = t / t[-1] if t[-1] else t
        for gid in excess.columns:
            y = excess[gid].to_numpy()
            ok = ~np.isnan(y)
            if ok.sum() < min_months:
                continue
            curve = np.interp(grid, t[ok], y[ok])
            rows.append(curve - curve[0])
            keys.append((gid, cond))
    idx = pd.MultiIndex.from_tuples(keys, names=["game_id", "condition"])
    return pd.DataFrame(rows, index=idx).sort_index()


def name_shape(c: np.ndarray) -> str:
    c = np.asarray(c, dtype=float)
    total, peak_i = c[-1] - c[0], int(np.argmax(c))
    peak, span = c.max(), c.max() - c.min()
    if abs(total) < 0.1 and span < 0.2:
        return "flat"
    if 0.15 * len(c) <= peak_i <= 0.85 * len(c) and c[-1] < peak - 0.5 * (peak - c[0]) and peak - c[0] > 0.2:
        return "spike & fade"
    if total <= -0.1:
        return "decliner"
    two_thirds = c[int(len(c) * 2 / 3)]
    if total > 0 and (c[-1] - two_thirds) / total > 0.6:
        return "late surge"
    return "steady climber"


STRENGTH = ["strong", "moderate", "mild"]


def _names(centers: np.ndarray) -> dict[int, str]:
    """Shape name per centroid; when several share a shape, qualify by how far they end from 0."""
    base = {i: name_shape(c) for i, c in enumerate(centers)}
    names = {}
    for shape in set(base.values()):
        members = sorted((i for i in base if base[i] == shape), key=lambda i: -abs(centers[i][-1]))
        for rank, i in enumerate(members):
            if len(members) == 1:
                names[i] = shape
            else:
                names[i] = f"{STRENGTH[rank]} {shape}" if rank < len(STRENGTH) else f"{shape} #{rank + 1}"
    return names


def cluster_curves(curves: pd.DataFrame, k: int = 5, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(curves) < k:
        return (pd.DataFrame(columns=["game_id", "condition", "cluster", "shape"]),
                pd.DataFrame(columns=["cluster", "shape", "n", "share", "end_value", "centroid"]))
    with threadpool_limits(4):
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(curves.to_numpy())
    names = _names(km.cluster_centers_)
    assign = curves.index.to_frame(index=False)
    assign["cluster"] = km.labels_
    assign["shape"] = assign["cluster"].map(names)
    counts = assign["cluster"].value_counts()
    summary = pd.DataFrame({
        "cluster": range(k),
        "shape": [names[i] for i in range(k)],
        "n": [int(counts.get(i, 0)) for i in range(k)],
        "end_value": km.cluster_centers_[:, -1],
        "centroid": [json.dumps(np.round(c, 4).tolist()) for c in km.cluster_centers_],
    })
    summary["share"] = summary["n"] / summary["n"].sum()
    return assign, summary


def profile_clusters(assign: pd.DataFrame, factors: pd.DataFrame, columns: list[str], min_support: int = 20,
                     top: int = 5) -> pd.DataFrame:
    """Per cluster: factor values most over-represented in it (lift of membership vs overall)."""
    base = factors.drop(columns=["rising"]).merge(assign, on=["game_id", "condition"])
    out = []
    for cl in sorted(base["cluster"].unique()):
        df = base.assign(rising=(base["cluster"] == cl).astype(float), condition="all")
        lift = factor_lift(df, columns, min_support=min_support)
        lift = lift[lift["lift_lo"] > 1].head(top)
        out.append(lift.assign(cluster=cl))
    cols = ["cluster", "factor", "value", "n", "lift", "lift_lo", "lift_hi"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)
