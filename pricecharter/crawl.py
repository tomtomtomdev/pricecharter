import sqlite3
from urllib.parse import urlencode

from playwright.async_api import Page

from . import BASE_URL, db
from .browser import is_challenge, wait_past_challenge
from .parse import parse_detail, parse_list_product, today
from .throttle import DeadlineReached, Throttle

MAX_RETRIES = 6

FETCH_JSON = """async (url) => {
    const r = await fetch(url, {headers: {accept: 'application/json'}});
    return {status: r.status, retryAfter: r.headers.get('retry-after'), body: r.ok ? await r.json() : null};
}"""


def list_url(console: str, cursor: int, release_date: str) -> str:
    q = {
        "sort": "highest-price",
        "when": "none",
        "release-date": release_date,
        "exclude-variants": "true",
        "exclude-hardware": "true",
        "format": "json",
        "cursor": cursor,
    }
    return f"{BASE_URL}/console/{console}?{urlencode(q)}"


async def _fetch_json(page: Page, throttle: Throttle, url: str) -> dict:
    for attempt in range(MAX_RETRIES):
        await throttle.wait()
        res = await page.evaluate(FETCH_JSON, url)
        if res["status"] == 200 and res["body"] is not None:
            throttle.ok()
            return res["body"]
        print(f"   HTTP {res['status']} on {url} (attempt {attempt + 1})")
        if res["status"] == 429:
            await throttle.rate_limited(attempt, res["retryAfter"])
            continue
        if res["status"] == 403:
            # clearance expired: reload a real page so Cloudflare can re-challenge
            await page.goto(BASE_URL + "/", wait_until="domcontentloaded")
            await wait_past_challenge(page)
        await throttle.backoff(attempt)
    raise RuntimeError(f"giving up on {url}")


async def crawl_list(page: Page, conn: sqlite3.Connection, throttle: Throttle, console: str, release_date: str) -> int:
    run = db.start_run(conn, "list", console)
    day, cursor, rank = today(), 0, 0
    try:
        while True:
            body = await _fetch_json(page, throttle, list_url(console, cursor, release_date))
            products = body.get("products") or []
            for p in products:
                rank += 1
                db.upsert_list_game(conn, parse_list_product(p), rank, day)
            conn.commit()
            print(f"[{console}] list cursor={cursor} +{len(products)} (total {rank})")
            nxt = body.get("cursor")
            if not products or not nxt:
                break
            cursor = int(nxt)
    except Exception as e:
        db.finish_run(conn, run, rank, 1, repr(e))
        raise
    db.finish_run(conn, run, rank, 0)
    return rank


async def _load_detail(page: Page, throttle: Throttle, url: str) -> str:
    for attempt in range(MAX_RETRIES):
        await throttle.wait()
        resp = await page.goto(url, wait_until="domcontentloaded")
        if await is_challenge(page):
            await wait_past_challenge(page)
        status = resp.status if resp else 0
        if status == 429:
            print(f"   HTTP 429 on {url} (attempt {attempt + 1})")
            await throttle.rate_limited(attempt, await resp.header_value("retry-after"))
            continue
        html = await page.content()
        if "VGPC.chart_data" in html:
            throttle.ok()
            return html
        print(f"   HTTP {status} / no chart data on {url} (attempt {attempt + 1})")
        await throttle.backoff(attempt)
    raise RuntimeError(f"giving up on {url}")


async def crawl_details(
    page: Page, conn: sqlite3.Connection, throttle: Throttle, consoles: list[str],
    stale_days: float, limit: int | None,
) -> tuple[int, int]:
    games = db.games_due(conn, consoles, stale_days, limit)
    run = db.start_run(conn, "details", ",".join(consoles))
    ok = failed = 0
    day = today()
    print(f"[details] {len(games)} games due across {len(consoles)} consoles")
    try:
        for i, g in enumerate(games, 1):
            url = f"{BASE_URL}/game/{g['console']}/{g['slug']}"
            tag = f"[{g['console']}] {i}/{len(games)}"
            try:
                detail = parse_detail(await _load_detail(page, throttle, url))
                if detail["pc_id"] and detail["pc_id"] != g["id"]:
                    raise ValueError(f"id mismatch: page {detail['pc_id']} vs db {g['id']}")
                db.save_detail(conn, g["id"], detail, day)
                conn.commit()
                ok += 1
                h, s = detail["history"], detail["sales"]
                print(
                    f"{tag} {g['name']}: "
                    f"history L{len(h['loose'])}/C{len(h['cib'])}/N{len(h['new'])} "
                    f"sales L{len(s['loose'])}/C{len(s['cib'])}/N{len(s['new'])}"
                )
            except DeadlineReached:
                raise
            except Exception as e:
                conn.rollback()
                failed += 1
                print(f"{tag} FAILED {url}: {e!r}")
    except DeadlineReached as e:
        db.finish_run(conn, run, ok, failed, f"deadline: {e}")
        raise
    db.finish_run(conn, run, ok, failed)
    return ok, failed
