"""Fetch trade lanes (origin/destination routes) from a local CSV file."""

import csv
import re

_DEFAULT_CSV_PATH = "trade_lanes_all.csv"

# The Hapag-Lloyd location search doesn't recognize these CSV values directly
# (terminal codes / alternate spellings) — map them to a name it does recognize.
# Verified against the live site's autocomplete.
PORT_NAME_MAP: dict[str, str] = {
    "JNPT": "Nhava Sheva",
    "NHAVA SHEVA": "Nhava Sheva",
    "Antwerpen": "Antwerp",
    "Pipavav (Victor) Port": "Pipavav",
    # NSIGT / NSICT / BMCT are terminals within the Nhava Sheva port complex;
    # the site has no distinct entry for them, so approximate with the port name.
    "NSIGT": "Nhava Sheva",
    "NSICT": "Nhava Sheva",
    "BMCT": "Nhava Sheva",
}


def _normalize_port(name: str) -> str:
    return PORT_NAME_MAP.get(name, name)


def fetch_trade_lanes(csv_path: str = _DEFAULT_CSV_PATH) -> list[dict]:
    """Return all trade lane rows as
    [{"start_location": ..., "end_location": ..., "shipment_count": ...}],
    ordered by shipment_count descending. Location names are normalized via
    PORT_NAME_MAP so they match what the Hapag-Lloyd site's search recognizes."""
    lanes: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trade_lane = (row.get("trade_lane") or "").strip()
            if not trade_lane:
                continue
            parsed = _parse_trade_lane(trade_lane)
            if not parsed:
                continue
            origin, dest = parsed
            count_raw = (row.get("shipment_count") or "0").strip()
            try:
                count = int(count_raw)
            except ValueError:
                count = 0
            lanes.append({
                "start_location": _normalize_port(origin),
                "end_location": _normalize_port(dest),
                "shipment_count": count,
            })

    lanes.sort(key=lambda lane: lane["shipment_count"], reverse=True)
    return lanes


def fetch_trade_lanes_from_supabase(
    table: str | None = None, url: str | None = None, key: str | None = None,
) -> list[dict]:
    """Same shape as fetch_trade_lanes(), but reads trade_lane/shipment_count rows
    from a Supabase table instead of a local CSV."""
    from supabase import create_client

    from hapag_lloyd.config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_TRADE_LANES_TABLE

    url = url or SUPABASE_URL
    key = key or SUPABASE_KEY
    table = table or SUPABASE_TRADE_LANES_TABLE
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set (in .env or passed explicitly).")

    client = create_client(url, key)
    rows = client.table(table).select("trade_lane, shipment_count").execute().data

    lanes: list[dict] = []
    for row in rows:
        trade_lane = (row.get("trade_lane") or "").strip()
        if not trade_lane:
            continue
        parsed = _parse_trade_lane(trade_lane)
        if not parsed:
            continue
        origin, dest = parsed
        lanes.append({
            "start_location": _normalize_port(origin),
            "end_location": _normalize_port(dest),
            "shipment_count": int(row.get("shipment_count") or 0),
        })

    lanes.sort(key=lambda lane: lane["shipment_count"], reverse=True)
    return lanes


def _parse_trade_lane(trade_lane: str) -> tuple[str, str] | None:
    """Split "Origin - Destination" into (origin, destination). Splits on the first
    ' - ' separator with surrounding spaces so port names containing hyphens survive."""
    parts = re.split(r"\s+-\s+", trade_lane.strip(), maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0].strip(), parts[1].strip()
