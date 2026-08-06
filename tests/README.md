# Tests

Unit tests for the pure data-parsing logic in `hapag_lloyd/`. These do not launch a browser, hit the network, or need credentials — they run against static input data (dicts, CSV text) and assert on the parsed output.

Each function under test has two test classes: a `...HappyPath` class covering well-formed input, and a `...FailPath` class covering missing fields, malformed shapes, empty input, and other edge cases — asserting that the code degrades gracefully (`None`/`""`/`{}`/skipped entries) rather than raising, except where raising is the documented, intended behavior (e.g. a missing CSV file).

## Running

From the project root:

```bash
pytest
```

Run a single file, class, or test:

```bash
pytest tests/test_api_parser.py
pytest tests/test_api_parser.py::TestParseChargeGroups
pytest tests/test_api_parser.py::TestParseChargeGroups::test_flattens_groups
```

## Files

### `test_api_parser.py`

Covers `hapag_lloyd/extractors/api_parser.py` — turning raw captured API requests/responses into the structured `api_data` block saved in each output file.

| Function under test | Happy path | Fail path |
|---|---|---|
| `_coerce_port` | String passthrough; dict resolves via `locationName`/`name`/`portName` before falling back to `locode`/`code`/`id`; non-string values are stringified. | `None`, `{}`, a dict with only unrecognized keys, or all-falsy values all return `""` instead of raising; unsupported types (`int`, `list`) also return `""`. |
| `_extract_top_level` | Requested keys present are copied through, in insertion order of the source dict. | Missing keys are silently omitted; empty `data` or empty `keys` both return `{}`. |
| `_extract_route_from_request` | Finds origin/destination as top-level keys, inside `routings[0]`, or nested in an arbitrary sub-dict; dict-valued ports are run through `_coerce_port`; top-level keys win over nested matches; a route with only one side present still returns that side. | No matching keys anywhere, only unrelated keys, an empty `routings` list, or a non-dict first `routings` element all return `{}`/partial results without raising. |
| `_parse_charge_groups` | Flattens one or many charge groups/charges into `{group, name, code, currency, containers}` records; `label` is preferred over `name` for the group field, `name` is used when `label` is absent. | Non-dict groups are skipped; empty input, a missing `data` key, or an empty `data` list all produce `[]`; a charge missing optional fields still produces a record with `None`s rather than a `KeyError`. |
| `_parse_offer_v4` | Route read from `request.routings[0]`, falling back to `offer.routing`; container/commodity/`validFrom` fields extracted from `cargoDetails`; `departures` parsed from `offer.items`. | Completely empty payload returns empty strings/list, not an exception; missing `cargoDetails` simply omits those keys; non-dict entries in `offer.items` are skipped; a missing `items` key yields `departures: []`. |
| `_parse_offer_item` | Extracts `departureDate` and parses each entry in `productOffers`, in order, for multiple offers per departure. | Missing `productOffers` key returns `[]`; non-dict entries in the list are skipped; a missing `departureDate` returns `None` rather than raising. |
| `_parse_product_offer` | Extracts pricing metadata fields; parses `legs` with `_coerce_port`-normalized locations; prefers the `USD` charges section over `LOCAL`; extracts `ocean_freight_per_container` from the `SEA_FREIGHT` group. | Empty payload yields all-`None` metadata; missing/empty `legs` omits the `legs` key entirely (not `[]`); missing `sections` yields empty `charges` and no `ocean_freight_per_container` key; a `sections` dict without a `SEA_FREIGHT` group, or one with an empty `data` list, both omit `ocean_freight_per_container` rather than raising `IndexError`. |
| `parse_api_responses` | Assembles `search_request` (from either a v3 or v4 offer request body), `offer_created`, `offer_status` (first one only, deduplicated), and `offer_v4` from a mixed batch of captured responses; all four keys can be populated together; a `/status` URL is never misclassified as a v4 offer endpoint. | No input returns `{}`; `None` request bodies default to `{}` without raising; non-dict `data`, an unrecognized URL, or a response missing its `url`/`data` key are all ignored; a request body URL that doesn't match a known offer endpoint leaves `search_request` unset. Also documents that a v4 URL whose response is missing `data` entirely still parses into an empty-shell `offer_v4` (`data` defaults to `{}`, which is a dict, so it isn't treated as malformed the way a non-dict `data` value is). |

