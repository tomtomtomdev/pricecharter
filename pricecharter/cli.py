import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from . import CONSOLES, db
from .browser import connect, warm_up
from .crawl import crawl_details, crawl_list
from .parse import today
from .throttle import Throttle


def _console(value: str) -> str:
    slug = CONSOLES.get(value, value)
    if slug not in CONSOLES.values():
        raise argparse.ArgumentTypeError(f"unknown console {value!r}; choose from {', '.join(CONSOLES)}")
    return slug


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pricecharter")
    ap.add_argument("stage", choices=["list", "details", "all"])
    ap.add_argument("-c", "--console", type=_console, nargs="+", default=list(CONSOLES.values()),
                    help=f"aliases or slugs (default: all of {', '.join(CONSOLES)})")
    ap.add_argument("--db", type=Path, default=Path("pricecharter.db"))
    ap.add_argument("--interval", type=float, default=1.0, help="min seconds between requests (default 1.0)")
    ap.add_argument("--stale-days", type=float, default=7, help="re-crawl details older than this")
    ap.add_argument("--limit", type=int, help="max detail pages per console")
    ap.add_argument("--release-date", default=today(), help="list filter release-date (default today)")
    ap.add_argument("--port", type=int, default=9222, help="Chrome remote-debugging port")
    ap.add_argument("--profile", type=Path, default=Path(".chrome-profile"))
    return ap


async def run(args: argparse.Namespace) -> None:
    conn = db.connect(args.db)
    throttle = Throttle(args.interval)
    async with async_playwright() as pw:
        browser, page = await connect(pw, args.port, args.profile)
        try:
            await warm_up(page)
            for console in args.console:
                try:
                    if args.stage in ("list", "all"):
                        await crawl_list(page, conn, throttle, console, args.release_date)
                    if args.stage in ("details", "all"):
                        await crawl_details(page, conn, throttle, console, args.stale_days, args.limit)
                except RuntimeError as e:
                    print(f"[{console}] skipped: {e}")
        finally:
            await page.close()
            conn.close()


def main() -> None:
    try:
        asyncio.run(run(build_parser().parse_args()))
    except KeyboardInterrupt:
        print("\ninterrupted — progress is committed per page, re-run to resume")


if __name__ == "__main__":
    main()
