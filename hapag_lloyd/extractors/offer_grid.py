"""Extract departure dates and Quick Quote prices from the offer grid."""

import asyncio
import re
from playwright.async_api import Page
from hapag_lloyd.extractors.utils import parse_amount
from hapag_lloyd.logger import get_logger

log = get_logger()

async def extract_offer_grid(page: Page) -> list[dict]:
    """
    Return one entry per departure column:
        [{"date": "2026-07-09", "quick_quote_usd": 10.0}, …]
    """
    log.info("[results] Extracting offer grid …")
    try:
        await page.wait_for_selector(
            ".departure-date, [class*='departure'], td[class*='date'], th[class*='date'], "
            "[data-testid*='departure'], .offer-grid-header",
            state="visible",
            timeout=10_000,
        )
    except Exception:
        log.info("  [offer_grid] Date selectors not found — attempting extraction anyway …")
    await asyncio.sleep(1)

    date_cells = await _find_date_cells(page)
    price_cells = await page.query_selector_all(
        ".quick-quote-price, [class*='quickQuote'] .price, "
        "[class*='quick-quote'] .amount, .offer-price"
    )

    departures = []
    for i, dc in enumerate(date_cells):
        txt = await dc.inner_text()
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", txt)
        date_str = date_match.group() if date_match else txt.strip()

        price = None
        if i < len(price_cells):
            price = parse_amount(await price_cells[i].inner_text())

        departures.append({"date": date_str, "quick_quote_usd": price})

    return departures


async def _find_date_cells(page: Page) -> list:
    cells = await page.query_selector_all(
        ".departure-date, [class*='departure-date'], [class*='departureDate'], "
        "th.date-column, td.date-column, [data-date]"
    )
    if cells:
        return cells

    # Fallback: any cell whose text contains a YYYY-MM-DD date
    all_cells = await page.query_selector_all("th, td, .grid-cell, .column-header")
    return [c for c in all_cells if re.search(r"\d{4}-\d{2}-\d{2}", await c.inner_text())]
