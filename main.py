"""
Hapag-Lloyd freight quote scraper — entry point.

Usage:
    python main.py                          # loops every route from Supabase (default)
    python main.py --limit 20                # only the top 20 Supabase lanes (by shipment_count)
    python main.py --from-db                          # loop every route in trade_lanes_all.csv instead
    python main.py --from-db --csv other_lanes.csv
    python main.py --single                  # single route from config.json/.env (old default)
    python main.py --single --config config.json
    python main.py --single --output results.json
"""

import asyncio
import sys

from playwright.async_api import Page

# Windows' default console codepage (cp1252) can't print some Unicode punctuation
# (e.g. em dashes) that shows up in scraped port/city names or log messages.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from hapag_lloyd.config import parse_args, load_config, QUOTE_URL, CONTAINER_TYPES
from hapag_lloyd.browser import create_browser, create_context, new_page
from hapag_lloyd.network import NetworkCapture
from hapag_lloyd.auth import login, manual_login
from hapag_lloyd.form import (
    dismiss_cookie_banner,
    dismiss_onboarding_tour,
    dismiss_permission_error_modal,
    fill_search_form,
    click_search,
)
from hapag_lloyd.extractors.results import scrape_results_page
from hapag_lloyd.extractors.api_parser import parse_api_responses
from hapag_lloyd.output import build_output, make_output_path, save_json
from hapag_lloyd.mongo_store import save_to_mongo
from hapag_lloyd.trade_lanes import fetch_trade_lanes, fetch_trade_lanes_from_supabase
from hapag_lloyd.checkpoint import load_checkpoint, is_done, mark_success, mark_failed
from hapag_lloyd.errors import PermissionDeniedError, format_checkpoint_error
from hapag_lloyd.logger import setup_logging

log = setup_logging()


async def _scrape_current_form_state(page: Page, cfg: dict, capture: NetworkCapture) -> dict:
    """Fill the search form for cfg's route, submit, scrape results, and return the output dict."""
    await fill_search_form(page, cfg)
    await click_search(page)

    # Some routes/container types the account isn't entitled to return a "missing
    # permissions" error banner instead of offers — dismiss it and bail out of this
    # lane rather than waiting for results that will never arrive.
    if await dismiss_permission_error_modal(page):
        raise PermissionDeniedError(
            "Service unavailable due to missing permissions for this route/container type"
        )

    # A separate onboarding carousel ("Surcharges in Ocean Freight Currency", 1 of 3) can
    # appear on the results page after search, distinct from the pre-search one.
    await dismiss_onboarding_tour(page)

    log.info("[scraper] Starting extraction ...")

    visual_data = await scrape_results_page(page, capture=capture)

    # scrape_results_page waits for the full v4 offer response before returning, so this
    # reflects everything captured for this lane.
    api_data = parse_api_responses(capture.responses, capture.request_bodies)
    if api_data:
        log.info(f"[scraper] Parsed API data from {len(capture.responses)} captured responses")

    output = build_output(cfg, visual_data, capture.responses, api_data)
    return output


