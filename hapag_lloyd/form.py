"""Search form interactions: location, container, commodity, and Search button."""

import asyncio
import re
from playwright.async_api import Page


async def dismiss_cookie_banner(page: Page) -> None:
    """Click the cookie consent 'Accept All' button if the banner is present."""
    selectors = [
        "button:has-text('Accept All')",
        "button:has-text('Accept all')",
        "button:has-text('Allow All')",
        "button:has-text('Allow all')",
        "#onetrust-accept-btn-handler",
        "[data-testid='cookie-accept-all']",
        "button.accept-all-cookies",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3_000):
                await btn.click()
                print("[cookie] Dismissed cookie consent banner.")
                await asyncio.sleep(1)
                return
        except Exception:
            continue


async def fill_search_form(page: Page, cfg: dict) -> None:
    print("[form] Waiting for search form …")
    await page.wait_for_selector(
        "input[placeholder*='location' i], input[placeholder*='origin' i], "
        "hl-port-input input, [data-testid='origin-input']",
        state="visible",
        timeout=20_000,
    )

    await _set_location(page, cfg["start_location"], index=0)
    await _set_location(page, cfg["end_location"], index=1)
    await _set_radio(page, "received", cfg["received_at"])
    await _set_radio(page, "delivered", cfg["delivered_to"])
    await _set_date(page, cfg.get("valid_from", ""))
    await _set_container_type(page, cfg["container_type"])
    await _set_numeric_input(page, index=0, value=cfg["container_quantity"])
    await _set_numeric_input(page, index=1, value=cfg["weight_per_container"])
    await _set_commodity(page, cfg["commodity"])


async def click_search(page: Page) -> None:
    print("[form] Clicking Search …")
    btn = await page.query_selector(
        "button:has-text('Search'), [data-testid='search-button'], "
        "input[type='submit'][value*='Search' i], hl-button:has-text('Search')"
    )
    if btn:
        await btn.click()
    else:
        await page.keyboard.press("Enter")


# ── private helpers ───────────────────────────────────────────────────────────

async def _set_location(page: Page, value: str, index: int) -> None:
    label = "start" if index == 0 else "end"
    print(f"[form] Setting {label} location: {value}")
    inputs = await page.query_selector_all(
        "hl-port-input input, [placeholder*='start' i], [placeholder*='origin' i], "
        "[placeholder*='from' i], [placeholder*='end' i], [placeholder*='destination' i], "
        "[placeholder*='to' i], [placeholder*='location' i]"
    )
    el = inputs[index] if index < len(inputs) else None
    if not el:
        return
    await el.click()
    await el.fill("")
    await el.type(value, delay=80)
    await page.wait_for_selector(
        "mat-option, li[role='option'], .autocomplete-option",
        state="visible",
        timeout=10_000,
    )
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Enter")
    await asyncio.sleep(0.8)


async def _set_radio(page: Page, side: str, value: str) -> None:
    keyword = "terminal" if value == "terminal" else "door"
    radios = await page.query_selector_all("input[type='radio']")
    for radio in radios:
        label_el = await radio.evaluate_handle("el => el.closest('label') || el.parentElement")
        label_text = (await label_el.inner_text()).lower() if label_el else ""
        if keyword in label_text:
            await radio.check()
            break


async def _set_date(page: Page, value: str) -> None:
    if not value:
        return
    date_inputs = await page.query_selector_all("input[type='date'], input[placeholder*='date' i]")
    if date_inputs:
        await date_inputs[0].fill(value)


async def _set_container_type(page: Page, container_type: str) -> None:
    print(f"[form] Setting container type: {container_type}")
    dropdowns = await page.query_selector_all("select, mat-select, [role='combobox'], hl-select")
    for dd in dropdowns:
        dd_text = (await dd.inner_text()).lower()
        if any(kw in dd_text for kw in ("general purpose", "20'", "40'", "container")):
            tag = await dd.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                await dd.select_option(label=re.compile(container_type, re.I))
            else:
                await dd.click()
                await asyncio.sleep(0.5)
                for opt in await page.query_selector_all("mat-option, li[role='option']"):
                    t = await opt.inner_text()
                    if container_type.upper() in t.upper() or "high cube" in t.lower():
                        await opt.click()
                        break
            break


async def _set_numeric_input(page: Page, index: int, value: str) -> None:
    inputs = await page.query_selector_all("input[type='number']")
    if index < len(inputs):
        await inputs[index].fill(value)


async def _set_commodity(page: Page, commodity: str) -> None:
    print(f"[form] Setting commodity: {commodity}")
    els = await page.query_selector_all(
        "select[name*='commodity' i], mat-select[formcontrolname*='commodity' i], "
        "[placeholder*='commodity' i], [aria-label*='commodity' i]"
    )
    for el in els:
        tag = await el.evaluate("el => el.tagName.toLowerCase()")
        if tag == "select":
            await el.select_option(label=re.compile(commodity, re.I))
        else:
            await el.click()
            await asyncio.sleep(0.5)
            for opt in await page.query_selector_all("mat-option, li[role='option']"):
                t = await opt.inner_text()
                if commodity.upper() in t.upper():
                    await opt.click()
                    break
        break
