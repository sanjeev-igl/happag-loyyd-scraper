"""Browser and context factory."""

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


async def create_browser(pw: Playwright, headless: bool, slow_mo: int) -> Browser:
    return await pw.chromium.launch(
        headless=headless,
        slow_mo=slow_mo,
        args=["--start-maximized"],
    )


async def create_context(browser: Browser) -> BrowserContext:
    return await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=_USER_AGENT,
    )


async def new_page(context: BrowserContext) -> Page:
    return await context.new_page()
