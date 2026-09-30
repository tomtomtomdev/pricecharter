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
`--stale-days 7` (re-fetch details older than this), `--limit N`, `--release-date YYYY-MM-DD`.

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

## Tests

```sh
uv run pytest
```