### `test_trade_lanes.py`

Covers `hapag_lloyd/trade_lanes.py` — loading the route list used by `--from-db` / `--from-supabase`.

| Function under test | Happy path | Fail path |
|---|---|---|
| `_parse_trade_lane` | Splits `"Origin - Destination"` on the first `" - "` separator; hyphens inside the destination name survive because only the first separator is used; whitespace around each side is stripped. | Returns `None` (never raises) for a missing separator, an empty origin or destination side, an empty string, or a bare `"-"`. |
| `_normalize_port` | Maps known aliases/terminal codes (`JNPT`, `NHAVA SHEVA`, `Antwerpen`, `Pipavav (Victor) Port`, `NSIGT`, `NSICT`, `BMCT`) to the port name the Hapag-Lloyd site's search recognizes. | Unknown names and empty strings pass through unchanged; the lookup is documented as case-sensitive, so a differently-cased alias (`"jnpt"`) is *not* mapped — this is current behavior, not a guarantee it's the desired one. |
| `fetch_trade_lanes` | Reads a CSV into normalized, `shipment_count`-descending-sorted lane dicts; applies `PORT_NAME_MAP` to each side; ties in `shipment_count` preserve original row order (stable sort). | Rows with no separator or an empty `trade_lane` are skipped, not fatal; a missing or non-numeric `shipment_count` defaults to `0`; a header-only CSV returns `[]`; a missing file path raises `FileNotFoundError` (the one case that *is* expected to raise). Uses pytest's `tmp_path` fixture to write throwaway CSV files rather than relying on `trade_lanes_all.csv`. |

### `test_utils.py`

Covers the synchronous helpers in `hapag_lloyd/extractors/utils.py`.

| Function under test | Happy path | Fail path |
|---|---|---|
| `parse_amount` | Extracts a float from a plain decimal or integer string, a string with a currency prefix (`"USD 10.00"`), one with thousands separators (`"17,805.00"` or `"1,234,567.89"`), surrounding whitespace, or trailing non-numeric text. | Returns `None` (never raises) for a string with no digits, an empty string, a whitespace-only string, or a currency code with no accompanying number. |

### `test_checkpoint.py`

Covers `hapag_lloyd/checkpoint.py` — the resume/skip mechanism used by `main.py` so a re-run doesn't re-scrape routes it already completed.

| Function under test | Happy path | Fail path |
|---|---|---|
| `_key` | Builds a `"ORIGIN|DEST|CONTAINER"` key that's uppercased and whitespace-trimmed on each part, so lookups are insensitive to input casing/spacing; different container types or swapped origin/destination produce distinct keys. | N/A — pure string formatting, nothing to fail. |
| `load_checkpoint` | Reads back the `{key: entry}` map written by `mark_success`/`mark_failed`, including multiple accumulated entries. | A missing checkpoint file returns `{}` instead of raising; a file whose top-level JSON has no `"entries"` key also degrades to `{}` (via `dict.get` default) rather than `KeyError`. |
| `is_done` | Returns `True` only for a key recorded with `status: "success"`; lookup is case/whitespace-insensitive via `_key`. | Returns `False` (never raises) for an absent key, a `"failed"` entry (so it gets retried), or an entry dict with no `status` field at all. |
| `mark_success` | Records a `"success"` entry (with `scraped_at`, no `error` field) in the in-memory dict and persists it to `path` immediately, so a reload sees it; marking success after a prior failure flips `is_done` to `True`. | N/A — always succeeds; the write is the thing under test. |
| `mark_failed` | Records a `"failed"` entry with the given `error` message, both in-memory and persisted to disk; the route stays `is_done() == False` so it will be retried next run. | An empty/default `error=""` is dropped entirely rather than stored as `""` (since `_record` only sets the key when the value is truthy). |
| *(resume scenario)* | An end-to-end style test drives `load_checkpoint` → `is_done` → `mark_success` → reload, mirroring exactly how `main.py` uses this module across two runs. | — |

