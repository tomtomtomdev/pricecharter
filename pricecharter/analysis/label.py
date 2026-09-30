"""Rising = top `top` share of `window`-month excess return within console x condition."""

import numpy as np
import pandas as pd


def label_rising(
    metrics: pd.DataFrame, window: int = 36, top: float = 0.2, min_obs: int = 24, min_group: int = 10
) -> pd.DataFrame:
    col = f"excess_{window}m"
    out = metrics.copy()
    flat = out.reset_index(drop=True)  # positional: callers may pass duplicate index labels
    eligible = flat[col].notna() & (flat["n_months"] >= min_obs)
    values = flat[col].where(eligible)
    keys = [flat["console"], flat["condition"]]
    size = eligible.groupby(keys).transform("sum")
    threshold = values.groupby(keys).transform(lambda s: s.quantile(1 - top))
    rising = (values >= threshold).astype(float).where(eligible & (size >= min_group), np.nan)
    out["rising"] = rising.to_numpy()
    return out
