"""Deterministic synthetic PriceCharting DB with planted rising factors.

Planted signal (extra monthly log-return from 2019-01 on, on top of a shared market drift):
  genre RPG            +1.5%
  publisher SmallCo    +1.0%
  late release (>=1993) +0.8%
  "Mario" in name      +0.5%
Everything else only follows the market + noise.
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from pricecharter import db

GENRES = ["RPG", "Action", "Sports", "Puzzle"]
PUBLISHERS = ["Nintendo", "Capcom", "Konami", "SmallCo"]
MONTHS = pd.date_range("2010-01-01", "2026-09-01", freq="MS")
SIGNAL_START = pd.Timestamp("2019-01-01")
CONSOLES = ["nes", "pal-nes"]


def planted_boost(genre: str, publisher: str, year: int, name: str) -> float:
    return (
        0.015 * (genre == "RPG")
        + 0.010 * (publisher == "SmallCo")
        + 0.008 * (year >= 1993)
        + 0.005 * ("Mario" in name)
    )


def build(path: Path, games_per_console: int = 120, seed: int = 7) -> sqlite3.Connection:
    rng = np.random.default_rng(seed)
    conn = db.connect(path)
    market = np.cumsum(rng.normal(0.003, 0.01, len(MONTHS)))
    gid = 0
    for console in CONSOLES:
        for i in range(games_per_console):
            gid += 1
            genre = GENRES[rng.integers(len(GENRES))]
            publisher = PUBLISHERS[rng.integers(len(PUBLISHERS))]
            year = int(rng.integers(1985, 1995))
            name = f"{'Super Mario ' if rng.random() < 0.15 else ''}Game {gid}"
            db.upsert_list_game(
                conn,
                {"id": gid, "console": console, "slug": f"game-{gid}", "name": name, "image_url": None},
                i + 1,
                "2026-09-30",
            )
            conn.execute(
                "UPDATE games SET genre = ?, publisher = ?, release_date = ?, last_detail_at = datetime('now')"
                " WHERE id = ?",
                (genre, publisher, f"{year}-{rng.integers(1, 13):02d}-01", gid),
            )
            boost = planted_boost(genre, publisher, year, name)
            start = int(rng.integers(0, 24))  # series begin at different months
            base = rng.normal(np.log(2000), 0.8)
            rows = []
            for cond, mult, coverage in (("loose", 1.0, 1.0), ("cib", 2.2, 0.9), ("new", 5.0, 0.6)):
                if rng.random() > coverage:
                    continue
                noise = np.cumsum(rng.normal(0, 0.02, len(MONTHS)))
                extra = np.where(MONTHS >= SIGNAL_START, boost, 0.0).cumsum()
                logp = base + np.log(mult) + market + noise + extra
                for m, lp in list(zip(MONTHS, logp, strict=True))[start:]:
                    rows.append((gid, cond, m.date().isoformat(), int(round(np.exp(lp)))))
            conn.executemany(
                "INSERT INTO price_history (game_id, condition, month, price_cents) VALUES (?, ?, ?, ?)", rows
            )
            for k in range(int(rng.integers(0, 12))):
                conn.execute(
                    "INSERT INTO sales (game_id, condition, sale_id, sale_date, price_cents, source)"
                    " VALUES (?, 'loose', ?, ?, 1000, 'ebay')",
                    (gid, f"s{gid}-{k}", f"2026-{rng.integers(1, 10):02d}-15"),
                )
    conn.commit()
    return conn
