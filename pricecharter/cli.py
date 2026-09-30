import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from . import db
from .browser import connect, warm_up
from .consoles import REGIONS, platforms, resolve
from .crawl import crawl_details, crawl_list
from .parse import today
from .throttle import Throttle


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pricecharter")
    ap.add_argument("stage", choices=["list", "details", "all"])
    ap.add_argument("-c", "--console", nargs="+", metavar="NAME",
                    help=f"platforms ({' '.join(platforms())}) or exact slugs like pal-nes; default all")
    ap.add_argument("-r", "--region", nargs="+", choices=REGIONS, default=list(REGIONS),
                    help="regions a platform expands to (default: all)")
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
            for console in args.consoles:
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        args.consoles = [c.slug for c in resolve(args.console, args.region)]
    except ValueError as e:
        ap.error(str(e))
    return args


def main() -> None:
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\ninterrupted — progress is committed per page, re-run to resume")


if __name__ == "__main__":
    main()
