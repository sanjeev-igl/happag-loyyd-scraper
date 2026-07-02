"""Parse structured quote data from captured Hapag-Lloyd API responses."""

from __future__ import annotations


def parse_api_responses(responses: list[dict], request_bodies: dict[str, dict] | None = None) -> dict:
    """Extract the most useful fields from the captured network responses."""
    result: dict = {}
    request_bodies = request_bodies or {}

    # Extract route from the POST request body — most reliable source
    for url, body in request_bodies.items():
        if "/api/v3/offers/offer" in url or "/api/v4/offers/offer" in url:
            result["search_request"] = _extract_route_from_request(body)
            break

    for resp in responses:
        url = resp.get("url", "")
        data = resp.get("data", {})
        if not isinstance(data, dict):
            continue

        if "/api/v4/offers/" in url and "/status" not in url:
            result["offer_v4"] = _parse_offer_v4(data)
        elif "/api/v3/offers/offer" in url:
            result["offer_created"] = _extract_top_level(data, ["offerId", "id", "status"])
        elif "/status" in url and "offer_status" not in result:
            result["offer_status"] = _extract_top_level(data, ["status", "state", "progress"])

    return result


def _extract_route_from_request(body: dict) -> dict:
    """Pull origin/destination out of the POST body sent to create the offer."""
    route: dict = {}
    origin_keys = ("originPort", "pol", "loadingPort", "origin", "fromPort", "portOfLoading",
                   "departurePort", "originLocation", "startLocation")
    dest_keys = ("destinationPort", "pod", "dischargePort", "destination", "toPort",
                 "portOfDischarge", "arrivalPort", "destinationLocation", "endLocation")

    sources = [body] + [v for v in body.values() if isinstance(v, dict)]
    # routings is a list — check its first element
    routings = body.get("routings")
    if isinstance(routings, list) and routings:
        sources.append(routings[0])
    for src in sources:
        if "originPort" not in route:
            for k in origin_keys:
                if k in src:
                    route["originPort"] = _coerce_port(src[k])
                    break
        if "destinationPort" not in route:
            for k in dest_keys:
                if k in src:
                    route["destinationPort"] = _coerce_port(src[k])
                    break

    return route


def _parse_offer_v4(data: dict) -> dict:
    parsed: dict = {}

    # v4 wraps everything: {"type": ..., "request": {...}, "offer": {...}}
    request = data.get("request") or {}
    offer = data.get("offer") or {}

    # Store raw keys so field names are visible when structure is unknown
    parsed["_request_keys"] = list(request.keys())
    parsed["_offer_keys"] = list(offer.keys())

    # ── Identity ──────────────────────────────────────────────────────────────
    for key in ("offerId", "id", "referenceNumber", "status", "currency"):
        for src in (offer, request, data):
            if key in src:
                parsed[key] = src[key]
                break

    # ── Route ports ───────────────────────────────────────────────────────────
    origin_keys = ("originPort", "pol", "loadingPort", "origin", "departurePort",
                   "fromPort", "originLocation", "loadPort", "portOfLoading", "startLocation")
    dest_keys   = ("destinationPort", "pod", "dischargePort", "destination",
                   "arrivalPort", "toPort", "destinationLocation", "portOfDischarge", "endLocation")

    # Check flat fields in request → offer → root, then one level deeper in sub-dicts
    def _find_port(field_names):
        for src in (request, offer, data):
            for k in field_names:
                if k in src:
                    return _coerce_port(src[k])
            # one level deeper in dict sections
            for section_key in ("routing", "route", "transportation", "transportPlan",
                                "itinerary", "legs"):
                section = src.get(section_key)
                if not isinstance(section, dict):
                    continue
                for k in field_names:
                    if k in section:
                        return _coerce_port(section[k])
            # routings is a list — check its first element
            routings = src.get("routings")
            if isinstance(routings, list) and routings:
                first = routings[0]
                for k in field_names:
                    if k in first:
                        return _coerce_port(first[k])
        return None

    parsed["originPort"]      = _find_port(origin_keys)
    parsed["destinationPort"] = _find_port(dest_keys)

    # ── Container / commodity ─────────────────────────────────────────────────
    for key in ("containerType", "equipmentType", "commodity", "weight", "weightUnit"):
        for src in (request, offer, data):
            if key in src:
                parsed[key] = src[key]
                break

    # ── Departures / sailings ─────────────────────────────────────────────────
    sailing_keys = ("routings", "sailings", "schedules", "departures",
                    "options", "sailingOptions", "legs", "offerLegs")
    for src in (offer, request, data):
        for key in sailing_keys:
            if key in src and isinstance(src[key], list) and src[key]:
                parsed["departures"] = _parse_departure_list(src[key])
                break
        if "departures" in parsed:
            break

    # ── Pricing ───────────────────────────────────────────────────────────────
    for key in ("quickQuote", "price", "totalPrice", "oceanFreight",
                "chargeBreakdown", "charges", "rates"):
        for src in (offer, request, data):
            if key in src:
                parsed[key] = src[key]
                break

    # ── Validity ──────────────────────────────────────────────────────────────
    for key in ("validFrom", "validTo", "expiryDate", "validity"):
        for src in (offer, request, data):
            if key in src:
                parsed[key] = src[key]
                break

    return parsed


def _coerce_port(val) -> str:
    """Return a clean port code/name from a string or dict."""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        # Prefer the UN/LOCODE first, then a human-readable name
        for k in ("locationName", "name", "portName",
                  "locode", "unLocode", "portCode", "code", "id"):
            if val.get(k):
                return str(val[k])
    return ""


def _parse_departure_list(items: list) -> list[dict]:
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        entry: dict = {}

        # Dates
        for key in ("departureDate", "etd", "sailingDate", "cutOffDate",
                    "arrivalDate", "eta", "deliveryDate"):
            if key in item:
                entry[key] = item[key]

        # Transit & vessel
        for key in ("transitTime", "transitDays", "vesselName", "vessel",
                    "voyage", "voyageNumber", "service", "serviceCode"):
            if key in item:
                entry[key] = item[key]

        # Price — flat or nested
        for key in ("price", "totalPrice", "quickQuote", "amount",
                    "currency", "oceanFreight", "charges"):
            if key in item:
                entry[key] = item[key]

        # Store unknown keys so nothing is silently dropped
        entry["_raw_keys"] = list(item.keys())

        if len(entry) > 1:  # more than just _raw_keys
            result.append(entry)
    return result


def _extract_top_level(data: dict, keys: list[str]) -> dict:
    return {k: data[k] for k in keys if k in data}
