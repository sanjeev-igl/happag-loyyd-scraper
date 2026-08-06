# Hapag-Lloyd Freight Quote Scraper

Automates freight quote retrieval from [hapag-lloyd.com](https://www.hapag-lloyd.com) using Playwright, driving a [Camoufox](https://github.com/daijro/camoufox) (patched Firefox) browser to get past the site's Cloudflare Managed Challenge. Logs in, fills the quote search form for every container type on a route, captures the results (both visually and via the site's own API responses), and saves them to JSON, MongoDB, or both.

The scraper can run a single origin/destination route, or loop unattended over a full list of trade lanes pulled from Supabase or a local CSV — resuming safely via a checkpoint file if interrupted.

---

## Requirements

- Python 3.9+
- pip

---

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Fetch the Camoufox browser

```bash
python -m camoufox fetch
```

This downloads the patched Firefox build Camoufox launches (~500MB), separate from `pip install`. Run it once per machine/CI runner.

### 3. Configure credentials and storage

Copy or edit the `.env` file in the project root:

```env
# Hapag-Lloyd login
HL_EMAIL=your-email@example.com
HL_PASSWORD=your-password

# Optional defaults (all overridable via config.json / CLI flags)
HL_ORIGIN=NHAVA SHEVA
HL_DESTINATION=SINGAPORE
HL_RECEIVED_AT=terminal
HL_DELIVERED_TO=terminal
HL_VALID_FROM=
HL_CONTAINER_TYPE=40HC
HL_CONTAINER_QTY=1
HL_WEIGHT=20000
HL_WEIGHT_UNIT=kg
HL_COMMODITY=FAK
HL_HEADLESS=false
HL_OUTPUT=output/hapag_lloyd_quotes.json
HL_SLOW_MO=100

# Trade lane source (used when NOT running --single)
SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_TRADE_LANES_TABLE=trade_lanes

# Optional: also persist every scraped result to MongoDB
MONGO_URI=
MONGO_DB=
MONGO_COLLECTION=
```

> **Never commit `.env` to version control.** It is already in `.gitignore`.

- **Supabase** is only required for the default multi-lane mode (`python main.py`). It supplies the list of `trade_lane` / `shipment_count` rows to loop over.
- **MongoDB** is optional. If `MONGO_URI`, `MONGO_DB`, and `MONGO_COLLECTION` are all set, every scraped result is also inserted into that collection in addition to being saved as JSON.

---

## Configuration

Quote parameters for a single-route run are set via **three methods** (higher in the list = higher priority):

| Priority | Method |
|----------|--------|
| 1 (highest) | CLI flags |
| 2 | `config.json` file |
| 3 | `.env` / environment variables |

### config.json

Edit `config.json` to set default search parameters:

```json
{
  "email": "your-email@example.com",
  "password": "your-password",
  "start_location": "NHAVA SHEVA",
  "end_location": "SINGAPORE",
  "received_at": "terminal",
  "delivered_to": "terminal",
  "valid_from": "2026-06-25",
  "container_type": "40HC",
  "container_quantity": "1",
  "weight_per_container": "20000",
  "weight_unit": "kg",
  "commodity": "FAK",
  "headless": false,
  "output_file": "hapag_lloyd_quotes.json",
  "slow_mo": 120
}
```

| Field | Description | Example values |
|-------|-------------|----------------|
| `start_location` | Origin port | `"NHAVA SHEVA"`, `"SHANGHAI"` |
| `end_location` | Destination port | `"SINGAPORE"`, `"ROTTERDAM"` |
| `received_at` | Cargo pickup mode | `"terminal"` or `"door"` |
| `delivered_to` | Cargo delivery mode | `"terminal"` or `"door"` |
| `valid_from` | Quote date | `"YYYY-MM-DD"` (empty = today) |
| `container_type` | Container size/type | `"20GP"`, `"40HC"`, `"40GP"` |
| `container_quantity` | Number of containers | `"1"` |
| `weight_per_container` | Weight per container | `"20000"` |
| `weight_unit` | Weight unit | `"kg"` or `"lb"` |
| `commodity` | Commodity code | `"FAK"` (Freight All Kinds) |
| `headless` | Run browser invisibly | `true` or `false` |
| `output_file` | Output JSON path (single-route mode only) | `"quotes.json"` |
| `slow_mo` | Delay between actions (ms) | `120` |

Note: in multi-lane modes (`--from-db` / default Supabase mode), `container_type` is ignored — the scraper loops over **every** container type defined in `CONTAINER_TYPES` (`hapag_lloyd/config.py`) for each route.

---

## Running

The scraper has two modes: a **single route** (one origin/destination, from `config.json`/`.env`), or **looping over many routes** pulled from Supabase or a CSV file.

### Single route

```bash
python main.py --single
python main.py --single --config config.json
python main.py --single --output results.json
```

Scrapes one origin/destination pair (from config/CLI) across every container type in `CONTAINER_TYPES`.

### Loop over Supabase trade lanes (default)

```bash
python main.py
python main.py --limit 20        # only the top 20 lanes by shipment_count
```

Fetches routes from the Supabase table configured via `SUPABASE_TRADE_LANES_TABLE` and loops through every route × container type combination.

### Loop over a local CSV instead

```bash
python main.py --from-db
python main.py --from-db --csv other_lanes.csv
```

Reads routes from `trade_lanes_all.csv` (or the `--csv` path given), formatted with `trade_lane` (`"Origin - Destination"`) and `shipment_count` columns. Certain known terminal codes / alternate names (e.g. `JNPT`, `NSIGT`, `Antwerpen`) are normalized to the port names the Hapag-Lloyd site's search recognizes — see `PORT_NAME_MAP` in `hapag_lloyd/trade_lanes.py`.

### All CLI options

```
--config        Path to JSON config file
--origin        Origin port name
--destination   Destination port name
--email         Hapag-Lloyd account email
--password      Hapag-Lloyd account password
--output        Output JSON file path (--single mode only)
--headless      Run browser in headless (invisible) mode
--single        Scrape one route from config.json/.env instead of looping
--from-db       Loop over every route in a trade lanes CSV instead of Supabase
--from-supabase Loop over every route in the Supabase trade_lanes table (default)
--limit N       With --from-db/--from-supabase, only process the top N lanes (by shipment_count)
--csv PATH      Path to the trade lanes CSV file (used with --from-db). Default: trade_lanes_all.csv
```

If no email/password is configured, the scraper opens the browser and waits for you to log in manually before continuing.

---

## Resuming interrupted runs (checkpointing)

Every successful `(route, container type)` scrape is recorded in `checkpoint.json` as soon as it completes. If a run is interrupted and restarted, already-succeeded combinations are skipped automatically; failed combinations are always retried. Delete `checkpoint.json` to force a full re-scrape.

---

## Output

### JSON files

In multi-lane modes, one JSON file per `(route, container type)` is written to `output/`, named `ORIGIN_to_DEST_CONTAINERTYPE_YYYY-MM-DD_HH-MM-SS.json`. In `--single` mode with an explicit `--output`, results are written to that single path instead.

Each output file contains:

```json
{
  "config": { "...search parameters used (credentials stripped)..." },
  "api_data": { "...structured data parsed from captured API responses..." },
  "visual_data": { "...data scraped directly from the results page DOM..." },
  "api_responses": [ "...raw API responses captured during the session..." ]
}
```

### MongoDB

If Mongo is configured (see [Setup](#3-configure-credentials-and-storage)), every scraped result is also inserted as a document into the configured collection, in addition to the JSON file.

---

## Project structure

```
main.py                        Entry point: single-route and multi-lane run loops
hapag_lloyd/
  config.py                    Defaults, .env/config.json/CLI merging, container type map
  browser.py                   Camoufox browser + Playwright context/page setup
  auth.py                      Login (credentialed + manual fallback)
  form.py                      Search form filling, cookie/onboarding/error-modal dismissal
  network.py                   Captures API requests/responses made during the session
  extractors/
    results.py                 Waits for and scrapes the results page
    api_parser.py               Parses captured API responses into structured data
    quick_quote.py, price_breakdown.py, offer_grid.py, utils.py
  output.py                     Assembles and saves the output JSON
  mongo_store.py                Optional MongoDB persistence
  trade_lanes.py                 Loads trade lanes from Supabase or CSV
  checkpoint.py                 Tracks completed (route, container type) combinations
tests/                          Pytest unit tests (api_parser, trade_lanes, utils)
trade_lanes_all.csv             Local trade lane list used by --from-db
config.json                     Default single-route search parameters
checkpoint.json                 Auto-generated resume state (safe to delete)
```

---

## Tests

Unit tests cover the pure data-parsing logic (API response parsing, trade lane CSV parsing, extractor utils) and don't require a browser or network access:

```bash
pytest
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: playwright` or `camoufox` | Run `pip install -r requirements.txt` |
| Browser not found / launch error | Run `python -m camoufox fetch` |
| Login fails | Check credentials in `.env` or `config.json` |
| No results returned | Try with `"headless": false` to watch the browser and debug form filling |
| Slow / timing errors | Increase `slow_mo` in `config.json` (e.g. `200`) |
| `SUPABASE_URL and SUPABASE_KEY must be set` | Set both in `.env`, or run with `--from-db` to use the local CSV instead |
| `MONGO_URI, MONGO_DB, and MONGO_COLLECTION must be set` | Set all three in `.env`, or don't rely on Mongo persistence — JSON files are always saved regardless |
| A route/container type fails with "missing permissions" | The account isn't entitled to quote that route/container combination; the scraper marks it failed in `checkpoint.json` and moves on |
