from pathlib import Path

from pricecharter.crawl import list_url
from pricecharter.parse import parse_detail, parse_list_product, price_cents

FIXTURE = Path(__file__).parent / "fixtures" / "game_nes_stadium_events.html"


def test_price_cents():
    assert price_cents("$39,600.51") == 3960051
    assert price_cents("$233.33") == 23333
    assert price_cents("-") is None
    assert price_cents(None) is None


def test_parse_list_product_maps_price_columns():
    g = parse_list_product({
        "id": "12224", "consoleUri": "nes", "productUri": "family-fun-fitness-stadium-events",
        "productName": "Family Fun Fitness Stadium Events", "imageUri": "https://x/60.jpg",
        "price1": "$19,000.00", "price2": "$233.33", "price3": "$39,600.51",
    })
    assert g["id"] == 12224
    assert (g["loose_cents"], g["cib_cents"], g["new_cents"]) == (1900000, 3960051, 23333)


def test_list_url():
    u = list_url("playstation-2", 150, "2026-09-30")
    assert u.startswith("https://www.pricecharting.com/console/playstation-2?sort=highest-price")
    assert "cursor=150" in u and "format=json" in u and "exclude-variants=true" in u


def test_parse_detail():
    d = parse_detail(FIXTURE.read_text())
    assert d["pc_id"] == 12224
    assert d["details"]["genre"] == "Sports"
    assert d["details"]["release_date"] == "1987-09-01"
    assert d["details"]["publisher"] == "Bandai"
    assert d["details"]["upc"] == "045557873059"
    assert d["details"]["asin"] is None
    assert d["current"] == {"loose_cents": 1900000, "cib_cents": 3960051, "new_cents": 23333}

    h = d["history"]
    assert set(h) == {"loose", "cib", "new"}
    assert h["loose"][0] == ("2008-09-01", 82000)
    assert h["cib"][-1] == ("2026-09-01", 3960051)
    assert all(month.endswith("-01") and cents > 0 for pts in h.values() for month, cents in pts)

    s = d["sales"]
    assert s["loose"][0]["title"] == "Private Sale" and s["loose"][0]["source"] == "private"
    assert s["loose"][0]["sale_id"].startswith("h-")
    cib = s["cib"][0]
    assert cib["sale_id"] == "ebay-133142289558"
    assert (cib["sale_date"], cib["price_cents"], cib["source"]) == ("2020-03-12", 5500000, "ebay")
    assert cib["url"].startswith("https://www.ebay.com/itm/133142289558")
    assert s["new"][0]["source"] == "goldin"
    assert len({x["sale_id"] for x in s["cib"]}) == len(s["cib"])


def test_esrb_rating():
    assert parse_detail(FIXTURE.read_text())["details"]["esrb"] is None  # page says "none"
    html = '<table id="attribute"><tr><td class="title">ESRB Rating:</td><td class="details"> Teen </td></tr></table>'
    assert parse_detail(html)["details"]["esrb"] == "Teen"
