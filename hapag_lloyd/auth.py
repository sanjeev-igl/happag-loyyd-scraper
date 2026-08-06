"""Authentication: automatic SSO login or manual browser hand-off."""

import asyncio
from playwright.async_api import Frame, Page
from hapag_lloyd.config import QUOTE_URL
from hapag_lloyd.logger import get_logger

log = get_logger()
_PRIVACY_MODAL_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "button:has-text('Select All')",
    "button:has-text('Accept Cookies')",
    "button:has-text('Accept All')",
    "button:has-text('Accept all')",
    "button:has-text('Allow All')",
    "button:has-text('Confirm My Choices')",
)


async def _wait_for_cloudflare(page: Page, timeout: int = 30_000) -> None:
    """Wait out the Cloudflare Managed Challenge interstitial ("checking your browser" /
    "Verifying..." / "Security Check") shown on first navigation to hapag-lloyd.com.

    The challenge takes a variable amount of time to clear (observed 4-12+ seconds) — a
    fixed sleep races it and can lose, leaving callers to probe a page that's still the
    interstitial (or blank, mid-SPA-boot) rather than the real login/quote page.
    """
    deadline = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < deadline:
        try:
            body_text = (await page.inner_text("body")).lower()
        except Exception:
            body_text = ""
        challenge_showing = any(
            marker in body_text
            for marker in ("checking your browser", "verifying", "security check")
        )
        if not challenge_showing and body_text.strip():
            return
        await asyncio.sleep(0.5)
    log.info("[auth] Cloudflare challenge did not clear within timeout — proceeding anyway.")


def _login_frame(page: Page) -> Page | Frame:
    """Return the frame that actually hosts the B2C login form/cookie modal.

    The identity.hapag-lloyd.com login UI (form + OneTrust cookie banner) renders inside a
    same-origin iframe rather than the top-level document, so `page.locator(...)` calls
    against the main frame silently find nothing. Fall back to the main page for other steps.
    """
    for frame in page.frames:
        if "identity.hapag-lloyd.com" in frame.url:
            return frame
    return page


def _privacy_modal_targets(page: Page):
    """Yield every frame the privacy/cookie overlay could be rendered in.

    The simple OneTrust banner lives in the login frame's top-level document, but the
    expanded 'Privacy Preference Center' panel (with 'Select All' / 'Confirm My Choices')
    renders inside its own nested iframe (id 'interpretedSPHost', name 'SPUserConsent'),
    which `_login_frame` alone won't see into.
    """
    yield _login_frame(page)
    for frame in page.frames:
        if "onetrust" in frame.url.lower() or "consent" in (frame.name or "").lower():
            yield frame


async def _dismiss_privacy_modal(page: Page) -> None:
    """Dismiss the cookie/privacy overlay on the login page or main site, if present.

    Several overlays have been observed here (OneTrust cookie banner, and the
    'Privacy Preference Center' modal with 'Select All' / 'Confirm My Choices' buttons).
    'Select All' is preferred so all cookie categories are accepted in one click; once a
    button is clicked the modal is gone, so stop trying the rest.
    """
    for target in _privacy_modal_targets(page):
        for sel in _PRIVACY_MODAL_SELECTORS:
            try:
                btn = target.locator(sel).first
                if await btn.is_visible(timeout=3_000):
                    await btn.click(force=True)
                    log.info(f"[auth] Dismissed privacy/cookie overlay ({sel}).")
                    await asyncio.sleep(1)
                    return
            except Exception:
                continue


async def login(page: Page, email: str, password: str) -> None:
    """Navigate to the quote URL and fill SSO credentials if redirected to a login page."""
    await page.goto(QUOTE_URL, wait_until="domcontentloaded")
    await _wait_for_cloudflare(page)
    await asyncio.sleep(2)
    await _dismiss_privacy_modal(page)

    if await _needs_login(page):
        log.info("[auth] Detected login page — filling credentials …")
        target = _login_frame(page)
        await target.fill(
            "#signInName, input[type='email'], input[name='email'], input[name='username']",
            email,
        )
        await target.fill("#password, input[type='password']", password)

        # The OneTrust banner can render on a delay and reappear right before the click,
        # covering the form and swallowing clicks even with force=True (the browser's hit-test
        # still resolves to the modal, not the button underneath). Re-check immediately before
        # each click attempt and retry until the submit actually goes through.
        submit_selector = "#next, button[type='submit'], input[type='submit']"
        for _ in range(5):
            await _dismiss_privacy_modal(page)
            target = _login_frame(page)
            await target.click(submit_selector, force=True)
            for _ in range(10):
                if "/solutions/new-quote/" in page.url:
                    break
                await asyncio.sleep(1)
            if "/solutions/new-quote/" in page.url:
                break
        else:
            await page.screenshot(path="login_stuck_debug.png")
            raise TimeoutError(f"Login did not redirect to the quote page (stuck at {page.url})")

        log.info("[auth] Login successful.")
    else:
        log.info("[auth] Already authenticated.")


async def manual_login(page: Page) -> None:
    """Open the quote URL and let the user log in by hand, then press Enter."""
    log.info("[auth] No credentials supplied — opening browser for manual login.")
    await page.goto(QUOTE_URL, wait_until="domcontentloaded")
    await _wait_for_cloudflare(page)
    await asyncio.sleep(2)
    await _dismiss_privacy_modal(page)

    if await _needs_login(page):
        log.info("[auth] Login required. Please log in in the browser, then press Enter here …")
    else:
        log.info("[auth] Already authenticated. Press Enter to continue …")
    input()


async def _needs_login(page: Page) -> bool:
    """Return True if a login/email form is visible on the current page."""
    # Check URL keywords as a fast first pass
    url_keywords = ("login", "signin", "auth", "sso", "idp", "okta", "ping", "b2c", "adfs")
    if any(kw in page.url.lower() for kw in url_keywords):
        return True

    # Check page content: presence of an email or username input that is visible
    target = _login_frame(page)
    for sel in (
        "input[type='email']",
        "input[name='email']",
        "input[name='username']",
        "input[id*='email' i]",
        "input[id*='user' i]",
        "input[placeholder*='email' i]",
    ):
        try:
            el = target.locator(sel).first
            if await el.is_visible(timeout=2_000):
                return True
        except Exception:
            continue

    return False
