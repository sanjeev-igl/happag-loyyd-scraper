"""Orchestrate all extractors to build the full results payload."""

import asyncio
import re
from datetime import datetime, timezone
from playwright.async_api import Page

from hapag_lloyd.extractors.offer_grid import extract_offer_grid
from hapag_lloyd.extractors.quick_quote import extract_quick_quote_summary
from hapag_lloyd.extractors.price_breakdown import extract_price_breakdown


async def scrape_results_page(page: Page, api_data: dict | None = None) -> dict:
    """Wait for the Offer Selection page and collect all quote data."""
    print("[results] Waiting for offer selection page …")
    try:
        await page.wait_for_selector(
            ".offer-selection, [class*='offerSelection'], "
            "[class*='departure'], .route-header",
            state="visible",
            timeout=15_000,
        )
    except Exception:
        print("[results] Specific selectors not found — falling back to networkidle …")
        try:
            await page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
    await asyncio.sleep(2)

    departures   = await extract_offer_grid(page)
    quick_quote  = await extract_quick_quote_summary(page)
    price_breakdown = await extract_price_breakdown(page)

    # Fall back to API data when DOM scraping yields nothing
    offer_v4 = (api_data or {}).get("offer_v4", {})
    if not departures and offer_v4.get("departures"):
        print("[results] DOM scraping yielded no departures — using API data.")
        departures = offer_v4["departures"]

    if not quick_quote:
        quick_quote = _quick_quote_from_api(offer_v4)

    if not price_breakdown:
        price_breakdown = _price_breakdown_from_api(offer_v4)

    return {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "route": await _extract_route(page) or _route_from_api(offer_v4),
        "departures": departures,
        "quick_quote": quick_quote,
        "price_breakdown": price_breakdown,
    }


def _route_from_api(offer_v4: dict) -> str | None:
    origin = offer_v4.get("originPort")
    dest   = offer_v4.get("destinationPort")
    if origin and dest:
        return f"{origin} – {dest}"
    return None


def _quick_quote_from_api(offer_v4: dict) -> dict:
    result: dict = {}
    for key in ("quickQuote", "price", "totalPrice", "oceanFreight"):
        if key in offer_v4:
            result[key] = offer_v4[key]
    for key in ("validFrom", "validTo"):
        if key in offer_v4:
            result[key] = offer_v4[key]
    return result


def _price_breakdown_from_api(offer_v4: dict) -> dict:
    result: dict = {}
    for key in ("chargeBreakdown", "charges", "rates"):
        if key in offer_v4:
            result[key] = offer_v4[key]
    return result


async def _extract_route(page: Page) -> str | None:
    els = await page.query_selector_all(".route-header, [class*='route-header'], h2, h3, [class*='routeTitle']")
    for el in els:
        txt = (await el.inner_text()).strip()
        if re.search(r"[A-Z]{5}\s*[-–]\s*[A-Z]{5}", txt):
            return txt
    return None
