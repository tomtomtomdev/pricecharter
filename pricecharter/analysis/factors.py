"""Candidate rising factors per game x condition.

Categorical columns (strings) feed lift tables and pattern mining; numeric columns feed the model.
Price-based factors are measured at the *start* of the window so they aren't caused by the rise.
"""

import re

import numpy as np
import pandas as pd

FRANCHISES = {
    "mario": r"\bmario\b", "zelda": r"\bzelda\b", "pokemon": r"\bpok[eé]mon\b", "metroid": r"\bmetroid\b",
    "kirby": r"\bkirby\b", "donkey kong": r"\bdonkey kong\b", "mega man": r"\bmega ?man\b|\brockman\b",
    "castlevania": r"\bcastlevania\b|\bakumajo\b", "final fantasy": r"\bfinal fantasy\b",
    "dragon quest": r"\bdragon (quest|warrior)\b", "resident evil": r"\bresident evil\b|\bbiohazard\b",
    "sonic": r"\bsonic\b", "street fighter": r"\bstreet fighter\b", "fire emblem": r"\bfire emblem\b",
    "persona": r"\bpersona\b", "shin megami tensei": r"\bshin megami tensei\b|\bmegami\b",
    "metal gear": r"\bmetal gear\b", "kingdom hearts": r"\bkingdom hearts\b", "halo": r"\bhalo\b",
    "contra": r"\bcontra\b|\bprobotector\b", "ninja gaiden": r"\bninja gaiden\b",
    "earthbound": r"\bearthbound\b|\bmother\b",
    "star fox": r"\bstar ?fox\b", "animal crossing": r"\banimal crossing\b", "xenoblade": r"\bxeno(blade|saga|gears)\b",
    "tales of": r"\btales of\b", "suikoden": r"\bsuikoden\b", "silent hill": r"\bsilent hill\b",
    "monster hunter": r"\bmonster hunter\b", "harvest moon": r"\bharvest moon\b|\bstory of seasons\b",
    "atelier": r"\batelier\b", "disgaea": r"\bdisgaea\b", "pikmin": r"\bpikmin\b", "smash bros": r"\bsmash bros",
    "wario": r"\bwario", "yoshi": r"\byoshi", "crash": r"\bcrash bandicoot\b", "spyro": r"\bspyro\b",
}
KEYWORDS = {
    "limited": r"\blimited\b", "collector": r"\bcollector'?s?\b", "special_edition": r"\bspecial edition\b",
    "test_or_proto": r"\btest\b|\bprototype\b|\bdebug\b", "competition": r"\bcompetition\b|\bchampionship",
    "promo": r"\bpromo\b|\bnot for resale\b|\bnfr\b", "demo": r"\bdemo\b|\bkiosk\b",
    "budget_reprint": r"greatest hits|player'?s choice|\bplatinum\b|nintendo selects|\bclassics\b|\bbest\b",
    "bundle": r"\bbundle\b|\bcombo\b|\b\d ?in ?1\b",
}
TOP_N = 25
PRICE_BINS = [0, 2000, 10000, 50000, np.inf]
PRICE_LABELS = ["<$20", "$20-100", "$100-500", "$500+"]
RATIO_BINS = [0, 1.5, 3, np.inf]
RATIO_LABELS = ["<1.5x", "1.5-3x", "3x+"]
SALES_BINS = [-1, 0, 4, 14, np.inf]
SALES_LABELS = ["0", "1-4", "5-14", "15+"]

_FRANCHISE_RE = {k: re.compile(v, re.I) for k, v in FRANCHISES.items()}
_KEYWORD_RE = {k: re.compile(v, re.I) for k, v in KEYWORDS.items()}


def _cut(values: pd.Series, bins, labels, right: bool = True) -> pd.Series:
    """Bin into string labels; missing -> 'unknown'."""
    cat = pd.cut(values, bins, labels=labels, right=right)
    return cat.astype(object).where(cat.notna(), "unknown").astype(str)


def franchise(name: str) -> str:
    for key, rx in _FRANCHISE_RE.items():
        if rx.search(name or ""):
            return key
    return "none"


def keywords(name: str) -> dict[str, str]:
    return {f"kw_{k}": "yes" if rx.search(name or "") else "no" for k, rx in _KEYWORD_RE.items()}


def top_n(values: pd.Series, n: int = TOP_N) -> pd.Series:
    v = values.fillna("unknown")
    keep = v[v != "unknown"].value_counts().index[:n]
    return v.where(v.isin(keep) | (v == "unknown"), "other")


