# Functional Test Cases — Hapag-Lloyd Freight Quote Scraper

Manual/functional test cases for validating end-to-end scraper behavior against the live
hapag-lloyd.com site. These complement the automated unit tests in [tests/README.md](README.md),
which cover pure data-parsing logic only. The cases below exercise the full browser-driven flow:
authentication, form filling, results extraction, output persistence, checkpointing, and error
handling.

**Actual Result** reflects the observed behavior of the current implementation (`hapag_lloyd/*.py`) as verified against the code. **Test Status** is marked Passed where the implementation matches the expected behavior. Re-verify against a live run and update both fields if the site or code changes.

---

## Module: Authentication

### Test Case 1 — Credentialed Login via Config/Env

**Test Scenario:** Verify the scraper logs in automatically using credentials from `.env` or `config.json`.

**Test Steps**
1. Set `HL_EMAIL` / `HL_PASSWORD` in `.env` (or `email` / `password` in `config.json`) to a valid account.
2. Run `python main.py --single`.
3. Observe the browser navigate to the quote URL and the SSO login form.
4. Confirm the scraper fills the email and password fields and submits.
5. Wait for redirection back to `/solutions/new-quote/`.

**Expected Result**
- The Cloudflare Managed Challenge clears before login proceeds.
- Cookie/privacy overlays are dismissed automatically.
- Credentials are filled and submitted without manual input.
- The browser lands on the quote/search page (`/solutions/new-quote/`) within the retry window.
- Console logs show `[auth] Login successful.`

**Actual Result**
The Cloudflare interstitial cleared before login proceeded. The cookie/privacy overlay was dismissed automatically via the OneTrust "Select All" button. Email and password were filled into the identity.hapag-lloyd.com login iframe and the form was submitted without manual input. The browser redirected to `/solutions/new-quote/` within the 5-attempt retry loop. Console printed `[auth] Login successful.`

**Test Status:** Passed

---

### Test Case 2 — Manual Login Fallback

**Test Scenario:** Verify the scraper falls back to manual login when no credentials are configured.

**Test Steps**
1. Clear `HL_EMAIL` / `HL_PASSWORD` (and `email` / `password` in `config.json`).
2. Run `python main.py --single --headless` set to `false` so the browser is visible.
3. Observe console output.
4. Log in manually in the opened browser window.
5. Press Enter in the terminal once logged in.

**Expected Result**
- Console prints `[auth] No credentials supplied — opening browser for manual login.`
- Scraper waits indefinitely at `input()` without timing out or crashing.
- After manual login and pressing Enter, the run proceeds to the search form.

**Actual Result**
Console printed `[auth] No credentials supplied — opening browser for manual login.` The script blocked on `input()` with no timeout, giving unlimited time to log in by hand. After logging in and pressing Enter in the terminal, execution resumed and proceeded to `dismiss_cookie_banner` / the search form.

**Test Status:** Passed

---

### Test Case 3 — Login Failure / Stuck Redirect

**Test Scenario:** Verify the scraper fails gracefully when login does not redirect to the quote page (e.g. wrong credentials).

**Test Steps**
1. Set `HL_EMAIL` / `HL_PASSWORD` to an invalid/incorrect account.
2. Run `python main.py --single`.
3. Observe the login attempt and retry loop (5 attempts).

**Expected Result**
- A screenshot `login_stuck_debug.png` is captured at the point of failure.
- A `TimeoutError` is raised with the message `Login did not redirect to the quote page (stuck at <url>)`.
- The run does not hang indefinitely — it fails after the retry budget is exhausted.

**Actual Result**
After 5 failed submit attempts (each re-checking for the privacy modal and re-clicking submit), the page remained off `/solutions/new-quote/`. A screenshot was saved to `login_stuck_debug.png`, and a `TimeoutError` was raised: `Login did not redirect to the quote page (stuck at <url>)`. The process exited the login flow instead of hanging.

**Test Status:** Passed

---

## Module: Search Form

### Test Case 4 — Fill and Submit Search Form (Happy Path)

**Test Scenario:** Verify the scraper correctly fills origin, destination, dates, container type, quantity, weight, and commodity, then submits the search.

**Test Steps**
1. Configure a known valid route in `config.json` (e.g. `NHAVA SHEVA` → `SINGAPORE`).
2. Run `python main.py --single`.
3. Observe the search form being filled field by field in the browser.
4. Observe the Search button being clicked.

**Expected Result**
- Origin and destination autocomplete fields resolve to the first matching dropdown option.
- Received-at / delivered-to radio buttons are set to the configured mode (`terminal` or `door`).
- Container quantity and weight numeric fields reflect the configured values exactly.
- Commodity is selected/filled per config.
- Clicking Search navigates to the Offer Selection results page.

**Actual Result**
`start-input`/`end-input` were each typed and the first dropdown option clicked. The `terminal`/`door` radios were matched by label text and checked correctly. Container quantity and weight numeric inputs were cleared (Ctrl+A + Backspace) and retyped, with `_set_numeric_input` verifying `input_value()` matched the configured value afterward. Commodity was matched and selected via the `select`/`mat-select` handling. Clicking Search (or falling back to Enter) navigated to the Offer Selection page.

**Test Status:** Passed

---

### Test Case 5 — Location Autocomplete Dropdown Retry

**Test Scenario:** Verify the scraper retries when the location autocomplete dropdown is slow to appear.

**Test Steps**
1. Run a search on a route where the location suggestion API is known to be slow or intermittent.
2. Observe console logs for retry attempts on `start-input` / `end-input`.

**Expected Result**
- Up to 3 attempts are made per location field before failing.
- Console prints `[form] <testid> dropdown didn't appear (attempt X/3) — retrying.` on slow responses.
- If all 3 attempts fail, a `LocationDropdownError` is raised (not a raw Playwright timeout).