async def run(cfg: dict, explicit_output: bool = False) -> list[dict]:
    outputs = []
    checkpoint = load_checkpoint()
    async with create_browser(cfg["headless"], cfg["slow_mo"]) as browser:
        context = await create_context(browser)
        page = await new_page(context)

        capture = NetworkCapture()
        capture.attach(page)

        if cfg["email"] and cfg["password"]:
            await login(page, cfg["email"], cfg["password"])
        else:
            await manual_login(page)

        await dismiss_cookie_banner(page)
        await dismiss_onboarding_tour(page)

        for i, ctype in enumerate(CONTAINER_TYPES, start=1):
            log.info(f"[container {i}/{len(CONTAINER_TYPES)}] {ctype['label']}")

            if is_done(checkpoint, cfg["start_location"], cfg["end_location"], ctype["label"]):
                log.info(f"[container {i}/{len(CONTAINER_TYPES)}] SKIPPED (already succeeded in checkpoint.json)")
                continue

            type_cfg = dict(cfg)
            type_cfg["container_type"] = ctype["label"]
            type_cfg["container_type_group"] = ctype["group"]

            capture.responses.clear()
            capture.request_bodies.clear()

            try:
                if i > 1:
                    # Re-navigate to a clean Search form for the next container type,
                    # same as switching between routes.
                    await page.goto(QUOTE_URL, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    await dismiss_cookie_banner(page)
                    await dismiss_onboarding_tour(page)

                output = await _scrape_current_form_state(page, type_cfg, capture)

                if explicit_output and len(CONTAINER_TYPES) == 1:
                    out_path = cfg["output_file"]
                else:
                    out_path = make_output_path(type_cfg)
                save_json(output, out_path)
                save_to_mongo(output)
                outputs.append(output)
                mark_success(checkpoint, cfg["start_location"], cfg["end_location"], ctype["label"])
            except Exception as exc:
                error_str = format_checkpoint_error(exc)
                log.error(f"[container {i}/{len(CONTAINER_TYPES)}] FAILED: {error_str}")
                mark_failed(checkpoint, cfg["start_location"], cfg["end_location"], ctype["label"], error=error_str)
                continue

        return outputs


async def run_from_db(
    cfg: dict, limit: int | None = None, csv_path: str = "trade_lanes_all.csv", use_supabase: bool = False,
) -> None:
    if use_supabase:
        lanes = fetch_trade_lanes_from_supabase()
        log.info(f"[supabase] Loaded {len(lanes)} trade lanes.")
    else:
        lanes = fetch_trade_lanes(csv_path)
        log.info(f"[csv] Loaded {len(lanes)} trade lanes from {csv_path}.")
    if limit:
        lanes = lanes[:limit]

    checkpoint = load_checkpoint()

    async with create_browser(cfg["headless"], cfg["slow_mo"]) as browser:
        context = await create_context(browser)
        page = await new_page(context)

        capture = NetworkCapture()
        capture.attach(page)

        if cfg["email"] and cfg["password"]:
            await login(page, cfg["email"], cfg["password"])
        else:
            await manual_login(page)

        await dismiss_cookie_banner(page)
        await dismiss_onboarding_tour(page)

        first_search = True
        for i, lane in enumerate(lanes, start=1):
            log.info(f"[lane {i}/{len(lanes)}] {lane['start_location']} to {lane['end_location']} "
                     f"(shipment_count={lane['shipment_count']})")

            lane_cfg = dict(cfg)
            lane_cfg["start_location"] = lane["start_location"]
            lane_cfg["end_location"] = lane["end_location"]

            for j, ctype in enumerate(CONTAINER_TYPES, start=1):
                log.info(f"[container {j}/{len(CONTAINER_TYPES)}] {ctype['label']}")

                if is_done(checkpoint, lane_cfg["start_location"], lane_cfg["end_location"], ctype["label"]):
                    log.info(f"[lane {i}/{len(lanes)}] [container {j}/{len(CONTAINER_TYPES)}] SKIPPED (already succeeded in checkpoint.json)")
                    continue

                type_cfg = dict(lane_cfg)
                type_cfg["container_type"] = ctype["label"]
                type_cfg["container_type_group"] = ctype["group"]

                capture.responses.clear()
                capture.request_bodies.clear()

                try:
                    if not first_search:
                        # After a search, the page is on the Offer Selection step — re-navigate
                        # to get back to a clean, empty Search form for the next container type
                        # (or the next lane, once every container type here is done).
                        await page.goto(QUOTE_URL, wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                    first_search = False

                    output = await _scrape_current_form_state(page, type_cfg, capture)
                    output_file = make_output_path(type_cfg)
                    save_json(output, output_file)
                    save_to_mongo(output)
                    mark_success(checkpoint, lane_cfg["start_location"], lane_cfg["end_location"], ctype["label"])
                except Exception as exc:
                    error_str = format_checkpoint_error(exc)
                    log.error(f"[lane {i}/{len(lanes)}] [container {j}/{len(CONTAINER_TYPES)}] FAILED: {error_str}")
                    mark_failed(
                        checkpoint, lane_cfg["start_location"], lane_cfg["end_location"], ctype["label"], error=error_str,
                    )
                    continue


def main() -> None:
    args = parse_args()
    cfg = load_config(args)

    if args.single:
        asyncio.run(run(cfg, explicit_output=bool(args.output)))
    else:
        use_supabase = not args.from_db
        asyncio.run(run_from_db(
            cfg, limit=args.limit, csv_path=args.csv, use_supabase=use_supabase,
        ))


if __name__ == "__main__":
    main()
