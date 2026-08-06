"""Open the Price Breakdown modal, scrape all tables, then close it."""

import asyncio
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from hapag_lloyd.extractors.utils import wait_and_click, table_to_rows
from hapag_lloyd.logger import get_logger

log = get_logger()
_BTN_SEL = (
    "button:has-text('Price Breakdown'), "
    "[class*='price-breakdown']:not(table):not(tr):not(td), "
    "a:has-text('Price Breakdown')"
)
_MODAL_SEL = (
    ".price-breakdown-modal, [class*='breakdown-modal'], "
    "mat-dialog-container, .modal-content, [role='dialog']"
)
_CLOSE_SEL = (
    "button[aria-label='close' i], button:has-text('×'), "
    ".modal-close, [data-testid='close-button'], mat-dialog-container button:first-child"
)


async def extract_price_breakdown(page: Page) -> dict:
    """Click Price Breakdown, scrape the modal, close it. Returns structured dict."""
    if not await _open_modal(page):
        return {}

    modal = await page.query_selector(_MODAL_SEL)
    root = modal or page

    breakdown: dict = {}

    # First table → total price estimate
    tables = await root.query_selector_all("table")
    if tables:
        breakdown["total_price_estimate"] = await table_to_rows(tables[0])

    # Named sections (h3/h4) → next sibling table
    sections = await root.query_selector_all("h3, h4, [class*='section-title'], [class*='charges-title']")
    for sec in sections:
        sec_text = (await sec.inner_text()).strip()
        next_table = await sec.evaluate_handle(
            "el => { let s = el.nextElementSibling; "
            "while (s && s.tagName !== 'TABLE') s = s.nextElementSibling; "
            "return s; }"
        )
        if next_table and next_table.as_element():
            rows = await table_to_rows(next_table.as_element())
            if rows:
                breakdown[sec_text] = rows

    # Sidebar summary (plain text block)
    sidebar = await root.query_selector(".breakdown-sidebar, [class*='sidebar'], [class*='summary-panel']")
    if sidebar:
        breakdown["sidebar_summary"] = (await sidebar.inner_text()).strip()

    await _close_modal(page)
    return breakdown


async def _open_modal(page: Page) -> bool:
    try:
        await wait_and_click(page, _BTN_SEL, timeout=8_000)
    except PlaywrightTimeout:
        log.info("  [breakdown] Price Breakdown button not found — skipping.")
        return False

    await asyncio.sleep(1.5)

    try:
        await page.wait_for_selector(_MODAL_SEL, state="visible", timeout=8_000)
        return True
    except PlaywrightTimeout:
        log.info("  [breakdown] Modal did not appear — skipping.")
        return False


async def _close_modal(page: Page) -> None:
    try:
        await wait_and_click(page, _CLOSE_SEL, timeout=4_000)
    except PlaywrightTimeout:
        await page.keyboard.press("Escape")
    await asyncio.sleep(0.5)
