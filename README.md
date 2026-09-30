# pricecharter

Crawls PriceCharting console lists (highest price, no variants/hardware) and each game's
detail page into SQLite: current Loose/CIB/New prices, the full monthly "All" price
history, and recent sold listings per condition.

## Run (one step)

```sh
./run.sh                          # list + details, all consoles
./run.sh list -c nes ps2 -r pal   # just the PAL lists
./run.sh details -c switch --limit 50
```

`run.sh` installs `uv` if missing, syncs deps, and runs the crawler. Requires Google Chrome.

Platforms: `nes snes gba ds 3ds gamecube wii wiiu ps1 ps2 psp vita ps3 switch xbox xbox360`,
each crawled in three regions (48 console pages): `-r ntsc-u pal ntsc-j` (default all).
Exact slugs work too, e.g. `-c pal-nes famicom`. Japanese NES/SNES are `famicom`/`super-famicom`.

Options: `--db pricecharter.db`, `--interval 1.0` (min seconds between requests),
`--stale-days 7` (re-fetch details older than this), `--limit N` (detail pages this run),
`--until 23:00` (stop cleanly at that local time), `--list-fresh-hours 20` (skip lists crawled
recently), `--release-date YYYY-MM-DD`.

Details are prioritized across all selected consoles: never-fetched titles first, then the stalest,
so a crawl spread over several weekends always makes forward progress.

## Weekend schedule

```sh
./schedule.sh install     # Sat & Sun 01:00 → stops 23:00 (launchd LaunchAgent)
./schedule.sh status      # state, last exit code, tail of logs/crawl.log
./schedule.sh uninstall
```

It runs in your logged-in session (headed Chrome needs it). If the Mac is asleep at 01:00 the
job runs on wake, but only on Saturday or Sunday. To wake the Mac for it:
`sudo pmset repeat wakeorpoweron SU 00:55:00`.

## How it works

- Cloudflare blocks plain HTTP and Playwright-launched Chrome, so the crawler starts the
  real Chrome app with `--remote-debugging-port=9222` and a profile in `.chrome-profile/`,
  then attaches over CDP. If a challenge doesn't clear on its own, solve it in the window;
  the crawl continues.
- **List:** `/console/<slug>?…&format=json&cursor=N` (150 per page) fetched from inside the
  page, so it carries the Cloudflare cookie.
- **Detail:** `/game/<console>/<slug>`: `VGPC.chart_data` (monthly, cents) + HTML tables.
- **Throttle:** ≥1s between requests. A 429 pauses 30s/60s/120s… and doubles the interval,
  which eases back to 1s after a run of successes. Ads, analytics and images are blocked.
- Each game is committed on its own; Ctrl-C and re-run to resume.

## Tables

| table | contents |
|---|---|
| `games` | id (PriceCharting ID), console slug, platform, region (ntsc-u/pal/ntsc-j), slug, name, image, genre, release date, publisher, developer, UPC, ePID, list rank |
| `price_snapshots` | current loose/cib/new cents per game per day, from `list` and `detail` |
| `price_history` | `(game_id, condition, month) → price_cents`, condition ∈ loose/cib/new |
| `sales` | recent sold listings: condition, sale id, date, title, price, source (ebay/goldin/…), url |
| `crawl_runs` | per stage/console run log |

## Analysis

```sh
./run.sh analyze                          # all crawled consoles/conditions
./run.sh analyze -c nes snes --condition cib --window 60 --top 0.1
```

Each title's monthly price is compared to its console's median index (so the 2020–21 boom
doesn't count as a pattern). "Rising" = top 20% of 36-month excess return per console × condition.

| Step | Output table | Report section |
|---|---|---|
| Console index (median monthly move) | `console_index` | Console price index |
| Per-series returns, excess vs index, slope, volatility, drawdown, biggest jump | `series_metrics` | — |
| Factor lift with 95% Wilson ranges | `factor_lift` | Top rising factors |
| Factor combinations (≤3 traits, non-redundant) | `patterns` | Rising patterns |
| Curve-shape clusters + over-represented traits | `curve_clusters`, `cluster_summary`, `cluster_profile` | Curve shapes |
| Signals in the 12 months before the biggest jumps | `pre_breakout` | Before the jumps |
| Out-of-sample model check (time split) + permutation importance | `model_summary`, `model_importance` | Model check |
| Current titles matching the patterns (+ model forecast if it has signal) | `watchlist` | Watchlist |

Every run is logged in `analysis_runs`; the report goes to `reports/analysis-<asof>.html`
(`--report PATH`, `--no-report`, `--no-model` to skip the slowest step).

## Tests

```sh
uv run pytest
```
