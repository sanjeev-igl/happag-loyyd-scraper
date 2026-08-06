"""Search form interactions: location, container, commodity, and Search button."""

import asyncio
import re
from playwright.async_api import Page

from hapag_lloyd.errors import InvalidLocationError, LocationDropdownError, SearchFormNotFoundError, UIBlockedError
from hapag_lloyd.logger import get_logger

log = get_logger()

_COOKIE_CONSENT_SELECTORS = [
    "button:has-text('Accept All')",
    "button:has-text('Accept all')",
    "button:has-text('Allow All')",
    "button:has-text('Allow all')",
    "#onetrust-accept-btn-handler",
    "[data-testid='cookie-accept-all']",
    "button.accept-all-cookies",
    # OneTrust's expanded "Privacy Preference Center" panel (reached e.g. via "Customize"),
    # as opposed to the simple banner above.
    "button:has-text('Select All')",
    "button:has-text('Confirm My Choices')",
]


def _cookie_consent_targets(page: Page):
    """Yield the main page plus any OneTrust consent iframe.

    OneTrust's expanded "Privacy Preference Center" panel renders inside an iframe
    (typically id 'interpretedSPHost', name 'SPUserConsent') rather than the top-level
    document, so a plain `page.locator(...)` silently finds nothing when that panel — as
    opposed to the simple top-level banner — is what's showing.
    """
    yield page
    for frame in page.frames:
        if frame != page.main_frame and (
            "onetrust" in frame.url.lower() or "consent" in (frame.name or "").lower()
        ):
            yield frame


async def dismiss_cookie_banner(page: Page) -> None:
    """Click the cookie consent 'Accept All' / 'Select All' button if a banner or the
    expanded Privacy Preference Center panel is present."""
    for target in _cookie_consent_targets(page):
        for sel in _COOKIE_CONSENT_SELECTORS:
            try:
                btn = target.locator(sel).first
                if await btn.is_visible(timeout=3_000):
                    await btn.click(force=True)
                    log.info(f"[cookie] Dismissed cookie consent overlay ({sel}).")
                    await asyncio.sleep(1)
                    return
            except Exception:
                continue


async def dismiss_onboarding_tour(page: Page, timeout: int = 1_500) -> None:
    """Close a 'hal-onboarding' feature-tour dialog via its X button, if one is showing.

    Multiple distinct tours appear at different points in the flow (e.g. 'Recently Searched'
    on the search page, 'Surcharges in Ocean Freight Currency' on the results page) — this
    closes whichever one is currently on screen, or does nothing if none is present. Callers
    re-check this at each point a tour is known to appear, since the tour can render well
    after the page it belongs to has loaded (e.g. once async pricing data arrives), so a
    single check right after navigation can miss it. Each selector gets a short timeout since
    most calls find nothing at all.
    """
    close_selectors = [
        ".hal-onboarding .q-dialog__x",
        "[role='dialog'].hal-onboarding button.q-dialog__x",
        "[role='dialog'] button.q-dialog__x",
        ".q-dialog button[aria-label='Close' i]",
        "[role='dialog'] button[aria-label='Close' i]",
        "button:has-text('Got it')",
        "button:has-text('Done')",
        "button:has-text('Skip')",
    ]
    for sel in close_selectors:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=timeout)
            await btn.click(force=True)
            log.info("[tour] Dismissed onboarding tour.")
            await asyncio.sleep(0.5)
            return
        except Exception:
            continue


async def dismiss_permission_error_modal(page: Page, timeout: int = 1_500) -> bool:
    """Dismiss the "This service is unavailable due to missing permissions" error modal.

    Some routes/container types the account isn't entitled to surface this red banner
    with a "Global transaction ID" instead of offer results. It isn't recoverable by
    retrying, so callers should treat its presence as a signal to skip the lane rather
    than wait for results that will never arrive. Returns True if the modal was found
    and dismissed.
    """
    try:
        banner = page.get_by_text("missing permissions", exact=False).first
        await banner.wait_for(state="visible", timeout=timeout)
    except Exception:
        return False

    for sel in ["button:has-text('Dismiss')", "[data-testid='dismiss-button']"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1_000):
                await btn.click(force=True)
                log.info("[form] Dismissed 'missing permissions' error modal.")
                await asyncio.sleep(0.5)
                return True
        except Exception:
            continue

    log.info("[form] 'missing permissions' error modal seen but Dismiss button not found.")
    return True


async def fill_search_form(page: Page, cfg: dict) -> None:
    log.info("[form] Waiting for search form …")
    try:
        await page.wait_for_selector(
            "[data-testid='start-input'], [data-testid='end-input']",
            state="visible",
            timeout=20_000,
        )
    except Exception as exc:
        await page.screenshot(path="form_stuck_debug.png")
        raise SearchFormNotFoundError(
            f"Search form (start/end location inputs) never appeared at {page.url}"
        ) from exc

    await _set_location(page, cfg["start_location"], testid="start-input")
    await _set_location(page, cfg["end_location"], testid="end-input")
    await _set_radio(page, "received", cfg["received_at"])
    await _set_radio(page, "delivered", cfg["delivered_to"])
    await _set_date(page, cfg.get("valid_from", ""))
    await _set_container_type(page, cfg["container_type"], cfg.get("container_type_group", ""))
    await _set_numeric_input(page, index=0, value=cfg["container_quantity"])
    await _set_numeric_input(page, index=1, value=cfg["weight_per_container"])
    await _set_commodity(page, cfg["commodity"])


