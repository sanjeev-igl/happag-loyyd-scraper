"""Shared low-level helpers for all extractors."""

import asyncio
import re
from playwright.async_api import Page, ElementHandle, TimeoutError as PlaywrightTimeout


def parse_amount(text: str) -> float | None:
    """Return the first numeric value from a string like 'USD 10.00' or '17,805.00'."""
    cleaned = text.strip().replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", cleaned)
    return float(m.group()) if m else None


async def wait_and_click(page: Page, selector: str, timeout: int = 15_000) -> None:
    await page.wait_for_selector(selector, state="visible", timeout=timeout)
    await page.click(selector)


async def fill_autocomplete(page: Page, input_selector: str, value: str) -> None:
    """Type into an autocomplete field and select the first suggestion."""
    await page.click(input_selector)
    await page.fill(input_selector, "")
    await page.type(input_selector, value, delay=80)
    await page.wait_for_selector(
        "ul[role='listbox'] li, .autocomplete-item, mat-option",
        state="visible",
        timeout=10_000,
    )
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Enter")
    await asyncio.sleep(0.5)


async def table_to_rows(table_el: ElementHandle | None) -> list[dict]:
    """Convert an HTML <table> element into a list of dicts keyed by header text."""
    if not table_el:
        return []
    rows = []
    headers: list[str] = []
    for tr in await table_el.query_selector_all("tr"):
        cells = await tr.query_selector_all("th, td")
        texts = [(await c.inner_text()).strip() for c in cells]
        if not headers:
            headers = texts
        elif texts:
            rows.append(dict(zip(headers, texts)))
    return rows
