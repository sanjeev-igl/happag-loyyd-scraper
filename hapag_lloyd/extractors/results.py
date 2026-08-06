"""Orchestrate all extractors to build the full results payload."""

import asyncio
import re
from datetime import datetime, timezone
from playwright.async_api import Page

from hapag_lloyd.extractors.offer_grid import extract_offer_grid
from hapag_lloyd.extractors.quick_quote import extract_quick_quote_summary
from hapag_lloyd.extractors.price_breakdown import extract_price_breakdown
from hapag_lloyd.extractors.api_parser import parse_api_responses
from hapag_lloyd.form import dismiss_onboarding_tour
from hapag_lloyd.network import NetworkCapture
from hapag_lloyd.errors import NoOffersFoundError, NoSpotRateError, OfferSelectionPageError
from hapag_lloyd.logger import get_logger

log = get_logger()

async def scrape_results_page(page: Page, api_data: dict | None = None, capture: NetworkCapture | None = None) -> dict:
    """Wait for the Offer Selection page and collect all quote data."""
    log.info("[results] Waiting for offer selection page …")
    offer_page_loaded = True
    try:
        await page.wait_for_selector(
            ".offer-selection, [class*='offerSelection'], "
            "[class*='departure'], .route-header",
            state="visible",
            timeout=15_000,
        )
    except Exception:
        log.info("[results] Specific selectors not found — falling back to networkidle …")
        offer_page_loaded = False
        try:
            await page.wait_for_load_state("networkidle", timeout=8_000)
            offer_page_loaded = True
        except Exception:
            pass

    # The "Surcharges in Ocean Freight Currency" onboarding tour renders once the offer
    # selection page itself is up — dismissing it right after click_search is too early
    # (the tour isn't in the DOM yet), so it must be retried here too.
    await dismiss_onboarding_tour(page)

    # The full priced offer (/api/v4/offers/{id}) can arrive after status polling responses —
    # wait for it explicitly rather than racing it with a fixed sleep. HL's backend computes
    # pricing asynchronously and status-polls until it's ready, so this can take a while.
    v4_offer_received = False
    if capture is not None:
        for _ in range(45):
            if capture.has_v4_offer():
                v4_offer_received = True
                break
            await asyncio.sleep(1)
        else:
            log.info("[results] Timed out waiting for priced offer (v4) response.")
        api_data = parse_api_responses(capture.responses, capture.request_bodies)
    else:
        await asyncio.sleep(2)

    # The tour can also appear only once pricing has finished loading (as seen in the
    # v4-offer wait above), so check once more right before scraping the DOM.
    await dismiss_onboarding_tour(page)

    departures   = await extract_offer_grid(page)
    quick_quote  = await extract_quick_quote_summary(page)
    price_breakdown = await extract_price_breakdown(page)

    # Fall back to API data when DOM scraping yields nothing
    offer_v4 = (api_data or {}).get("offer_v4", {})
    if not departures and offer_v4.get("departures"):
        log.info("[results] DOM scraping yielded no departures — using API data.")
        departures = offer_v4["departures"]

    if not quick_quote:
        quick_quote = _quick_quote_from_api(offer_v4)

    if not price_breakdown:
        price_breakdown = _price_breakdown_from_api(offer_v4)

    if not departures:
        if not offer_page_loaded:
            raise OfferSelectionPageError(
                f"Offer selection page never loaded at {page.url} (no offer grid, no networkidle)"
            )
        if capture is not None and not v4_offer_received:
            raise NoOffersFoundError(
                "Offer selection page loaded but no priced offer (/api/v4/offers/{id}) "
                "was returned within 45s — carrier likely has no capacity/rate for this route"
            )
        raise NoSpotRateError(
            "Offer selection page loaded and a priced offer response was received, "
            "but it contained no departures/spot rates for this route and container type"
        )

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
    """Summarize ocean freight per container type for the earliest departure's first product offer."""
    departures = offer_v4.get("departures", [])
    if not departures:
        return {}
    first_offers = departures[0].get("productOffers", [])
    if not first_offers:
        return {}
    result: dict = {"validFrom": offer_v4.get("validFrom")}
    ocean_freight = first_offers[0].get("ocean_freight_per_container")
    if ocean_freight:
        result["ocean_freight_per_container"] = ocean_freight
    return result


def _price_breakdown_from_api(offer_v4: dict) -> dict:
    """Full charge breakdown for the earliest departure's first product offer."""
    departures = offer_v4.get("departures", [])
    if not departures:
        return {}
    first_offers = departures[0].get("productOffers", [])
    if not first_offers:
        return {}
    return {"charges": first_offers[0].get("charges", [])}


async def _extract_route(page: Page) -> str | None:
    els = await page.query_selector_all(".route-header, [class*='route-header'], h2, h3, [class*='routeTitle']")
    for el in els:
        txt = (await el.inner_text()).strip()
        if re.search(r"[A-Z]{5}\s*[-–]\s*[A-Z]{5}", txt):
            return txt
    return None
