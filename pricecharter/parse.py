"""Pure parsers: list JSON rows and game detail HTML -> plain dicts. No I/O."""

import hashlib
import json
import re
from datetime import UTC, date, datetime

from bs4 import BeautifulSoup

from . import CONDITIONS

NONE_VALUES = {"", "none", "n/a"}


def price_cents(text: str | None) -> int | None:
    """'$39,600.51' -> 3960051; blanks/dashes -> None."""
    if not text:
        return None
    digits = re.sub(r"[^\d.]", "", text)
    if not digits:
        return None
    return round(float(digits) * 100)


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return None if text.lower() in NONE_VALUES else text


def _iso_date(text: str | None) -> str | None:
    text = _clean(text)
    if not text:
        return None
    for fmt in ("%B %d, %Y", "%Y-%m-%d", "%B %Y", "%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


# ---------- list JSON ----------

def parse_list_product(p: dict) -> dict:
    # On console list pages: price1 = loose, price2 = new, price3 = CIB
    return {
        "id": int(p["id"]),
        "console": p["consoleUri"],
        "slug": p["productUri"],
        "name": p["productName"],
        "image_url": p.get("imageUri") or None,
        "loose_cents": price_cents(p.get("price1")),
        "new_cents": price_cents(p.get("price2")),
        "cib_cents": price_cents(p.get("price3")),
    }


# ---------- detail HTML ----------

def parse_chart_data(html: str) -> dict[str, list[tuple[str, int]]]:
    """VGPC.chart_data -> {'loose'|'cib'|'new': [(YYYY-MM-01, cents), ...]}, zeros dropped."""
    i = html.find("VGPC.chart_data")
    if i < 0:
        return {}
    data, _ = json.JSONDecoder().raw_decode(html[html.index("{", i):])
    out = {}
    for key, cond in CONDITIONS.items():
        points = []
        for ts, cents in data.get(key) or []:
            if cents:
                month = datetime.fromtimestamp(ts / 1000, tz=UTC).date().replace(day=1)
                points.append((month.isoformat(), int(cents)))
        out[cond] = points
    return out


DETAIL_FIELDS = {
    "Genre:": "genre",
    "Release Date:": "release_date",
    "ESRB Rating:": "esrb",
    "Publisher:": "publisher",
    "Developer:": "developer",
    "Model Number:": "model_number",
    "Player Count:": "player_count",
    "UPC:": "upc",
    "ASIN (Amazon):": "asin",
    "ePID (eBay):": "epid",
    "PriceCharting ID:": "pc_id",
}

CURRENT_PRICE_IDS = {"used_price": "loose_cents", "complete_price": "cib_cents", "new_price": "new_cents"}


def _sale_rows(soup: BeautifulSoup, key: str) -> list[dict]:
    box = soup.select_one(f"div.completed-auctions-{key}:not(.tab)")
    if not box:
        return []
    sales = []
    for tr in box.select("tbody tr"):
        d = tr.select_one("td.date")
        p = tr.select_one("td.numeric span.js-price")
        if not d or not p:
            continue
        title_td = tr.select_one("td.title")
        a = title_td.select_one("a") if title_td else None
        title = _clean(a.get_text() if a else title_td.get_text() if title_td else None)
        sale_date = d.get_text(strip=True)
        cents = price_cents(p.get_text())
        row_id = tr.get("id")
        source = row_id.split("-", 1)[0] if row_id else None
        if not source and title_td:
            m = re.search(r"\[([^\]]+)\]", title_td.get_text())
            source = m.group(1).lower() if m else "private"
        sales.append({
            "sale_id": row_id or "h-" + hashlib.sha1(f"{sale_date}|{title}|{cents}".encode()).hexdigest()[:16],
            "sale_date": sale_date,
            "title": title,
            "price_cents": cents,
            "source": source,
            "url": a.get("href") if a else None,
        })
    return sales


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    details = {}
    table = soup.select_one("table#attribute")
    for tr in table.select("tr") if table else []:
        k, v = tr.select_one("td.title"), tr.select_one("td.details")
        if k and v and (field := DETAIL_FIELDS.get(k.get_text(strip=True))):
            details[field] = _clean(v.get_text())
    details["release_date"] = _iso_date(details.get("release_date"))
    pc_id = details.pop("pc_id", None)

    current = {}
    for html_id, col in CURRENT_PRICE_IDS.items():
        el = soup.select_one(f"#{html_id} .price")
        current[col] = price_cents(el.get_text()) if el else None

    return {
        "pc_id": int(pc_id) if pc_id and pc_id.isdigit() else None,
        "details": details,
        "current": current,
        "history": parse_chart_data(html),
        "sales": {cond: _sale_rows(soup, key) for key, cond in CONDITIONS.items()},
    }


def today() -> str:
    return date.today().isoformat()
