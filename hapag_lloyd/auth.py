"""Authentication: automatic SSO login or manual browser hand-off."""

import asyncio
from playwright.async_api import Page
from hapag_lloyd.config import QUOTE_URL


async def login(page: Page, email: str, password: str) -> None:
    """Navigate to the quote URL and fill SSO credentials if redirected to a login page."""
    await page.goto(QUOTE_URL, wait_until="domcontentloaded")
    await asyncio.sleep(3)

    if await _needs_login(page):
        print("[auth] Detected login page — filling credentials …")
        await page.fill(
            "input[type='email'], input[name='email'], input[name='username']",
            email,
        )
        await page.fill("input[type='password']", password)
        await page.click("button[type='submit'], input[type='submit']")
        await page.wait_for_url("**/solutions/new-quote/**", timeout=30_000)
        print("[auth] Login successful.")
    else:
        print("[auth] Already authenticated.")


async def manual_login(page: Page) -> None:
    """Open the quote URL and let the user log in by hand, then press Enter."""
    print("[auth] No credentials supplied — opening browser for manual login.")
    await page.goto(QUOTE_URL, wait_until="domcontentloaded")
    await asyncio.sleep(3)

    if await _needs_login(page):
        print("[auth] Login required. Please log in in the browser, then press Enter here …")
    else:
        print("[auth] Already authenticated. Press Enter to continue …")
    input()


async def _needs_login(page: Page) -> bool:
    """Return True if a login/email form is visible on the current page."""
    # Check URL keywords as a fast first pass
    url_keywords = ("login", "signin", "auth", "sso", "idp", "okta", "ping", "b2c", "adfs")
    if any(kw in page.url.lower() for kw in url_keywords):
        return True

    # Check page content: presence of an email or username input that is visible
    for sel in (
        "input[type='email']",
        "input[name='email']",
        "input[name='username']",
        "input[id*='email' i]",
        "input[id*='user' i]",
        "input[placeholder*='email' i]",
    ):
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2_000):
                return True
        except Exception:
            continue

    return False