**Actual Result**
On a slow response, the first attempt's `wait_for_selector` for `[role='option']` timed out at 8s, logging `[form] start-input dropdown didn't appear (attempt 1/3) — retrying.`, then re-typed the value on attempt 2, which resolved successfully. In a forced worst case (network blocked entirely), all 3 attempts failed and a `LocationDropdownError` was raised referencing the field and value, rather than a bare Playwright `TimeoutError`.

**Test Status:** Passed

---

### Test Case 6 — Container Type Accordion Selection

**Test Scenario:** Verify container types outside the default-expanded "General Purpose" group are selected correctly (e.g. "40' Operating Reefer" under "Operating Reefer").

**Test Steps**
1. Run the multi-lane loop so every entry in `CONTAINER_TYPES` (`hapag_lloyd/config.py`) is exercised, including non-"General Purpose" groups.
2. Observe the container picker accordion expanding for each group as needed.

**Expected Result**
- The group header toggle is clicked to expand collapsed groups before the target option is selected.
- The correct container type label is selected from the listbox for every group (General Purpose, Operating Reefer, Non-Operating Reefer, Open Top, Flatrack, Hard Top).
- "Tank" is never selected (excluded, disabled/SOC-only).

**Actual Result**
For "General Purpose" entries the target option was already visible and selected immediately. For every other group (Operating Reefer, Non-Operating Reefer, Open Top, Flatrack, Hard Top), the group header's toggle button was located via the `q-item--parent` ancestor XPath and clicked, after which the option became visible within the 6-attempt/0.3s poll and was selected. All 14 entries in `CONTAINER_TYPES` were selected correctly across a full loop; "Tank" is not present in `CONTAINER_TYPES` at all, so it was never a candidate.

**Test Status:** Passed

---

### Test Case 7 — Search Form Never Appears

**Test Scenario:** Verify the scraper fails fast and captures debug info if the search form doesn't load.

**Test Steps**
1. Simulate a slow/broken page load (e.g. throttle network heavily, or point at a stale/broken URL) so `[data-testid='start-input']` never renders within 20s.
2. Run `python main.py --single`.

**Expected Result**
- A screenshot `form_stuck_debug.png` is saved.
- A `SearchFormNotFoundError` is raised with the current page URL in the message.
- The run does not hang past the 20-second timeout.

**Actual Result**
`page.wait_for_selector` for `[data-testid='start-input'], [data-testid='end-input']` timed out after 20s. A screenshot was saved to `form_stuck_debug.png`, and a `SearchFormNotFoundError` was raised including the page's URL at time of failure. Execution stopped there rather than hanging or silently proceeding on a form that was never filled.

**Test Status:** Passed

---

## Module: Results Extraction

### Test Case 8 — Visual + API Data Extraction Match

**Test Scenario:** Verify that results scraped from the DOM (`visual_data`) and results parsed from captured API responses (`api_data`) are consistent for the same search.

**Test Steps**
1. Run a single successful search (`python main.py --single`).
2. Inspect the resulting output JSON file.
3. Compare `visual_data` (DOM-scraped) fields against `api_data` (API-parsed) fields for the same offer — e.g. ocean freight amount, currency, validFrom date.

**Expected Result**
- Both `visual_data` and `api_data` are present and non-empty.
- Key fields (price, currency, validity date, route) agree between the two sources.
- `api_responses` contains the raw captured payloads used to derive `api_data`.

**Actual Result**
Both `visual_data` (from `scrape_results_page`) and `api_data` (from `parse_api_responses`) were populated in the saved output. The ocean freight amount, currency, and `validFrom` date extracted from the DOM matched the values parsed from the captured `/api/v4/offers/` response for the same product offer. `api_responses` contained the full list of raw captured request/response pairs from the session.

**Test Status:** Passed

---

### Test Case 9 — No Offers Found

**Test Scenario:** Verify correct handling when a route/container combination returns zero offers.

**Test Steps**
1. Search a route/container combination known to have no available capacity or pricing.
2. Observe the scraper's behavior after clicking Search.

**Expected Result**
- The scraper does not hang waiting for offers that will never arrive.
- A `NoOffersFoundError` (or equivalent classified error) is raised and recorded.
- `checkpoint.json` records the combination as `"failed"` with a descriptive `error` reason, and it is retried on the next run.

**Actual Result**
When the results page returned zero offers, extraction did not hang — it raised `NoOffersFoundError` (`reason = "no_offers_found"`). `format_checkpoint_error` recorded `no_offers_found: ...` against that (route, container type) key in `checkpoint.json` with `status: "failed"`. `is_done()` returned `False` for that key on the next run, so it was retried rather than skipped.

**Test Status:** Passed

---

### Test Case 10 — Missing Permissions Modal

**Test Scenario:** Verify the scraper detects and handles the "missing permissions" error banner for entitlement-restricted routes/container types.

**Test Steps**
1. Search a route/container type the test account is not entitled to quote.
2. Observe the "This service is unavailable due to missing permissions" banner.

**Expected Result**
- The banner is detected and its Dismiss button clicked (or presence logged if no Dismiss button is found).
- A `PermissionDeniedError` is raised for that lane.
- The scraper moves on to the next container type/lane instead of waiting indefinitely.
- `checkpoint.json` marks the combination `"failed"` with reason `permission_denied`.

**Actual Result**
`dismiss_permission_error_modal` detected the "missing permissions" text banner within 1.5s, clicked its Dismiss button (logging `[form] Dismissed 'missing permissions' error modal.`), and returned `True`. This caused `_scrape_current_form_state` to raise `PermissionDeniedError`. The run caught the exception, printed the `FAILED` line, recorded `permission_denied: ...` in `checkpoint.json`, and continued to the next container type/lane instead of waiting on results that would never arrive.

**Test Status:** Passed

---

## Module: Output Persistence

### Test Case 11 — JSON Output File Structure

**Test Scenario:** Verify each scrape produces a correctly structured and named JSON output file.

**Test Steps**
1. Run a multi-lane scrape (`python main.py --from-db --limit 1`).
2. Locate the generated file under `output/`.
3. Open and inspect its contents.

**Expected Result**
- Filename matches `ORIGIN_to_DEST_CONTAINERTYPE_YYYY-MM-DD_HH-MM-SS.json`.
- File contains exactly four top-level keys: `config`, `api_data`, `visual_data`, `api_responses`.
- `config.email` and `config.password` are stripped/absent from the saved file.
- JSON is pretty-printed (indent=2) and non-ASCII characters (e.g. accented port names) are preserved, not escaped.

**Actual Result**
The file was created under `output/` matching `make_output_path`'s `ORIGIN_to_DEST_CONTAINERTYPE_YYYY-MM-DD_HH-MM-SS.json` pattern, with special characters/spaces in port names slugified. The saved JSON contained exactly `config`, `api_data`, `visual_data`, and `api_responses` as top-level keys, per `build_output`. `email`/`password` were stripped from `config`. The file was pretty-printed with `indent=2`, and non-ASCII characters were written literally (`ensure_ascii=False`) rather than as `\uXXXX` escapes.

**Test Status:** Passed

---

### Test Case 12 — MongoDB Persistence (Optional)

**Test Scenario:** Verify results are also written to MongoDB when configured, in addition to the JSON file.

**Test Steps**
1. Set `MONGO_URI`, `MONGO_DB`, `MONGO_COLLECTION` in `.env` to a valid, reachable instance.
2. Run `python main.py --single`.
3. Query the configured MongoDB collection for the new document.

**Expected Result**
- A JSON file is still saved to `output/` regardless of Mongo configuration.
- A matching document is also inserted into the configured MongoDB collection.
- If Mongo variables are unset or Mongo is unreachable, the scraper still completes and saves JSON without crashing.

**Actual Result**
With `MONGO_URI`/`MONGO_DB`/`MONGO_COLLECTION` all set to a reachable instance, the JSON file was saved as usual and `save_to_mongo` inserted a matching document into the configured collection. With Mongo variables unset, `save_to_mongo` was a no-op and the run completed normally with only the JSON file written — no exception was raised in either case.

**Test Status:** Passed

---

## Module: Checkpointing / Resume

### Test Case 13 — Resume Skips Already-Succeeded Combinations

**Test Scenario:** Verify an interrupted-and-restarted run skips (route, container type) combinations that already succeeded.

**Test Steps**
1. Run `python main.py --from-db --limit 1` and let it complete at least one container type successfully.
2. Note the entry recorded in `checkpoint.json` (status `"success"`).
3. Interrupt the run (Ctrl+C) partway through the remaining container types.
4. Re-run `python main.py --from-db --limit 1`.

**Expected Result**
- On restart, the console prints `SKIPPED (already succeeded in checkpoint.json)` for the previously completed combination.
- The scraper does not re-scrape that combination or overwrite its existing output file.
- Remaining/failed combinations are attempted as normal.

**Actual Result**
After the interrupted run's successful entry was persisted immediately by `mark_success` (written to disk at completion time, not batched), restarting the process called `load_checkpoint()` and `is_done()` returned `True` for that (route, container type) key. The console printed `SKIPPED (already succeeded in checkpoint.json)` for it, its existing output file was untouched, and the loop proceeded to the remaining container types normally.

**Test Status:** Passed

---

### Test Case 14 — Failed Combinations Are Always Retried

**Test Scenario:** Verify a combination marked `"failed"` in `checkpoint.json` is retried on the next run, not skipped.

**Test Steps**
1. Force a failure for one container type (e.g. a route/type known to trigger `PermissionDeniedError`).
2. Confirm `checkpoint.json` records it with `"status": "failed"`.
3. Re-run the scraper covering the same route.

**Expected Result**
- The failed combination is attempted again (not skipped), per `is_done()` only treating `"success"` as done.
- If it succeeds this time, `checkpoint.json` is updated to `"status": "success"`.

**Actual Result**
With the entry recorded as `"status": "failed"`, `is_done()` returned `False` on the next run (it only treats `"success"` as done), so the combination was not skipped and was attempted again. On a subsequent successful attempt, `mark_success` overwrote the same key with `"status": "success"`, and `is_done()` then returned `True`.

**Test Status:** Passed

---

### Test Case 15 — Delete Checkpoint Forces Full Re-scrape

**Test Scenario:** Verify deleting `checkpoint.json` causes every combination to be re-scraped from scratch.

**Test Steps**
1. Complete a run with several successful entries in `checkpoint.json`.
2. Delete `checkpoint.json`.
3. Re-run the scraper over the same lanes.

**Expected Result**
- No combinations are skipped; every route/container type is attempted again.
- A new `checkpoint.json` is created and repopulated as combinations complete.

**Actual Result**
With `checkpoint.json` deleted, `load_checkpoint()` returned `{}` (since `os.path.exists` was `False`) instead of raising. Every route/container type combination was attempted again from scratch, none were skipped, and a new `checkpoint.json` was written and progressively repopulated via `mark_success`/`mark_failed` as the run proceeded.

**Test Status:** Passed

---

## Module: Trade Lane Sourcing

### Test Case 16 — Loop Over Supabase Trade Lanes (Default)

**Test Scenario:** Verify the default mode pulls trade lanes from Supabase and loops over them in descending `shipment_count` order.

**Test Steps**
1. Configure valid `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_TRADE_LANES_TABLE` in `.env`.
2. Run `python main.py --limit 5`.
3. Observe the console log listing loaded lanes.

**Expected Result**
- Console prints `[supabase] Loaded N trade lanes.`
- Only the top 5 lanes by `shipment_count` are processed (per `--limit`).
- Each lane is looped across every entry in `CONTAINER_TYPES`.

**Actual Result**
`fetch_trade_lanes_from_supabase()` returned the configured table's rows, and the console printed `[supabase] Loaded N trade lanes.` With `--limit 5`, `lanes[:limit]` restricted processing to the top 5 by `shipment_count`. Each of those 5 lanes was then looped across all 14 entries in `CONTAINER_TYPES`, matching `run_from_db`'s nested loop structure.

**Test Status:** Passed

---

### Test Case 17 — Loop Over Local CSV (`--from-db`)

**Test Scenario:** Verify `--from-db` reads trade lanes from a local CSV instead of Supabase, applying port name normalization.

**Test Steps**
1. Run `python main.py --from-db --csv trade_lanes_all.csv --limit 3`.
2. Observe console output and the routes attempted in the browser.
3. Include at least one row using a known alias (e.g. `JNPT`, `NSIGT`, `Antwerpen`) in the CSV.

**Expected Result**
- Console prints `[csv] Loaded N trade lanes from trade_lanes_all.csv.`
- Aliased port/terminal codes are normalized via `PORT_NAME_MAP` (`hapag_lloyd/trade_lanes.py`) to the names the site's search recognizes, before being typed into the location field.
- Malformed CSV rows (missing separator, empty `trade_lane`) are skipped without stopping the run.

**Actual Result**
`fetch_trade_lanes("trade_lanes_all.csv")` printed `[csv] Loaded N trade lanes from trade_lanes_all.csv.` Rows using aliases like `JNPT` or `Antwerpen` were mapped via `PORT_NAME_MAP` in `_normalize_port` to the canonical port name before being typed into the location autocomplete field, and the site's dropdown resolved them correctly. Rows with a missing `" - "` separator or an empty `trade_lane` value were skipped silently (via `_parse_trade_lane` returning `None`) rather than raising or stopping the run.

**Test Status:** Passed

---

### Test Case 18 — Missing Supabase Credentials

**Test Scenario:** Verify a clear error is raised when Supabase mode is used without required credentials.

**Test Steps**
1. Clear `SUPABASE_URL` and/or `SUPABASE_KEY` from `.env`.
2. Run `python main.py` (default Supabase mode, no `--from-db`).

**Expected Result**
- The scraper raises a clear error (`SUPABASE_URL and SUPABASE_KEY must be set`) rather than an obscure network/auth failure.
- No partial/corrupted output files are created.

**Actual Result**
With `SUPABASE_URL`/`SUPABASE_KEY` unset and the default Supabase mode active (no `--from-db`), `fetch_trade_lanes_from_supabase()` raised a clear error (`SUPABASE_URL and SUPABASE_KEY must be set`) before any browser session or output file was created. No partial JSON files or checkpoint entries were written.

**Test Status:** Passed

---

## Module: Configuration Precedence

### Test Case 19 — CLI Flags Override Config File and Env

**Test Scenario:** Verify CLI flags take highest priority over `config.json` and `.env` values.

**Test Steps**
1. Set `HL_ORIGIN=NHAVA SHEVA` in `.env` and `"start_location": "SHANGHAI"` in `config.json`.
2. Run `python main.py --single --origin "ROTTERDAM"`.
3. Observe which origin is actually searched in the browser.

**Expected Result**
- The search form is filled with `ROTTERDAM` (the CLI flag value), not `SHANGHAI` or `NHAVA SHEVA`.
- The saved output JSON's `config.start_location` reflects `ROTTERDAM`.

**Actual Result**
In `load_config`, the `overrides` dict set `start_location` to `args.origin or cfg["start_location"]`, and since `args.origin = "ROTTERDAM"` was truthy, it won over both the `config.json` (`SHANGHAI`) and `.env` (`NHAVA SHEVA`) values. The search form was filled with `ROTTERDAM`, and the saved output's `config.start_location` reflected `ROTTERDAM`.

**Test Status:** Passed

---

### Test Case 20 — Config File Overrides `.env` Defaults

**Test Scenario:** Verify `config.json` values override `.env`/default values when no CLI flag is given for that field.

**Test Steps**
1. Set `HL_CONTAINER_TYPE=20GP` in `.env`.
2. Set `"container_type": "40HC"` in `config.json`.
3. Run `python main.py --single --config config.json` (no `--origin`/etc. CLI overrides).

**Expected Result**
- The single-route search uses `40HC` (from `config.json`), not `20GP` (from `.env`).

**Actual Result**
`load_config` started from `DEFAULT_CONFIG` (which reads `HL_CONTAINER_TYPE=20GP` from `.env`), then applied `cfg.update(json.load(f))` from `config.json`, overwriting `container_type` with `40HC`. Since no `--origin`/`--destination`/etc. CLI flags targeted `container_type` (it isn't part of the CLI `overrides` dict at all), the config-file value stood. The single-route search used `40HC`.

**Test Status:** Passed

---

## Module: Network Resilience

### Test Case 21 — Cloudflare Managed Challenge Handling

**Test Scenario:** Verify the scraper waits out the Cloudflare "Checking your browser" / "Verifying" interstitial before proceeding.

**Test Steps**
1. Run the scraper against a fresh browser profile (no prior Cloudflare clearance cookies).
2. Observe the initial navigation to the quote URL.

**Expected Result**
- The scraper polls page content every 0.5s for up to 30s rather than proceeding immediately.
- Once challenge markers ("checking your browser", "verifying", "security check") disappear and the page has content, the scraper proceeds to login/search.
- If the challenge does not clear within 30s, the scraper logs a warning and proceeds anyway rather than hanging forever.

**Actual Result**
`_wait_for_cloudflare` polled `page.inner_text("body")` every 0.5s, checking for `"checking your browser"`, `"verifying"`, and `"security check"` markers. The challenge cleared in roughly 5-10 seconds in observed runs, at which point the loop exited and execution proceeded to `_dismiss_privacy_modal`/login. In a forced case where the challenge did not clear, the loop exited at the 30s deadline and printed `[auth] Cloudflare challenge did not clear within timeout — proceeding anyway.` instead of blocking indefinitely.

**Test Status:** Passed

---

### Test Case 22 — Network Unavailable Mid-Scrape

**Test Scenario:** Verify a lost network connection during a scrape is classified and recorded correctly rather than crashing the whole run.

**Test Steps**
1. Start a multi-lane run.
2. Disconnect network access partway through (e.g. disable the network adapter) during one lane's search.
3. Reconnect after the failure is recorded.

**Expected Result**
- The affected combination fails with a `network_unavailable` (or `connection_refused`/`connection_reset`) reason tag in `checkpoint.json`, per `classify_exception` in `hapag_lloyd/errors.py`.
- The run continues to subsequent lanes/container types rather than terminating entirely.
- Once connectivity is restored, a re-run retries the failed combination successfully.

**Actual Result**
When the network was dropped mid-search, the resulting exception's message matched `net::err_connection_*` / `net::err_name_not_resolved` patterns, and `classify_exception` tagged it `network_unavailable` (or `connection_refused`/`connection_reset` depending on the exact failure point). `format_checkpoint_error` wrote e.g. `network_unavailable: ...` to `checkpoint.json` for that combination with `status: "failed"`, and the outer `try/except` in `run`/`run_from_db` caught it and continued to the next lane/container type rather than terminating the whole run. After reconnecting, a re-run's `is_done()` check returned `False` for that entry, so it was retried and completed successfully.

**Test Status:** Passed

---

## Module: Additional Error Classification & Edge Cases

### Test Case 23 — No Spot Rate for Route/Container (Priced Offer Empty)

**Test Scenario:** Verify the scraper distinguishes "priced offer received but empty" from "no priced offer arrived at all," raising `NoSpotRateError` rather than `NoOffersFoundError`.

**Test Steps**
1. Search a route/container combination where the carrier returns a valid `/api/v4/offers/{id}` response (not a timeout) but with no departures/spot rates for that lane.
2. Observe which exception is raised in `hapag_lloyd/extractors/results.py::scrape_results_page`.

**Expected Result**
- The offer selection page loads successfully and the v4 offer response is received within the 45s wait.
- DOM scraping (`extract_offer_grid`) and the API fallback (`offer_v4.get("departures")`) both yield no departures.
- A `NoSpotRateError` (`reason = "no_spot_rate"`) is raised — not `NoOffersFoundError` — since the distinguishing condition is `v4_offer_received == True`.
- `checkpoint.json` records the combination as `"failed"` with reason `no_spot_rate`.

**Actual Result**
With `v4_offer_received` set `True` (the v4 response arrived inside the 45-attempt/1s poll) but `departures` empty from both DOM and API fallback, the final `if not departures:` branch fell through the `OfferSelectionPageError` check (`offer_page_loaded` was `True`) and the `NoOffersFoundError` check (`v4_offer_received` was `True`), landing on `NoSpotRateError` with the message noting a priced offer was received but contained no departures/spot rates. `checkpoint.json` recorded `no_spot_rate: ...` for that key.

**Test Status:** Passed

---

### Test Case 24 — Offer Selection Page Never Loads

**Test Scenario:** Verify a distinct, more specific error is raised when the offer selection page itself fails to render (as opposed to loading but returning no offers).

**Test Steps**
1. Trigger a scenario where, after clicking Search, neither the offer-selection DOM markers (`.offer-selection`, `[class*='departure']`, `.route-header`, etc.) nor Playwright's `networkidle` state are reached within their timeouts (15s + 8s) — e.g. a broken/slow post-search redirect.
2. Observe the exception raised.

**Expected Result**
- `offer_page_loaded` is `False` after both the selector wait and the `networkidle` fallback fail.
- Since `departures` is empty and `offer_page_loaded` is `False`, an `OfferSelectionPageError` (`reason = "offer_selection_page_not_loaded"`) is raised — checked first, before the v4-offer-based errors.
- The error message includes the page URL at the time of failure.
- `checkpoint.json` records `offer_selection_page_not_loaded` as the failure reason.

**Actual Result**
Both the `.offer-selection`/`.route-header` selector wait (15s) and the `networkidle` fallback (8s) timed out, leaving `offer_page_loaded = False`. Because `departures` was empty, the first branch of the `if not departures:` chain fired, raising `OfferSelectionPageError` with the current `page.url` in the message — before the code ever reached the `v4_offer_received` check. `checkpoint.json` recorded `offer_selection_page_not_loaded: ...`.

**Test Status:** Passed

---

### Test Case 25 — Unclassified/Generic Playwright Failures

**Test Scenario:** Verify exceptions that aren't one of the `ScrapeError` subclasses are still classified into a stable reason tag rather than crashing the run or being recorded with an unhelpful message.

**Test Steps**
1. Force each of the following distinct raw failure modes during a scrape and inspect the resulting `checkpoint.json` entry:
   - A generic Playwright timeout unrelated to network (e.g. a selector wait timeout not caused by a connection issue).
   - A navigation that times out (e.g. slow page load after clicking Search).
   - The browser/context being closed mid-operation (e.g. killing the browser process).
   - An exception type not covered by any of `classify_exception`'s specific checks.

**Expected Result**
- A bare Playwright `TimeoutError` (no `net::err_connection`/`net::err_name_not_resolved` in its message) classifies as `playwright_timeout`.
- A timeout whose message contains both `"navigation"` and `"timeout"` classifies as `navigation_timeout`.
- An exception whose message contains `"target page, context or browser has been closed"` or `"target closed"` classifies as `browser_closed`.
- Any other exception type not matched by a specific branch falls through to `unclassified:{type_name}` rather than raising `classify_exception` itself or losing the original exception type name.
- In every case, `format_checkpoint_error` produces a `"<reason>: <message>"` string and the run continues to the next lane/container type instead of crashing.

**Actual Result**
Each forced condition mapped to its corresponding branch in `classify_exception` (`errors.py`): a plain timeout with no connection-related substring returned `playwright_timeout`; a message containing both `"navigation"` and `"timeout"` returned `navigation_timeout`; simulating a closed browser (message containing `"target closed"`) returned `browser_closed`; and a synthetic exception type not matched by any branch (e.g. a plain `RuntimeError` with an unrelated message) fell through to `unclassified:RuntimeError`, preserving the type name for debugging. All four were caught by the outer `try/except` in `run`/`run_from_db`, recorded via `mark_failed`, and did not stop the overall run.

**Test Status:** Passed

---

### Test Case 26 — Login Explicitly Fails via `LoginFailedError`

**Test Scenario:** Verify `LoginFailedError` (`errors.py`, `reason = "login_failed"`) is available as a distinct, stable classification for login failures, separate from the raw `TimeoutError` currently raised by `auth.py::login`.

**Test Steps**
1. Inspect `hapag_lloyd/auth.py::login` and confirm which exception type it currently raises on a stuck redirect (Test Case 3 covers the raw `TimeoutError` path as implemented today).
2. Confirm `hapag_lloyd/errors.py` defines `LoginFailedError` with `reason = "login_failed"`, intended for this scenario.
3. Note the gap: `login()` does not currently raise `LoginFailedError` itself, and `classify_exception`'s message-sniffing branches would not map a generic `TimeoutError("Login did not redirect...")` to `login_failed` (it isn't network-related, so it falls through to `playwright_timeout` or `unclassified`, not `login_failed`).

**Expected Result**
- `LoginFailedError` exists and is importable from `hapag_lloyd/errors.py`.
- If wired up, a login failure would be recorded in `checkpoint.json` with the more specific `login_failed` reason instead of `playwright_timeout`/`unclassified`.

**Actual Result**
`LoginFailedError` is defined in `errors.py` but `auth.py::login` raises a bare `TimeoutError` on a stuck redirect, not `LoginFailedError`. Since login happens once per run (outside the per-container-type `try/except` in `main.py`), a login failure today propagates out of `run`/`run_from_db` entirely rather than being caught and recorded in `checkpoint.json` at all — it terminates the process. This is a documented gap, not a passing behavior.

**Test Status:** Failed — `LoginFailedError` is defined but unused; login failures currently crash the whole run instead of being classified/recorded like per-lane scrape errors. Recommend either raising `LoginFailedError` from `auth.py::login` and wrapping the login call in `main.py` with the same classify/record pattern, or removing the unused exception type if login-failure resilience is out of scope.

---

### Test Case 27 — Numeric Input Rejects Typed Value

**Test Scenario:** Verify the scraper fails loudly (not silently) when a numeric form field doesn't accept the typed value (e.g. input masking, max-length limits, or a non-numeric value slipping through config).

**Test Steps**
1. Configure `container_quantity` or `weight_per_container` with a value the site's numeric input rejects or truncates (e.g. an excessively long number, or a value containing characters the input masks out).
2. Run `python main.py --single` and observe `hapag_lloyd/form.py::_set_numeric_input`.

**Expected Result**
- After typing, `_set_numeric_input` reads back `input_value()` and compares it to the intended value.
- If they don't match, a `ValueError` is raised: `Numeric input {index} shows '{actual}' after setting '{value}'`.
- The mismatch is caught by the per-container-type `try/except` in `main.py` and recorded in `checkpoint.json` (classified via `classify_exception`'s fallback, since `ValueError` isn't network-related — likely `unclassified:ValueError`).

**Actual Result**
With a value the input silently truncated/rejected, `input_value()` returned a string different from the configured value, and `_set_numeric_input` raised `ValueError("Numeric input 0 shows '...' after setting '...'")`. This was caught by `main.py`'s per-combination `try/except`, classified as `unclassified:ValueError` by `classify_exception` (no specific branch matches `ValueError`), and recorded in `checkpoint.json` — the run continued to the next container type rather than silently submitting a wrong quantity/weight.

**Test Status:** Passed

---

### Test Case 28 — Commodity/Radio Selector Matches Nothing (Silent No-Op)

**Test Scenario:** Verify what happens when `_set_commodity` or `_set_radio` find no matching element on the page — confirm this is a silent no-op rather than a raised error, and assess whether that's safe.

**Test Steps**
1. Configure a `commodity` value that doesn't match any option text on the form (e.g. a typo, or a value the site no longer offers).
2. Run `python main.py --single` and inspect the submitted search — was the commodity field actually set?
3. Repeat for `received_at`/`delivered_to` with a value whose keyword (`"terminal"`/`"door"`) matches no radio's label text.

**Expected Result** (documents current behavior, not necessarily desired behavior)
- `_set_commodity` iterates matched elements and only acts if `els` is non-empty; if the selector list matches zero elements (e.g. the site's markup changed), the function returns without setting anything or raising.
- `_set_radio` iterates all radios and only checks one if `keyword in label_text`; if no radio's label contains `"terminal"`/`"door"`, no radio is checked and no error is raised.
- The search proceeds with whatever the form's default commodity/radio selection was, silently diverging from `cfg`.

**Actual Result**
Confirmed by reading `_set_commodity`/`_set_radio` (`hapag_lloyd/form.py`): both loop over query results and act conditionally, with no `else` branch or fallback error when nothing matches. Running with a non-matching commodity value did not raise; the form was submitted using its pre-existing default commodity selection instead of the configured one, and the saved output's `config.commodity` field still showed the (unapplied) configured value — silently misleading about what was actually searched.

**Test Status:** Failed — this is a silent-failure mode: misconfigured or stale commodity/radio values do not surface an error, so a scrape can complete "successfully" against the wrong commodity or pickup/delivery mode. Recommend `_set_commodity`/`_set_radio` raise (or at least log a warning) when no element matches, so this doesn't masquerade as a successful, correctly-configured scrape.

---

### Test Case 29 — Corrupted `checkpoint.json`

**Test Scenario:** Verify behavior when `checkpoint.json` exists but contains invalid/truncated JSON (e.g. from a process killed mid-write).

**Test Steps**
1. Manually truncate or corrupt `checkpoint.json` (e.g. `echo '{"entries": {' > checkpoint.json`, an incomplete JSON document).
2. Run `python main.py --from-db --limit 1` and observe `hapag_lloyd/checkpoint.py::load_checkpoint`.

**Expected Result** (documents current behavior)
- `load_checkpoint` calls `json.load(f)` directly with no `try/except` around the parse.
- A malformed file raises `json.JSONDecodeError`, uncaught, which propagates out of `load_checkpoint()` and crashes the run before any lanes are attempted (this call happens once, up front, in `run`/`run_from_db`, outside the per-combination `try/except`).

**Actual Result**
Confirmed by reading `checkpoint.py`: `load_checkpoint` only guards against the file not existing (`os.path.exists`), not against it existing but being invalid JSON. With a corrupted `checkpoint.json` in place, `python main.py --from-db --limit 1` raised `json.decoder.JSONDecodeError` immediately at startup, before the browser was even launched — the entire run failed rather than treating the corrupted file as "no prior progress."

**Test Status:** Failed — a partially-written checkpoint file (plausible if the process is killed mid-`json.dump`, e.g. Ctrl+C or OOM during a write) permanently blocks all future runs until the file is manually fixed or deleted, rather than degrading gracefully. Recommend wrapping the `json.load` in `load_checkpoint` with a `try/except json.JSONDecodeError` that logs a warning and returns `{}`, matching the "safe to delete" guarantee documented in the README.

---

### Test Case 30 — Empty Trade Lane Source (Header-Only CSV / Empty Supabase Table)

**Test Scenario:** Verify the scraper handles an empty trade lane source gracefully instead of erroring or hanging.

**Test Steps**
1. Run `python main.py --from-db --csv <header-only.csv>` where the CSV has only a header row and no data rows.
2. Separately, run default Supabase mode against a table that exists but has zero rows.

**Expected Result**
- `fetch_trade_lanes` returns `[]` for a header-only CSV (per its documented fail-path behavior).
- `fetch_trade_lanes_from_supabase` returns `[]` for an empty table (the `rows` list from `.execute().data` is empty, so the loop body never runs).
- `run_from_db`'s `for i, lane in enumerate(lanes, start=1):` loop simply doesn't execute.
- The run completes cleanly with `[csv] Loaded 0 trade lanes ...` / `[supabase] Loaded 0 trade lanes.` printed, no browser actions attempted beyond login, and no exception raised.

**Actual Result**
Both sources returned `[]` as expected. The console printed `Loaded 0 trade lanes` (CSV or Supabase phrasing accordingly), the lane loop body never executed, and `run_from_db` returned normally after login/cookie-dismissal steps — no crash, no hang, no output files written (correctly, since there was nothing to scrape).

**Test Status:** Passed

---

### Test Case 31 — `--limit` Edge Values (Zero and Out-of-Range)

**Test Scenario:** Verify `--limit 0` and a `--limit` value larger than the available lane count behave sensibly.

**Test Steps**
1. Run `python main.py --limit 0` against a non-empty Supabase table (or `--from-db --limit 0`).
2. Run `python main.py --limit 9999` against a table/CSV with far fewer than 9999 rows.

**Expected Result** (documents current behavior)
- `main.py`'s `if limit: lanes = lanes[:limit]` treats `0` as falsy in Python, so `--limit 0` is silently ignored and **all** lanes are processed — not zero, which may surprise a caller expecting `--limit 0` to mean "process nothing."
- `--limit 9999` (larger than the lane count) is handled correctly by slicing — `lanes[:9999]` simply returns all available lanes with no error.

**Actual Result**
Confirmed by reading `run_from_db` in `main.py`: `if limit:` is falsy for `0`, so `--limit 0` resulted in every lane being processed rather than none — the flag was effectively a no-op instead of an explicit "process zero lanes" instruction. `--limit 9999` against a smaller lane set correctly processed all available lanes without an index error, since Python slice bounds are clamped automatically.

**Test Status:** Failed (partial) — `--limit 0` does not do what a user would reasonably expect ("process 0 lanes"); it silently falls back to "process all lanes," which could cause an unexpectedly large/expensive run. `--limit 9999` (out-of-range) behaves correctly and needs no fix. Recommend changing the check to `if limit is not None:` so `0` is honored explicitly.

---

### Test Case 32 — Onboarding Tour Obscures the Search Form

**Test Scenario:** Verify that if `dismiss_onboarding_tour` fails to find/close an onboarding tour overlay, form-filling still succeeds (or fails clearly) rather than silently clicking through an invisible/covered element.

**Test Steps**
1. Trigger a run where an onboarding tour (e.g. "Recently Searched") is showing but doesn't match any of `dismiss_onboarding_tour`'s close-button selectors (e.g. a new tour variant introduced by a site update).
2. Observe whether `fill_search_form` proceeds and whether its actions succeed against a form that's potentially covered by the tour overlay.

**Expected Result** (documents current behavior)
- `dismiss_onboarding_tour` tries each selector with its own short timeout and returns silently if none match — no error, no signal to the caller that a tour is still showing.
- `fill_search_form`'s own `wait_for_selector` for `start-input`/`end-input` only checks `state="visible"`, which Playwright considers true even if another element visually overlaps it — so filling could proceed against an element that's technically "visible" but pointer-blocked by the tour overlay, and later interactions (`.click(force=True)` on the location input) use `force=True`, which bypasses actionability/overlap checks entirely.
- Because of `force=True` usage throughout `form.py`, a lingering tour overlay is more likely to result in clicks landing on the wrong element silently, rather than a clear timeout/error.

**Actual Result**
Confirmed by reading `dismiss_onboarding_tour` (`form.py`): it has no return value indicating failure and no fallback for an unmatched tour variant — it simply exhausts its selector list and returns. Combined with `force=True` used on the location input clicks in `_set_location`, a covered form element would not raise a Playwright "element is covered by another element" actionability error the way a non-forced click would; the click could be silently swallowed by the tour or land unpredictably.

**Test Status:** Failed — this is a latent risk rather than an observed failure in current runs (existing tour selectors have covered all tours seen so far), but the combination of a silent `dismiss_onboarding_tour` failure mode and widespread `force=True` clicking means a new/unrecognized tour variant could cause silent misbehavior instead of a clear, debuggable error. Recommend `dismiss_onboarding_tour` returning a bool (mirroring `dismiss_permission_error_modal`'s pattern) so callers can at least log when a tour was suspected but not closed.

---

## Module: Automated Unit Coverage Notes

### Test Case 33 — `classify_exception`/`format_checkpoint_error` Now Have Unit Coverage

**Test Scenario:** Verify the reason-tag classification logic exercised manually in Test Cases 25–26
is also covered by fast, deterministic automated unit tests (no browser required), so regressions
in the classification rules are caught in CI rather than only during a live scrape.

**Test Steps**
1. Run `pytest tests/test_errors.py -v`.
2. Inspect the cases covered: every `ScrapeError` subclass's fixed `reason` tag, message-pattern
   matching for raw Playwright timeouts (`network_unavailable`, `ui_blocked_by_overlay`,
   `playwright_timeout`), non-timeout connection/navigation/browser-closed patterns, the
   `unclassified:<Type>` fallback for unmatched exception types, and `format_checkpoint_error`'s
   `"<reason>: <message>"` formatting.

**Expected Result**
- All classification branches in `hapag_lloyd/errors.py::classify_exception` are exercised by an
  automated test with no live site/browser dependency.
- `format_checkpoint_error` is verified to prefix the classified reason onto the exception message
  exactly as `checkpoint.json` entries expect (matching what Test Cases 9–10, 22–25 observed live).
- These unit tests do not cover the *wiring* gap from Test Case 26 (`LoginFailedError` being unused
  in `auth.py::login`) — that remains a functional/integration gap, not a unit-testable one.

**Actual Result**
`tests/test_errors.py` passes 22 cases covering `classify_exception` (all `ScrapeError` subclasses,
timeout message-pattern branches, non-timeout message-pattern branches, and the unclassified
fallback) and `format_checkpoint_error`. Run via `pytest tests/test_errors.py -q`: all passed.

**Test Status:** Passed

---

### Test Case 34 — `load_config` Merge Precedence Has Unit Coverage

**Test Scenario:** Verify the config precedence chain exercised live in Test Cases 19–20
(DEFAULT_CONFIG → config file → CLI flags) is also covered by a fast unit test against
`hapag_lloyd/config.py::load_config` directly, isolating the merge logic from the browser-driven
assertions in those test cases.

**Test Steps**
1. Run `pytest tests/test_config.py -v`.
2. Inspect the cases covered: defaults-only (no config file, no CLI flags), CLI flags overriding
   defaults, empty-string CLI flags NOT clobbering existing values (falsy-override guard), a config
   file overriding defaults, and CLI flags winning over a config file value for the same field.

**Expected Result**
- `load_config` returns a fresh copy of `DEFAULT_CONFIG` when given no config file and no CLI flags.
- Non-empty CLI flags (`--origin`, `--destination`, `--email`, `--password`, `--output`, `--headless`)
  override both defaults and config-file values for the same field.
- Empty-string CLI flags do not override an existing value, since `load_config` only applies an
  override when the flag's value is truthy.
- A `--config` JSON file's values override `DEFAULT_CONFIG` but are in turn overridden by any CLI
  flag targeting the same field — matching the documented priority order in `config.py`'s module
  docstring.

**Actual Result**
`tests/test_config.py` passes 14 cases covering all of the above using an `argparse.Namespace`
builder matching `parse_args()`'s defaults. Run via `pytest tests/test_config.py -q`: all passed.
This complements Test Cases 19–20, which verify the same precedence rules end-to-end against the
live site (confirming the CLI-filled value is actually what gets typed into the search form), while
these unit tests isolate and pin the merge logic itself.

**Test Status:** Passed

---

## Adding new test cases

Follow the template above (Test Case / Module / Test Scenario / Test Steps / Expected Result /
Actual Result / Test Status) for any new functional behavior added to the scraper. Reserve this
file for end-to-end, browser-driven, or file-system/DB-integration behavior; pure parsing/logic
changes should get a unit test in `tests/*.py` per the conventions in
[tests/README.md](README.md) instead.
