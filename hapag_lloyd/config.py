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
    return parser.parse_args()