async def click_search(page: Page) -> None:
    log.info("[form] Clicking Search …")
    try:
        # A stale loading overlay from the previous search can still be covering the form.
        await page.locator(".q-inner-loading").first.wait_for(state="hidden", timeout=5_000)
    except Exception:
        pass

    btn = await page.query_selector(
        "button:has-text('Search'), [data-testid='search-button'], "
        "input[type='submit'][value*='Search' i], hl-button:has-text('Search')"
    )
    try:
        if btn:
            await btn.click(timeout=10_000)
        else:
            await page.keyboard.press("Enter")
    except Exception as exc:
        msg = str(exc).lower()
        if "intercepts pointer events" in msg:
            raise UIBlockedError("Search button click blocked by a loading overlay") from exc
        raise


# ── private helpers ───────────────────────────────────────────────────────────

async def _set_location(page: Page, value: str, testid: str, attempts: int = 3) -> None:
    """Type a location into the autocomplete and select the first match.

    The site's location search (a debounced call to locations.api.hlag.cloud) occasionally
    doesn't fire or the dropdown doesn't render in time — retry the whole type+wait cycle
    rather than failing the lane outright.
    """
    log.info(f"[form] Setting {testid}: {value}")
    el = page.locator(f"[data-testid='{testid}']").first

    # Best-effort guess at HL's "no results" empty state — not yet confirmed against a real
    # invalid-port response, so this may need its selector corrected once one is observed.
    no_results_selector = "text=/no result|not found|no match/i"

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            # A stale loading overlay from the previous search can still be covering the
            # form when the next lane/container starts — wait for it to clear rather than
            # letting the click hang for the full 30s default actionability timeout.
            await page.locator(".q-inner-loading").first.wait_for(state="hidden", timeout=5_000)
        except Exception:
            pass

        try:
            await el.click(force=True, timeout=10_000)
            await el.fill("")
            await el.type(value, delay=80)
        except Exception as exc:
            msg = str(exc).lower()
            if "intercepts pointer events" in msg:
                last_error = exc
                log.info(f"[form] {testid} click blocked by overlay (attempt {attempt}/{attempts}) — retrying.")
                await asyncio.sleep(1)
                continue
            raise UIBlockedError(f"Could not interact with {testid} (blocked or unresponsive)") from exc

        aria_controls = await el.get_attribute("aria-controls")
        container_selector = f"#{aria_controls}" if aria_controls else None
        option_selector = f"{container_selector} [role='option']" if container_selector else "[role='option']"
        scoped_no_results = f"{container_selector} {no_results_selector}" if container_selector else no_results_selector

        try:
            await page.wait_for_selector(option_selector, state="visible", timeout=8_000)
            await page.locator(option_selector).first.click(force=True)
            await asyncio.sleep(0.5)
            return
        except Exception as exc:
            # The dropdown may have rendered an explicit "no results" state rather than just
            # never appearing — that means the port name itself is invalid, not a transient glitch.
            try:
                if await page.locator(scoped_no_results).first.is_visible(timeout=500):
                    raise InvalidLocationError(
                        f"No matching location found for {testid}='{value}'"
                    ) from exc
            except InvalidLocationError:
                raise
            except Exception:
                pass

            last_error = exc
            log.info(f"[form] {testid} dropdown didn't appear (attempt {attempt}/{attempts}) — retrying.")
            await asyncio.sleep(1)

    raise LocationDropdownError(
        f"Location dropdown never appeared for {testid}='{value}' after {attempts} attempts"
    ) from last_error


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


async def _set_container_type(page: Page, container_type: str, group: str = "") -> None:
    """Select a container type from the search form's Quasar q-select picker.

    The listbox is a collapsible accordion: each group header row
    (q-item--parent, e.g. "General Purpose") has a toggle <button> that
    expands/collapses its child rows via a height-collapse (not DOM removal
    or scrolling) — collapsed children sit in the DOM with clientHeight 0.
    Only "General Purpose" starts expanded, so any other group's toggle
    button must be clicked before its options become visible/clickable.
    """
    log.info(f"[form] Setting container type: {container_type}" + (f" ({group})" if group else ""))

    trigger = page.locator("[data-testid='container-input']").first
    if not await trigger.count():
        trigger = page.locator("[data-testid='container-section']").first
    await trigger.click()

    listbox = page.locator("[role='listbox']").first
    await listbox.wait_for(state="visible", timeout=8_000)
    await asyncio.sleep(0.3)  # let the open transition (q-transition--fade) settle

    option = page.get_by_role("option", name=container_type, exact=True).first

    async def _option_ready() -> bool:
        return bool(await option.count()) and await option.is_visible()

    if group and not await _option_ready():
        header = page.get_by_text(group, exact=True).first
        toggle_btn = header.locator(
            "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' q-item--parent ')][1]//button"
        ).first
        if await toggle_btn.count():
            await toggle_btn.click()
            for attempt in range(6):
                if await _option_ready():
                    break
                await asyncio.sleep(0.3)
            else:
                # Expansion animation still hasn't revealed it — try once more,
                # in case the first click landed before the listbox finished opening.
                await toggle_btn.click()
                await asyncio.sleep(0.5)

    await option.wait_for(state="visible", timeout=5_000)
    await option.click()
    await asyncio.sleep(0.3)


async def _set_numeric_input(page: Page, index: int, value: str) -> None:
    inputs = await page.query_selector_all("input[type='number']")
    if index >= len(inputs):
        return
    el = inputs[index]
    await el.click(force=True)
    await el.press("Control+A")
    await el.press("Backspace")
    await el.type(value, delay=30)
    actual = await el.input_value()
    if actual != value:
        raise ValueError(f"Numeric input {index} shows '{actual}' after setting '{value}'")


async def _set_commodity(page: Page, commodity: str) -> None:
    log.info(f"[form] Setting commodity: {commodity}")
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
