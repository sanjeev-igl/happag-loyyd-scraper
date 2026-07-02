"""Push scraped Hapag-Lloyd output files into MongoDB.

Usage:
    python push_to_mongo.py                    # process all files in output/
    python push_to_mongo.py output/file.json   # process a specific file
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "spot_pricing")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "happag_loyyd_spot_pricing")


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fmt_datetime(iso_str: str | None) -> str:
    """'2026-07-13T06:30:00.000+0000' -> '13-Jul-2026 06:30' (matches existing sailings docs)."""
    if not iso_str:
        return ""
    try:
        dt = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        return iso_str
    return dt.strftime("%d-%b-%Y %H:%M")


def _to_number(v, cast):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


def _is_available(product: dict | None, requested_code: str | None) -> bool:
    if not product or product.get("errorReason"):
        return False
    for container in product.get("containers", []):
        if container.get("containerType") == requested_code and not container.get("errorReason"):
            return True
    return False


def _build_price(product: dict | None) -> dict | None:
    """Headline ocean-freight price (SEA_FREIGHT charge), per container type."""
    if not product:
        return None
    for section in product.get("sections", {}).get("LOCAL", []):
        if section.get("name") == "SEA_FREIGHT" and section.get("data"):
            charge = section["data"][0]
            return {
                "currency": charge.get("currency"),
                "ocean_freight_per_container": {
                    c["containerType"]: c["amount"] for c in charge.get("containers", [])
                },
            }
    return None


def _build_breakdown(product: dict | None) -> list[dict]:
    """Flatten every LOCAL charge line (freight + export/import surcharges) per container type."""
    if not product:
        return []
    breakdown = []
    for section_type, section_list in product.get("sections", {}).items():
        for section in section_list:
            for charge in section.get("data", []):
                for container in charge.get("containers", []):
                    breakdown.append({
                        "section_type": section_type,
                        "section_name": section.get("name"),
                        "section_label": section.get("label"),
                        "charge_name": charge.get("name"),
                        "charge_code": charge.get("code"),
                        "currency": charge.get("currency"),
                        "container_type": container.get("containerType"),
                        "amount": container.get("amount"),
                        "is_considered_for_total": container.get("isConsideredForTotal"),
                    })
    return breakdown


def _build_tags(basic: dict | None, premium: dict | None) -> list[str]:
    tags = []
    if basic and basic.get("errorReason"):
        tags.append("basic_restricted")
    if premium and premium.get("errorReason"):
        tags.append("spot_restricted")
    return tags


def extract_sailings(data: dict, source_file: str) -> list[dict]:
    """One doc per departure date, merging QQ_MONTHLY (basic) + SPOT (premium) tiers."""
    sailings = []

    offer_v4_response = None
    for resp in data.get("api_responses", []):
        r_data = resp.get("data", {})
        if isinstance(r_data, dict) and "offer" in r_data and "items" in r_data.get("offer", {}):
            offer_v4_response = r_data
            break

    if not offer_v4_response:
        return sailings

    offer = offer_v4_response.get("offer", {})
    routing = offer.get("routing", {})
    origin = routing.get("startLocation", {})
    destination = routing.get("destinationLocation", {})
    scraped_at = data.get("visual_data", {}).get("scraped_at")
    config = data.get("config", {})
    requested_code = config.get("container_type_api_code")

    for item in offer.get("items", []):
        products = {p.get("productType"): p for p in item.get("productOffers", [])}
        basic = products.get("QQ_MONTHLY")
        premium = products.get("SPOT")
        primary = basic or premium
        if not primary:
            continue

        leg = (primary.get("legs") or [{}])[0]

        sailing = {
            "carrier": "HAPAG-LLOYD",

            "pol_locode": origin.get("locode"),
            "pol": ", ".join(p for p in (origin.get("locationName"), origin.get("countryCode")) if p),
            "pod_locode": destination.get("locode"),
            "pod": ", ".join(p for p in (destination.get("locationName"), destination.get("countryCode")) if p),

            "vessel": leg.get("vesselName"),
            "voyage": leg.get("voyageNumber"),
            "service": leg.get("serviceName"),

            "etd": fmt_datetime(leg.get("departureDateTime")),
            "eta": fmt_datetime(leg.get("arrivalDateTime")),
            "duration_days": primary.get("estimatedDaysOfTransport"),
            "doc_cutoff": fmt_datetime(primary.get("documentationClosureDateTime")),
            "vgm_cutoff": fmt_datetime(primary.get("verifiedGrossMassDatetime")),
            "last_gate_in": fmt_datetime(primary.get("cutOffDateTime")),

            "container_type_requested": config.get("container_type"),
            "container_quantity": _to_number(config.get("container_quantity"), int),
            "weight_per_container": _to_number(config.get("weight_per_container"), float),
            "weight_unit": config.get("weight_unit"),
            "commodity": config.get("commodity"),

            "basic_available": _is_available(basic, requested_code),
            "basic_price": _build_price(basic),
            "basic_breakdown": _build_breakdown(basic),

            "premium_available": _is_available(premium, requested_code),
            "premium_price": _build_price(premium),
            "premium_breakdown": _build_breakdown(premium),

            "tags": _build_tags(basic, premium),
            "offer_ids": {
                "basic": basic.get("id") if basic else None,
                "premium": premium.get("id") if premium else None,
            },

            "scraped_at": scraped_at,
            "source_file": source_file,
            "departure_date": item.get("departureDate"),
        }
        sailings.append(sailing)

    return sailings


def ensure_indexes(client: MongoClient) -> None:
    collection = client[MONGO_DB][MONGO_COLLECTION]
    collection.create_index(
        [
            ("pol_locode", 1),
            ("pod_locode", 1),
            ("vessel", 1),
            ("voyage", 1),
            ("departure_date", 1),
        ],
        unique=True,
        name="sailing_identity",
    )


def push_to_mongo(sailings: list[dict], client: MongoClient) -> tuple[int, int]:
    if not sailings:
        return 0, 0

    collection = client[MONGO_DB][MONGO_COLLECTION]
    now = datetime.now(timezone.utc).isoformat()

    ops = []
    for s in sailings:
        if not (s.get("pol_locode") and s.get("pod_locode") and s.get("vessel") and s.get("voyage")):
            continue
        key = {
            "pol_locode": s["pol_locode"],
            "pod_locode": s["pod_locode"],
            "vessel": s["vessel"],
            "voyage": s["voyage"],
            "departure_date": s["departure_date"],
        }
        s["updated_at"] = now
        ops.append(UpdateOne(key, {"$set": s}, upsert=True))

    if not ops:
        return 0, 0

    try:
        result = collection.bulk_write(ops, ordered=False)
        return result.upserted_count, result.modified_count
    except BulkWriteError as e:
        print(f"  [warn] Bulk write partial error: {e.details.get('writeErrors', [])}")
        return 0, 0


def main():
    paths: list[Path] = []

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            p = Path(arg)
            if not p.exists():
                print(f"[error] File not found: {p}")
                sys.exit(1)
            paths.append(p)
    else:
        output_dir = Path("output")
        if not output_dir.exists():
            print("[error] No 'output/' directory found. Pass a file path as argument.")
            sys.exit(1)
        paths = sorted(output_dir.glob("*.json"))
        if not paths:
            print("[error] No JSON files found in output/")
            sys.exit(1)

    print(f"Connecting to {MONGO_URI} -> {MONGO_DB}.{MONGO_COLLECTION}")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)

    try:
        client.admin.command("ping")
        print("Connected.\n")
    except Exception as e:
        print(f"[error] Cannot connect to MongoDB: {e}")
        sys.exit(1)

    ensure_indexes(client)

    total_inserted = total_updated = total_skipped = 0

    for path in paths:
        print(f"Processing: {path.name}")
        try:
            data = load_json(path)
        except json.JSONDecodeError as e:
            print(f"  [error] Invalid JSON — skipping: {e}")
            continue

        sailings = extract_sailings(data, str(path))

        if not sailings:
            print(f"  [skip] No product offers found in {path.name}")
            total_skipped += 1
            continue

        inserted, updated = push_to_mongo(sailings, client)
        print(f"  {len(sailings)} sailings -> inserted: {inserted}, updated: {updated}")
        total_inserted += inserted
        total_updated += updated

    print(f"\nDone. Total inserted: {total_inserted}, updated: {total_updated}, files skipped: {total_skipped}")
    client.close()


if __name__ == "__main__":
    main()
