PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS games (
    id              INTEGER PRIMARY KEY,          -- PriceCharting ID
    console         TEXT NOT NULL,                -- PriceCharting slug, e.g. 'pal-nes', 'famicom'
    platform        TEXT,                         -- 'nes', 'ps2', ... (region-independent)
    region          TEXT,                         -- 'ntsc-u' | 'pal' | 'ntsc-j'
    slug            TEXT NOT NULL,
    name            TEXT NOT NULL,
    image_url       TEXT,
    genre           TEXT,
    release_date    TEXT,                         -- ISO date
    publisher       TEXT,
    developer       TEXT,
    model_number    TEXT,
    player_count    TEXT,
    upc             TEXT,
    asin            TEXT,
    epid            TEXT,
    list_rank       INTEGER,                      -- position in highest-price sort
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_list_at    TEXT,
    last_detail_at  TEXT,
    UNIQUE (console, slug)
);
CREATE INDEX IF NOT EXISTS games_detail_due ON games (console, last_detail_at);

-- Current prices as seen at crawl time (one row per game/day/source)
CREATE TABLE IF NOT EXISTS price_snapshots (
    game_id      INTEGER NOT NULL REFERENCES games(id),
    captured_on  TEXT NOT NULL,                   -- ISO date
    source       TEXT NOT NULL CHECK (source IN ('list', 'detail')),
    loose_cents  INTEGER,
    cib_cents    INTEGER,
    new_cents    INTEGER,
    PRIMARY KEY (game_id, captured_on, source)
);

-- Monthly "All" timeframe chart series
CREATE TABLE IF NOT EXISTS price_history (
    game_id      INTEGER NOT NULL REFERENCES games(id),
    condition    TEXT NOT NULL CHECK (condition IN ('loose', 'cib', 'new')),
    month        TEXT NOT NULL,                   -- YYYY-MM-01
    price_cents  INTEGER NOT NULL,
    PRIMARY KEY (game_id, condition, month)
);

-- Recent completed sales per condition
CREATE TABLE IF NOT EXISTS sales (
    game_id      INTEGER NOT NULL REFERENCES games(id),
    condition    TEXT NOT NULL CHECK (condition IN ('loose', 'cib', 'new')),
    sale_id      TEXT NOT NULL,                   -- e.g. 'ebay-405459355284', or hash for private sales
    sale_date    TEXT NOT NULL,
    title        TEXT,
    price_cents  INTEGER,
    source       TEXT,                            -- ebay, goldin, heritage, private, ...
    url          TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (game_id, condition, sale_id)
);
CREATE INDEX IF NOT EXISTS sales_by_date ON sales (game_id, condition, sale_date);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id           INTEGER PRIMARY KEY,
    stage        TEXT NOT NULL,                   -- 'list' | 'details'
    console      TEXT NOT NULL,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT,
    ok           INTEGER NOT NULL DEFAULT 0,
    failed       INTEGER NOT NULL DEFAULT 0,
    error        TEXT
);
