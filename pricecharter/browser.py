"""Real headed Chrome, driven over CDP.

Playwright-launched Chrome gets stuck on the Cloudflare challenge, so we start the
regular Chrome binary with --remote-debugging-port and attach to it. The profile dir
keeps the cf_clearance cookie between runs.
"""

import asyncio
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Browser, Page, Playwright

from . import BASE_URL

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHALLENGE_TITLES = ("Just a moment", "Attention Required")
BLOCKED_TYPES = {"image", "media", "font"}
# Only the site itself and Cloudflare's challenge host; ads/analytics just add load.
ALLOWED_HOSTS = {"www.pricecharting.com", "challenges.cloudflare.com"}
# Same-origin XHRs the page fires on load that we don't need.
BLOCKED_PATHS = ("/search-autocomplete", "/consoles-autocomplete", "/js/zbar.wasm")


def _cdp_up(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
        return True
    except OSError:
        return False


async def ensure_chrome(port: int, profile: Path) -> None:
    if _cdp_up(port):
        return
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile.resolve()}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        if _cdp_up(port):
            return
        await asyncio.sleep(0.5)
    raise RuntimeError(f"Chrome did not open CDP port {port}")


async def connect(pw: Playwright, port: int, profile: Path) -> tuple[Browser, Page]:
    await ensure_chrome(port, profile)
    browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    ctx = browser.contexts[0]
    page = await ctx.new_page()

    async def route(r):
        req = r.request
        u = urlsplit(req.url)
        if (
            req.resource_type in BLOCKED_TYPES
            or u.hostname not in ALLOWED_HOSTS
            or u.path.startswith(BLOCKED_PATHS)
        ):
            await r.abort()
        else:
            await r.continue_()

    await page.route("**/*", route)
    return browser, page


async def is_challenge(page: Page) -> bool:
    try:
        title = await page.title()
    except Exception:
        return True
    return not title or title.startswith(CHALLENGE_TITLES) or title.startswith("Loading")


async def wait_past_challenge(page: Page, timeout: float = 300) -> None:
    """Cloudflare usually clears by itself; if not, the user solves it in the window."""
    warned = False
    for i in range(int(timeout)):
        if not await is_challenge(page):
            return
        if not warned and i >= 15:
            print("!! Cloudflare challenge — solve it in the Chrome window, crawl resumes automatically")
            warned = True
        await asyncio.sleep(1)
    raise RuntimeError("Stuck on Cloudflare challenge")


async def warm_up(page: Page) -> None:
    """Land on the site origin so in-page fetch() carries the clearance cookie."""
    await page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    await wait_past_challenge(page)
