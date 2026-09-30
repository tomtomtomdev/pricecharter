import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from . import db
from .browser import connect, warm_up
from .consoles import REGIONS, platforms, resolve
from .crawl import crawl_details, crawl_list
from .parse import today
from .throttle import DeadlineReached, Throttle
from .window import deadline_from


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pricecharter")
    ap.add_argument("stage", choices=["list", "details", "all", "analyze"])
    ap.add_argument("-c", "--console", nargs="+", metavar="NAME",
                    help=f"platforms ({' '.join(platforms())}) or exact slugs like pal-nes; default all")
    ap.add_argument("-r", "--region", nargs="+", choices=REGIONS, default=list(REGIONS),
                    help="regions a platform expands to (default: all)")
    ap.add_argument("--db", type=Path, default=Path("pricecharter.db"))
    ap.add_argument("--interval", type=float, default=1.0, help="min seconds between requests (default 1.0)")
    ap.add_argument("--stale-days", type=float, default=7, help="re-crawl details older than this")
    ap.add_argument("--limit", type=int, help="max detail pages this run")
    ap.add_argument("--until", metavar="HH:MM", help="stop cleanly at this local time (e.g. 23:00)")
    ap.add_argument("--list-fresh-hours", type=float, default=20,
                    help="skip a console's list if crawled successfully within this many hours (0 = never skip)")
    ap.add_argument("--release-date", default=today(), help="list filter release-date (default today)")
    ap.add_argument("--port", type=int, default=9222, help="Chrome remote-debugging port")
    ap.add_argument("--profile", type=Path, default=Path(".chrome-profile"))
    an = ap.add_argument_group("analyze")
    an.add_argument("--window", type=int, default=36, choices=[12, 36, 60], help="months for excess return")
    an.add_argument("--top", type=float, default=0.2, help="share of titles labeled rising per console")
    an.add_argument("--condition", nargs="+", choices=["loose", "cib", "new"], help="default all")
    an.add_argument("--asof", help="analysis end month YYYY-MM-01 (default latest)")
    an.add_argument("--report", type=Path, help="HTML report path (default reports/analysis-<asof>.html)")
    an.add_argument("--no-report", action="store_true", help="skip the HTML report")
    return ap


def run_analyze(args: argparse.Namespace) -> None:
    from .analysis.report import render_report  # pandas stack only needed here
    from .analysis.run import analyze, persist

    conn = db.connect(args.db)
    try:
        res = analyze(conn, args.consoles if args.console else None, args.condition,
                      window=args.window, top=args.top, asof=args.asof)
        run_id = persist(conn, res)
    finally:
        conn.close()
    p = res.params
    print(f"analysis #{run_id}: {p['n_series']} series, {p['n_labeled']} labeled, asof {p['asof']}, "
          f"window {p['window']}m, top {p['top']:.0%}")
    for cond, grp in res.factor_lift.groupby("condition"):
        print(f"\n[{cond}] top factors (lift, 95% lower bound, n)")
        for r in grp[grp["lift_lo"] > 1].head(10).itertuples():
            print(f"  {r.factor + '=' + r.value:<36} {r.lift:4.2f}x  >={r.lift_lo:4.2f}x  n={r.n}")
    for cond, grp in res.patterns.groupby("condition"):
        print(f"\n[{cond}] top patterns")
        for r in grp.head(10).itertuples():
            print(f"  {r.items:<60} {r.lift:4.2f}x  >={r.lift_lo:4.2f}x  n={r.n}")
    if not args.no_report:
        path = render_report(res, args.report or Path("reports") / f"analysis-{p['asof']}.html")
        print(f"\nreport: {path.resolve()}")


async def run(args: argparse.Namespace) -> None:
    conn = db.connect(args.db)
    throttle = Throttle(args.interval, deadline=args.deadline)
    if args.deadline:
        print(f"crawl window closes at {args.deadline:%Y-%m-%d %H:%M}")
    async with async_playwright() as pw:
        browser, page = await connect(pw, args.port, args.profile)
        try:
            await warm_up(page)
            if args.stage in ("list", "all"):
                for console in args.consoles:
                    if args.list_fresh_hours and db.list_fresh(conn, console, args.list_fresh_hours):
                        print(f"[{console}] list fresh, skipping")
                        continue
                    try:
                        await crawl_list(page, conn, throttle, console, args.release_date)
                    except RuntimeError as e:
                        print(f"[{console}] list skipped: {e}")
            if args.stage in ("details", "all"):
                await crawl_details(page, conn, throttle, args.consoles, args.stale_days, args.limit)
        except DeadlineReached as e:
            print(f"stopping: {e}. Progress is saved; the next run resumes.")
        finally:
            await page.close()
            conn.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        args.consoles = [c.slug for c in resolve(args.console, args.region)]
        args.deadline = deadline_from(args.until) if args.until else None
    except ValueError as e:
        ap.error(str(e))
    return args


def main() -> None:
    args = parse_args()
    if args.stage == "analyze":
        run_analyze(args)
        return
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\ninterrupted — progress is committed per page, re-run to resume")


if __name__ == "__main__":
    main()
