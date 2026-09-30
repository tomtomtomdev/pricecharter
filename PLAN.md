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
| Patterns | mlxtend (FP-growth) | frequent factor-combination mining |
| Model | scikit-learn `HistGradientBoostingRegressor` + permutation importance, `KMeans` | no libomp/LightGBM native install; importance without SHAP |
| Report | Jinja2 + Plotly (single static HTML) | shareable file, interactive charts |
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
- [ ] **S3 Crawl window** — `--until HH:MM` graceful stop (handles past-midnight), skip a console's list
      if crawled within `--list-fresh-hours`.
- [ ] **S4 Weekend schedule** — launchd plist generator + `schedule.sh install|uninstall|status`;
      Sat & Sun 01:00 start, stops 23:00.
- [ ] **S5 ESRB** — parse & store ESRB rating.

### Analysis (`pricecharter analyze`)

- [ ] **A1 Loader** — analysis deps group, load `price_history` + `games` into pandas; synthetic test DB builder.
- [ ] **A2 Console index** — median monthly log-return per console × condition.
- [ ] **A3 Series metrics** — excess return (1y/3y/5y/all), log slope, volatility, max drawdown,
      biggest-jump month → `series_metrics`.
- [ ] **A4 Rising label** — top 20% 3y excess return per console × condition, ≥24 months.
- [ ] **A5 Factors** — region, platform, genre, publisher, release year, lifecycle position,
      franchise/keyword tokens, price bucket, CIB/Loose & New/CIB ratios, sales liquidity.
- [ ] **A6 Factor lift** — rise rate vs baseline, lift, Wilson CI, min support → `factor_lift`.
- [ ] **A7 Patterns** — FP-growth over discretized factors ⇒ rising rules (support, confidence, lift) → `patterns`.
- [ ] **A8 CLI + persistence** — `pricecharter analyze` writes tables + `analysis_runs`.
- [ ] **A9 Report** — HTML: console indices, top factors, top patterns with example titles.
- [ ] **A10 Model** — time-split HistGB on excess return, baseline comparison, permutation importance → `model_importance`.
- [ ] **A11 Curve shapes** — KMeans on normalized curves, profile clusters by factors → `curve_clusters`.
- [ ] **A12 Pre-breakout signals** — what changed 6–12 months before the biggest jumps.
- [ ] **A13 Watchlist** — current titles best matching rising patterns, in the report.