### `test_output.py`

Covers `hapag_lloyd/output.py` — building the output file path and assembling/saving the final JSON payload.

| Function under test | Happy path | Fail path |
|---|---|---|
| `make_output_path` | Builds `output/ORIGIN_to_DEST_CONTAINER_YYYY-MM-DD_HH-MM-SS.json` from `cfg`; respects a custom `folder`; slugifies special characters/spaces/accents in location names; timestamp suffix matches the expected fixed-width format. | Missing `start_location`/`end_location` fall back to `"ORIGIN"`/`"DEST"` placeholders; a missing or empty-string `container_type` omits that path segment entirely rather than leaving a stray `_`. |
| `save_json` | Writes pretty-printed (`indent=2`), non-ASCII-preserving (`ensure_ascii=False`) JSON; creates missing parent directories; overwrites an existing file at the same path. | A bare filename with no directory component (`os.path.dirname(path)` returns `""`) does not raise — `folder or "."` covers it. |
| `build_output` | Assembles the four top-level keys (`config`, `api_data`, `visual_data`, `api_responses`); non-credential config fields pass through unchanged. | `email`/`password` are always stripped from the saved `config`; a missing or explicit `None` `api_data` both default to `{}`. |

### `test_results.py`

Covers the pure API-fallback helpers in `hapag_lloyd/extractors/results.py` — used when DOM scraping of the offer selection page yields nothing and the code falls back to the already-parsed `offer_v4` API data. (`scrape_results_page` and `_extract_route` itself are Playwright-driven and excluded, per the project convention below.)

| Function under test | Happy path | Fail path |
|---|---|---|
| `_route_from_api` | Joins `originPort`/`destinationPort` into an en-dash-separated `"ORIGIN – DEST"` display string. | Returns `None` (never raises) if either side is missing, both are missing, or a port value is present but falsy (`""`). |
| `_quick_quote_from_api` | Extracts `validFrom` plus `ocean_freight_per_container` from the **first** departure's **first** product offer only. | Returns `{}` for an empty payload, no departures, or a departure with no product offers; a missing `ocean_freight_per_container` key is simply omitted while `validFrom` is still included. |
| `_price_breakdown_from_api` | Extracts the `charges` list from the first departure's first product offer only. | Returns `{}` for an empty payload, no departures, or no product offers; a missing `charges` key on the offer itself yields `{"charges": []}` rather than `KeyError`. |

### `test_network.py`

Covers the synchronous parts of `hapag_lloyd/network.py`'s `NetworkCapture` — construction and `has_v4_offer()`. The keyword-filtered request/response listeners (`_on_request`/`_on_response`) require a live Playwright `Page`/`Request`/`Response` and are exercised end-to-end rather than unit tested here.

| Function under test | Happy path | Fail path |
|---|---|---|
| `NetworkCapture()` (init) | `responses` and `request_bodies` both start empty. | N/A |
| `has_v4_offer` | `True` once any captured response URL contains `/api/v4/offers/` and not `/status` — whether it's the only response or one of several. | `False` for an empty capture, `v3`-only responses, or a `/api/v4/offers/{id}/status` polling URL (explicitly excluded so in-flight polling isn't mistaken for the final priced offer). |

## Adding new tests

These tests intentionally target only the pure/synchronous parsing functions — nothing that drives Playwright, logs in, or calls Supabase/MongoDB. If you add a new pure helper (e.g. another `extractors/utils.py` function or another `api_parser.py` branch), add a test class/file following the naming pattern above (`Test<FunctionOrArea>`) rather than testing it end-to-end through the scraper.
