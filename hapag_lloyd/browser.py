"""Browser and context factory.

Uses Camoufox (a patched Firefox build) instead of stock Chromium to dodge
the Cloudflare Managed Challenge's automation fingerprinting.
"""

from contextlib import asynccontextmanager

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext, Page


@asynccontextmanager
async def create_browser(headless: bool, slow_mo: int):
    async with AsyncCamoufox(headless=headless, slow_mo=slow_mo) as browser:
        yield browser


async def create_context(browser: Browser) -> BrowserContext:
    return await browser.new_context(
        viewport={"width": 1440, "height": 900},
    )


async def new_page(context: BrowserContext) -> Page:
    return await context.new_page()
