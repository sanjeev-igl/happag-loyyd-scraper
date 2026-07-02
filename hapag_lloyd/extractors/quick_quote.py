"""Extract the Quick Quotes summary card (validity period + per-container prices)."""

import re
from playwright.async_api import Page


async def extract_quick_quote_summary(page: Page) -> dict:
    summary: dict = {}

    summary.update(await _extract_validity(page))
    container_prices = await _extract_container_prices(page)
    if container_prices:
        summary["ocean_freight_per_container"] = container_prices

    return summary


async def _extract_validity(page: Page) -> dict:
    els = await page.query_selector_all("[class*='validity'], [class*='valid-date'], .valid-period")
    if not els:
        return {}
    txt = await els[0].inner_text()
    dates = re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2} \w+ \d{4}", txt)
    if len(dates) >= 2:
        return {"valid_from": dates[0], "valid_to": dates[1]}
    return {}


async def _extract_container_prices(page: Page) -> list[dict]:
    price_rows = await page.query_selector_all(
        ".quick-quote-detail .price-row, [class*='container-price'], "
        ".offer-detail-row, .price-line"
    )
    results = []
    for row in price_rows:
        row_txt = await row.inner_text()
        currency_m = re.search(r"(USD|EUR|GBP|SGD|INR|AUD|CAD)", row_txt)
        amount_m = re.search(r"[\d,]+(?:\.\d{2})?", row_txt.replace(",", ""))
        type_m = re.search(r"(20STD|40STD|40HC|20'|40')", row_txt, re.I)
        if amount_m:
            results.append({
                "container_type": type_m.group() if type_m else None,
                "currency": currency_m.group() if currency_m else None,
                "amount": float(amount_m.group().replace(",", "")),
            })
    return results
