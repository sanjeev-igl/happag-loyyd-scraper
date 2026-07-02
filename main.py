"""
Hapag-Lloyd freight quote scraper — entry point.

Usage:
    python main.py
    python main.py --config config.json
    python main.py --output results.json
"""

import asyncio
from playwright.async_api import async_playwright

from hapag_lloyd.config import parse_args, load_config, QUOTE_URL
from hapag_lloyd.browser import create_browser, create_context, new_page
from hapag_lloyd.network import NetworkCapture
from hapag_lloyd.extractors.results import scrape_results_page
from hapag_lloyd.extractors.api_parser import parse_api_responses
from hapag_lloyd.output import build_output, make_output_path, save_json


async def run(cfg: dict, explicit_output: bool = False) -> dict:
    async with async_playwright() as pw:
        browser = await create_browser(pw, cfg["headless"], cfg["slow_mo"])
        context = await create_context(browser)
        page = await new_page(context)

        capture = NetworkCapture()
        capture.attach(page)

        await page.goto(QUOTE_URL, wait_until="domcontentloaded")

        print("\nBrowser is open.")
        print("  1. Log in if prompted")
        print("  2. Fill the search form")
        print("  3. Submit — wait for results to load")
        print("\nPress Enter here when results are visible ...")
        await asyncio.to_thread(input, "")

        print("[scraper] Starting extraction ...")
        api_data = parse_api_responses(capture.responses, capture.request_bodies)

        visual_data = await scrape_results_page(page, api_data)
        if api_data:
            print(f"[scraper] Parsed API data from {len(capture.responses)} captured responses")

        if not explicit_output:
            # Prefer the POST request body (exact ports the user searched)
            # then fall back to the v4 offer response, then config defaults
            search = api_data.get("search_request", {})
            offer = api_data.get("offer_v4", {})
            origin = (
                search.get("originPort") or
                offer.get("originPort") or offer.get("pol") or offer.get("origin") or
                cfg["start_location"]
            )
            dest = (
                search.get("destinationPort") or
                offer.get("destinationPort") or offer.get("pod") or offer.get("destination") or
                cfg["end_location"]
            )
            cfg["start_location"] = origin
            cfg["end_location"] = dest
            cfg["output_file"] = make_output_path(cfg)

        output = build_output(cfg, visual_data, capture.responses, api_data)
        save_json(output, cfg["output_file"])

        await browser.close()
        return output


def main() -> None:
    args = parse_args()
    cfg = load_config(args)
    asyncio.run(run(cfg, explicit_output=bool(args.output)))


if __name__ == "__main__":
    main()
