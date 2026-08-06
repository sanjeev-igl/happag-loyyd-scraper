"""Configuration defaults, file loading, and CLI argument parsing.

Priority (lowest → highest):
    DEFAULT_CONFIG → .env / environment variables → config JSON file → CLI flags
"""

import argparse
import json
import os

from dotenv import load_dotenv

load_dotenv()  # no-op if .env is absent

QUOTE_URL = "https://www.hapag-lloyd.com/solutions/new-quote/"

# Hapag-Lloyd uses different internal codes for container types.
# Map user-friendly labels → HL API codes so the config value matches
# what the API actually submits.
CONTAINER_TYPE_MAP: dict[str, str] = {
    "20DC": "22G0",
    "20GP": "22G0",
    "40DC": "42G0",
    "40GP": "42G0",
    "40HC": "45GP",   # HL codes 40' High Cube as 45GP internally
    "40HQ": "45GP",
    "45HC": "L5G0",
}

# The container type picker on the search form is a two-level accordion:
# a group header (e.g. "GENERAL PURPOSE") that expands to reveal individual
# container rows. Every selectable row (Tank is excluded — it's disabled,
# "Available only with SOC"), in accordion order.
CONTAINER_TYPES: list[dict[str, str]] = [
    {"group": "General Purpose", "label": "20' General Purpose"},
    {"group": "General Purpose", "label": "40' General Purpose"},
    {"group": "General Purpose", "label": "40' General Purpose High Cube"},
    {"group": "Operating Reefer", "label": "20' Operating Reefer"},
    {"group": "Operating Reefer", "label": "40' Operating Reefer"},
    {"group": "Non-Operating Reefer", "label": "40' Non-operating Reefer"},
    {"group": "Open Top", "label": "20' Open Top (in-gauge)"},
    {"group": "Open Top", "label": "40' Open Top (in-gauge)"},
    {"group": "Open Top", "label": "20' High Cube Open Top (in-gauge)"},
    {"group": "Open Top", "label": "40' High Cube Open Top (in-gauge)"},
    {"group": "Flatrack", "label": "20' Flatrack (in-gauge)"},
    {"group": "Flatrack", "label": "40' Flatrack (in-gauge)"},
    {"group": "Flatrack", "label": "40' High Cube Flatrack (in-gauge)"},
    {"group": "Hard Top", "label": "40' High Cube Hard Top (in-gauge)"},
]

DEFAULT_CONFIG: dict = {
    "email": os.getenv("HL_EMAIL", ""),
    "password": os.getenv("HL_PASSWORD", ""),
    "start_location": os.getenv("HL_ORIGIN", "NHAVA SHEVA"),
    "end_location": os.getenv("HL_DESTINATION", "SINGAPORE"),
    "received_at": os.getenv("HL_RECEIVED_AT", "terminal"),   # "terminal" | "door"
    "delivered_to": os.getenv("HL_DELIVERED_TO", "terminal"),  # "terminal" | "door"
    "valid_from": os.getenv("HL_VALID_FROM", ""),              # YYYY-MM-DD; empty = today
    "container_type": os.getenv("HL_CONTAINER_TYPE", "40HC"),
    "container_quantity": os.getenv("HL_CONTAINER_QTY", "1"),
    "weight_per_container": os.getenv("HL_WEIGHT", "20000"),
    "weight_unit": os.getenv("HL_WEIGHT_UNIT", "kg"),          # "kg" | "lb"
    "commodity": os.getenv("HL_COMMODITY", "FAK"),
    "headless": os.getenv("HL_HEADLESS", "").lower() in ("1", "true", "yes"),
    "output_file": os.getenv("HL_OUTPUT", "output/hapag_lloyd_quotes.json"),
    "slow_mo": int(os.getenv("HL_SLOW_MO", "100")),
}

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_TRADE_LANES_TABLE = os.getenv("SUPABASE_TRADE_LANES_TABLE", "trade_lanes")

MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB = os.getenv("MONGO_DB", "")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "")


def load_config(args: argparse.Namespace) -> dict:
    """Merge DEFAULT_CONFIG ← config file ← CLI flags (highest priority last)."""
    cfg = dict(DEFAULT_CONFIG)

    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg.update(json.load(f))

    overrides = {
        "headless": args.headless or cfg["headless"],
        "email": args.email or cfg["email"],
        "password": args.password or cfg["password"],
        "start_location": args.origin or cfg["start_location"],
        "end_location": args.destination or cfg["end_location"],
        "output_file": args.output or cfg["output_file"],
    }
    cfg.update({k: v for k, v in overrides.items() if v})
    if args.headless:
        cfg["headless"] = True

    return cfg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hapag-Lloyd freight quote scraper")
    parser.add_argument("--config", help="Path to JSON config file", default=None)
    parser.add_argument("--headless", action="store_true", default=False)
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--origin", default="")
    parser.add_argument("--destination", default="")
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--from-db", action="store_true", default=False,
        help="Loop over every route in the trade lanes CSV instead of Supabase.",
    )
    parser.add_argument(
        "--from-supabase", action="store_true", default=False,
        help="Loop over every route in the Supabase trade_lanes table. This is the default.",
    )
    parser.add_argument(
        "--single", action="store_true", default=False,
        help="Scrape a single route from config.json/.env instead of looping over Supabase/CSV.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="With --from-db/--from-supabase, only process the top N lanes (by shipment_count).",
    )
    parser.add_argument(
        "--csv", default="trade_lanes_all.csv",
        help="Path to the trade lanes CSV file (used with --from-db). Default: trade_lanes_all.csv",
    )
    return parser.parse_args()