def lifecycle(games: pd.DataFrame) -> pd.Series:
    """Release position within its console's release span: 0 = first title, 1 = last."""
    rd = games["release_date"]
    lo = rd.groupby(games["console"]).transform("min")
    hi = rd.groupby(games["console"]).transform("max")
    span = (hi - lo).dt.days.replace(0, np.nan)
    return ((rd - lo).dt.days / span).clip(0, 1)


def _lifecycle_bucket(pos: pd.Series) -> pd.Series:
    return _cut(pos, [-0.01, 0.2, 0.8, 1.01], ["early", "mid", "late"])


def game_factors(games: pd.DataFrame) -> pd.DataFrame:
    """Condition-independent factors, one row per game id."""
    g = pd.DataFrame(index=games.index)
    g["region"] = games["region"].fillna("unknown")
    g["platform"] = games["platform"].fillna("unknown")
    g["genre"] = games["genre"].fillna("unknown")
    g["publisher"] = top_n(games["publisher"])
    g["developer"] = top_n(games["developer"])
    g["esrb"] = games["esrb"].fillna("unknown") if "esrb" in games else "unknown"
    year = games["release_date"].dt.year
    g["release_year"] = year
    g["release_era"] = (year // 5 * 5).map(lambda y: f"{int(y)}-{int(y) + 4}" if pd.notna(y) else "unknown")
    g["lifecycle_pos"] = lifecycle(games)
    g["lifecycle"] = _lifecycle_bucket(g["lifecycle_pos"])
    g["franchise"] = games["name"].map(franchise)
    kw = pd.DataFrame([keywords(n) for n in games["name"]], index=games.index)
    return g.join(kw)


def _price_at(history: pd.DataFrame, month: pd.Timestamp) -> pd.DataFrame:
    """Last observed price per game x condition within 2 months up to `month` (cents)."""
    lo = month - pd.DateOffset(months=2)
    h = history[(history["month"] <= month) & (history["month"] >= lo)]
    last = h.sort_values("month").groupby(["game_id", "condition"])["price_cents"].last()
    return last.unstack("condition")


def price_factors(history: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    """Price level and condition ratios at `start`, long format keyed by (game_id, condition)."""
    p = _price_at(history, start)
    for c in ("loose", "cib", "new"):
        if c not in p:
            p[c] = np.nan
    ratios = pd.DataFrame({"cib_loose_ratio": p["cib"] / p["loose"], "new_cib_ratio": p["new"] / p["cib"]})
    long = p[["loose", "cib", "new"]].stack().dropna().rename("start_cents").reset_index()
    long = long.merge(ratios, left_on="game_id", right_index=True, how="left")
    long["log_price_start"] = np.log(long["start_cents"])
    long["price_bucket"] = _cut(long["start_cents"], PRICE_BINS, PRICE_LABELS, right=False)
    for col in ("cib_loose_ratio", "new_cib_ratio"):
        long[col.replace("_ratio", "")] = _cut(long[col], RATIO_BINS, RATIO_LABELS, right=False)
    return long.drop(columns="start_cents")


def sales_factors(sales: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Sold listings in the 12 months up to `asof` per game x condition (recent-activity proxy)."""
    s = sales[(sales["sale_date"] <= asof) & (sales["sale_date"] > asof - pd.DateOffset(months=12))]
    n = s.groupby(["game_id", "condition"]).size().rename("sales_12m").reset_index()
    return n


def build_factors(
    labeled: pd.DataFrame, games: pd.DataFrame, history: pd.DataFrame, sales: pd.DataFrame, window: int = 36
) -> pd.DataFrame:
    asof = labeled["asof"].iloc[0]
    start = asof - pd.DateOffset(months=window)
    out = labeled[["game_id", "console", "condition", "rising", f"excess_{window}m"]].copy()
    out = out.merge(game_factors(games), left_on="game_id", right_index=True, how="left")
    out = out.merge(price_factors(history, start), on=["game_id", "condition"], how="left")
    out = out.merge(sales_factors(sales, asof), on=["game_id", "condition"], how="left")
    out["sales_12m"] = out["sales_12m"].fillna(0).astype(int)
    out["liquidity"] = _cut(out["sales_12m"], SALES_BINS, SALES_LABELS)
    out["age_years"] = (start - out["game_id"].map(games["release_date"])).dt.days / 365.25
    for col in ("price_bucket", "cib_loose", "new_cib"):
        out[col] = out[col].fillna("unknown")
    return out


CATEGORICAL = [
    "region", "platform", "genre", "publisher", "developer", "esrb", "release_era", "lifecycle", "franchise",
    *[f"kw_{k}" for k in KEYWORDS], "price_bucket", "cib_loose", "new_cib", "liquidity",
]
NUMERIC = ["release_year", "lifecycle_pos", "log_price_start", "cib_loose_ratio", "new_cib_ratio", "sales_12m",
           "age_years"]
