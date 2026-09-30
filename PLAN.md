# pricecharter — plan & progress

Crawl PriceCharting (NTSC-U, PAL, NTSC-J) into SQLite on weekends, then analyze the
monthly price charts to find what rising titles have in common.

## Tech stack

| Area | Choice | Why |
|---|---|---|
| Language / env | Python 3.13, `uv` | one lockfile, `./run.sh` bootstraps everything |
| Browser | Playwright **attached over CDP to real headed Chrome** | Cloudflare blocks curl and Playwright-launched Chrome |
| HTML parsing | BeautifulSoup (`html.parser`) | no native deps, offline-testable against fixtures |
| Storage | SQLite (stdlib `sqlite3`, WAL) | single file, zero ops, fast enough for ~100k titles |
| Scheduling | macOS `launchd` LaunchAgent | headed Chrome needs the logged-in GUI session; cron/cloud can't |
| Analysis | pandas + numpy, scipy | series math, stats |
| Patterns | own level-wise itemset counting on a pandas boolean matrix | mlxtend drags in matplotlib; ≤3-item rules are a few lines |
| Model | scikit-learn `HistGradientBoostingRegressor` + permutation importance, `KMeans` | no libomp/LightGBM native install; importance without SHAP |
| Report | Jinja2 + Plotly.js from CDN (single static HTML) | shareable file, interactive charts, no Python plotting dep |
| Web UI | FastAPI + Jinja2 + HTMX (CDN), uvicorn, served on 127.0.0.1 | server-rendered, no JS build; reuses report templates/Plotly |
| UI data access | stdlib `sqlite3`, read-only URI (`mode=ro`) per request | safe to browse while the weekend crawl writes (WAL) |
| Quality | pytest (TDD), ruff, GitHub Actions CI | every slice ends green |

## Slice workflow

Each slice: **write failing test → implement → `uv run pytest` green → tick it here → commit → push.**

## Progress

### Crawler

- [x] **S0 Foundation** — CDP Chrome + Cloudflare wait, 1s throttle with 429 backoff, list JSON crawl,
      detail crawl (Loose/CIB/New monthly "All" history, current prices, recent sales), SQLite schema,
      `run.sh`, 16 NTSC-U consoles, parser tests.
- [x] **S1 CI** — ruff config + GitHub Actions running ruff and pytest.
- [x] **S2 Regions** — 48-console registry (platform × NTSC-U/PAL/NTSC-J), `games.platform`/`games.region`
      with migration for existing DBs, CLI `--region`.
- [x] **S3 Crawl window** — `--until HH:MM` graceful stop (handles past-midnight), skip a console's list
      if crawled within `--list-fresh-hours`.
- [x] **S4 Weekend schedule** — launchd plist generator + `schedule.sh install|uninstall|status`;
      Sat & Sun 01:00 start, stops 23:00.
- [x] **S5 ESRB** — parse & store ESRB rating.

### Analysis (`pricecharter analyze`)

- [x] **A1 Loader** — analysis deps group, load `price_history` + `games` into pandas; synthetic test DB builder.
- [x] **A2 Console index** — median monthly log-return per console × condition.
- [x] **A3 Series metrics** — excess return (1y/3y/5y/all), log slope, volatility, max drawdown,
      biggest-jump month → `series_metrics`.
- [x] **A4 Rising label** — top 20% 3y excess return per console × condition, ≥24 months.
- [x] **A5 Factors** — region, platform, genre, publisher, release year, lifecycle position,
      franchise/keyword tokens, price bucket, CIB/Loose & New/CIB ratios, sales liquidity.
- [x] **A6 Factor lift** — rise rate vs baseline, lift, Wilson CI, min support → `factor_lift`.
- [x] **A7 Patterns** — frequent itemsets (≤3 factors) over discretized factors ⇒ rising rules (support, confidence, lift) → `patterns`.
- [x] **A8 CLI + persistence** — `pricecharter analyze` writes tables + `analysis_runs`.
- [x] **A9 Report** — HTML: console indices, top factors, top patterns with example titles.
- [x] **A10 Model** — time-split HistGB on excess return, baseline comparison, permutation importance → `model_importance`.
- [x] **A11 Curve shapes** — KMeans on normalized curves, profile clusters by factors → `curve_clusters`.
- [x] **A12 Pre-breakout signals** — what changed 6–12 months before the biggest jumps.
- [x] **A13 Watchlist** — current titles best matching rising patterns, in the report.

### Web UI (`pricecharter serve`)

Local browser over the crawled DB + latest analysis tables. Every page works before `analyze` has ever run
(analysis sections just say so). Tests use `fastapi.testclient` against the synthetic DB in `tests/analysis/synth.py`.

- [x] **U1 Skeleton** — `ui` dependency group (fastapi, uvicorn, httpx2), `pricecharter/ui/app.py` `create_app(db_path)`,
      read-only connection per request, base layout, `pricecharter serve --host 127.0.0.1 --http-port 8000` (`--port` is Chrome's CDP port);
      test: app boots on synth DB and a write through its connection fails.
- [x] **U2 Dashboard `/`** — per-console coverage (listed, detail-fetched, stale > `--stale-days`, with history),
      recent `crawl_runs` (ok/failed/error), last `analysis_runs` row.
- [x] **U3 Browse `/games`** — name search, filters (platform, region, console, genre), sort (current price, list rank,
      name, 3y excess return when available), pagination; HTMX partial for live search.
- [x] **U4 Game page `/games/{id}`** — metadata + image, latest loose/CIB/new, Plotly monthly history (log toggle),
      recent sales table, link back to PriceCharting; 404 for unknown id.
- [x] **U5 Analysis on game page** — console index overlay, `series_metrics` (excess returns, drawdown, biggest jump),
      rising label, curve cluster, watchlist membership; hidden when tables are missing.
- [x] **U6 Console page `/consoles/{slug}`** — index chart per condition, top risers/fallers by excess return, coverage.
- [ ] **U7 Insights `/insights`** — factor lift, patterns, curve shapes, pre-breakout signals, model importance;
      extract the chart/table builders from `analysis/report.py` into a shared module (report output unchanged).
- [ ] **U8 Watchlist `/watchlist`** — sortable table linking to game pages, filter by console/condition.
- [ ] **U9 Compare `/compare?ids=…`** — overlay up to 6 titles, raw price or rebased to 100 / vs console index;
      "add to compare" from browse and game pages.
- [ ] **U10 Ship** — `./run.sh serve` (no Chrome check for `serve`/`analyze`), README section, CI runs UI tests.
