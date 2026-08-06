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
    """Parse the real /api/v4/offers/{id} payload.

    Shape observed live: {"type", "request": {...}, "offer": {"routing", "cargoDetails",
    "items": [{"id", "departureDate", "productOffers": [{...pricing sections...}]}]}}
    """
    parsed: dict = {}

    request = data.get("request") or {}
    offer = data.get("offer") or {}

    routing = request.get("routings", [{}])[0] if request.get("routings") else offer.get("routing", {})
    start = routing.get("startLocation", {})
    end = routing.get("endLocation") or routing.get("destinationLocation") or {}
    parsed["originPort"] = _coerce_port(start)
    parsed["destinationPort"] = _coerce_port(end)

    cargo = request.get("cargoDetails") or offer.get("cargoDetails") or {}
    container = cargo.get("container", {})
    if container:
        parsed["containerType"] = container.get("containerType")
        parsed["containerQuantity"] = container.get("amount")
        parsed["weightPerContainer"] = container.get("cargoWeightPerContainer")
        parsed["weightUnit"] = container.get("unitOfMeasure")
    commodity = cargo.get("commodityGroup", {})
    if commodity:
        parsed["commodity"] = commodity.get("name")

    parsed["validFrom"] = request.get("validFrom")

    items = offer.get("items", [])
    parsed["departures"] = [_parse_offer_item(item) for item in items if isinstance(item, dict)]

    return parsed


def _parse_offer_item(item: dict) -> dict:
    """One departure date's offer, containing one or more product offers (Quick Quote, Spot, ...)."""
    entry: dict = {
        "departureDate": item.get("departureDate"),
        "productOffers": [_parse_product_offer(po) for po in item.get("productOffers", [])
                           if isinstance(po, dict)],
    }
    return entry


def _parse_product_offer(po: dict) -> dict:
    """A single priced offer (e.g. QQ_MONTHLY) with legs, charges, and value-added services."""
    result: dict = {
        "offerId": po.get("offerId"),
        "productType": po.get("productType"),
        "departureDate": po.get("departureDate"),
        "arrivalDate": po.get("arrivalDate"),
        "estimatedDaysOfTransport": po.get("estimatedDaysOfTransport"),
        "cutOffDateTime": po.get("cutOffDateTime"),
        "offerValidTo": po.get("offerValidTo"),
        "potentialQuotationValidFrom": po.get("potentialQuotationValidFrom"),
        "potentialQuotationValidTo": po.get("potentialQuotationValidTo"),
        "includedCharges": po.get("includedCharges"),
        "excludedCharges": po.get("excludedCharges"),
        "containers": po.get("containers"),
    }

    legs = po.get("legs", [])
    if legs:
        result["legs"] = [
            {
                "modeOfTransport": leg.get("modeOfTransport"),
                "departureLocation": _coerce_port(leg.get("departureLocation")),
                "departureDateTime": leg.get("departureDateTime"),
                "arrivalLocation": _coerce_port(leg.get("arrivalLocation")),
                "arrivalDateTime": leg.get("arrivalDateTime"),
                "serviceName": leg.get("serviceName"),
                "voyageNumber": leg.get("voyageNumber"),
                "transitTime": leg.get("transitTime"),
                "vesselName": leg.get("vesselName"),
            }
            for leg in legs
        ]

    # sections["USD"] holds the same charges normalized to USD; prefer it, fall back to LOCAL.
    sections = po.get("sections", {})
    charge_groups = sections.get("USD") or sections.get("LOCAL") or []
    result["charges"] = _parse_charge_groups(charge_groups)

    # Total ocean freight per container type, from the SEA_FREIGHT group.
    ocean_freight = next((g for g in charge_groups if g.get("name") == "SEA_FREIGHT"), None)
    if ocean_freight and ocean_freight.get("data"):
        sea = ocean_freight["data"][0]
        result["ocean_freight_per_container"] = [
            {"container_type": c.get("containerType"), "amount": c.get("amount"), "currency": sea.get("currency")}
            for c in sea.get("containers", [])
        ]

    return result


def _parse_charge_groups(charge_groups: list) -> list[dict]:
    """Flatten sections[...] charge groups into [{group, name, code, currency, containers}]."""
    result = []
    for group in charge_groups:
        if not isinstance(group, dict):
            continue
        for charge in group.get("data", []):
            result.append({
                "group": group.get("label") or group.get("name"),
                "name": charge.get("name"),
                "code": charge.get("code"),
                "currency": charge.get("currency"),
                "containers": charge.get("containers"),
            })
    return result


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


def _extract_top_level(data: dict, keys: list[str]) -> dict:
    return {k: data[k] for k in keys if k in data}
