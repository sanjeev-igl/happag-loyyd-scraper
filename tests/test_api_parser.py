"""Unit tests for hapag_lloyd.extractors.api_parser."""

from hapag_lloyd.extractors.api_parser import (
    _coerce_port,
    _extract_route_from_request,
    _extract_top_level,
    _parse_charge_groups,
    _parse_offer_item,
    _parse_offer_v4,
    _parse_product_offer,
    parse_api_responses,
)


class TestCoercePortHappyPath:
    """_coerce_port returns a usable display string from either a plain string or a dict."""

    def test_string_input_is_passed_through_unchanged(self):
        assert _coerce_port("INNSA") == "INNSA"

    def test_dict_prefers_locationname_over_locode(self):
        val = {"locode": "INNSA", "locationName": "Nhava Sheva"}
        assert _coerce_port(val) == "Nhava Sheva"

    def test_dict_prefers_name_over_locode(self):
        # _coerce_port checks locationName/name/portName before locode/unLocode/etc.
        val = {"locode": "INNSA", "name": "Nhava Sheva"}
        assert _coerce_port(val) == "Nhava Sheva"

    def test_dict_falls_back_to_portname_when_no_name_present(self):
        val = {"portName": "Singapore"}
        assert _coerce_port(val) == "Singapore"

    def test_dict_uses_locode_when_no_name_field_present(self):
        val = {"locode": "INNSA"}
        assert _coerce_port(val) == "INNSA"

    def test_dict_falls_back_to_code_when_only_code_present(self):
        val = {"code": "SGSIN"}
        assert _coerce_port(val) == "SGSIN"

    def test_dict_falls_back_to_id_as_last_resort(self):
        val = {"id": "12345"}
        assert _coerce_port(val) == "12345"

    def test_non_string_locode_value_is_coerced_to_string(self):
        val = {"id": 12345}
        assert _coerce_port(val) == "12345"


class TestCoercePortFailPath:
    """_coerce_port degrades to an empty string rather than raising for absent/unusable input."""

    def test_none_returns_empty_string(self):
        assert _coerce_port(None) == ""

    def test_empty_dict_returns_empty_string(self):
        assert _coerce_port({}) == ""

    def test_dict_with_only_unrecognized_keys_returns_empty_string(self):
        assert _coerce_port({"foo": "bar"}) == ""

    def test_dict_with_falsy_values_for_every_key_returns_empty_string(self):
        assert _coerce_port({"locode": "", "name": None}) == ""

    def test_unsupported_type_returns_empty_string(self):
        assert _coerce_port(123) == ""
        assert _coerce_port(["INNSA"]) == ""


class TestExtractTopLevelHappyPath:
    """_extract_top_level pulls exactly the requested keys that are present."""

    def test_only_requested_keys_are_kept(self):
        data = {"offerId": "123", "status": "OK", "extra": "ignored"}
        assert _extract_top_level(data, ["offerId", "status"]) == {"offerId": "123", "status": "OK"}

    def test_all_requested_keys_present_returns_full_set(self):
        data = {"status": "PENDING", "state": "running", "progress": 50}
        assert _extract_top_level(data, ["status", "state", "progress"]) == data

    def test_key_order_in_requested_list_does_not_affect_result_contents(self):
        data = {"a": 1, "b": 2}
        assert _extract_top_level(data, ["b", "a"]) == {"a": 1, "b": 2}


class TestExtractTopLevelFailPath:
    """_extract_top_level omits absent keys instead of raising KeyError."""

    def test_missing_keys_are_omitted_from_result(self):
        data = {"offerId": "123"}
        assert _extract_top_level(data, ["offerId", "status"]) == {"offerId": "123"}

    def test_no_requested_keys_present_returns_empty_dict(self):
        assert _extract_top_level({"unrelated": "value"}, ["offerId", "status"]) == {}

    def test_empty_data_dict_returns_empty_dict(self):
        assert _extract_top_level({}, ["offerId", "status"]) == {}

    def test_empty_keys_list_returns_empty_dict(self):
        assert _extract_top_level({"offerId": "123"}, []) == {}


class TestExtractRouteFromRequestHappyPath:
    """_extract_route_from_request finds origin/destination under any of the known key spellings."""

    def test_top_level_originport_and_destinationport_keys(self):
        body = {"originPort": "INNSA", "destinationPort": "SGSIN"}
        assert _extract_route_from_request(body) == {
            "originPort": "INNSA",
            "destinationPort": "SGSIN",
        }

    def test_route_is_read_from_first_element_of_routings_list(self):
        body = {"routings": [{"pol": "INNSA", "pod": "SGSIN"}]}
        assert _extract_route_from_request(body) == {
            "originPort": "INNSA",
            "destinationPort": "SGSIN",
        }

    def test_route_is_found_inside_an_arbitrary_nested_dict(self):
        body = {"search": {"origin": "INNSA", "destination": "SGSIN"}}
        assert _extract_route_from_request(body) == {
            "originPort": "INNSA",
            "destinationPort": "SGSIN",
        }

    def test_dict_valued_port_fields_are_coerced_via_coerce_port(self):
        body = {"originPort": {"name": "Nhava Sheva"}, "destinationPort": {"locode": "SGSIN"}}
        assert _extract_route_from_request(body) == {
            "originPort": "Nhava Sheva",
            "destinationPort": "SGSIN",
        }

    def test_top_level_key_takes_priority_over_nested_dict_match(self):
        body = {"originPort": "INNSA", "search": {"origin": "OTHERPORT"}}
        assert _extract_route_from_request(body)["originPort"] == "INNSA"

    def test_only_destination_present_still_returns_partial_route(self):
        body = {"destinationPort": "SGSIN"}
        assert _extract_route_from_request(body) == {"destinationPort": "SGSIN"}


class TestExtractRouteFromRequestFailPath:
    """_extract_route_from_request returns an empty/partial dict rather than raising when data is missing."""

    def test_no_matching_keys_anywhere_returns_empty_dict(self):
        assert _extract_route_from_request({}) == {}

    def test_unrelated_keys_only_returns_empty_dict(self):
        assert _extract_route_from_request({"foo": "bar", "nested": {"baz": "qux"}}) == {}

    def test_empty_routings_list_is_ignored_without_error(self):
        assert _extract_route_from_request({"routings": []}) == {}

    def test_non_dict_routings_first_element_is_ignored_without_error(self):
        assert _extract_route_from_request({"routings": ["not-a-dict"]}) == {}


class TestParseChargeGroupsHappyPath:
    """_parse_charge_groups flattens grouped charge-line data into a single list of records."""

    def test_flattens_a_single_group_with_one_charge(self):
        charge_groups = [
            {
                "label": "Ocean Freight",
                "data": [
                    {"name": "Base Freight", "code": "BAS", "currency": "USD", "containers": []},
                ],
            }
        ]
        result = _parse_charge_groups(charge_groups)
        assert result == [
            {
                "group": "Ocean Freight",
                "name": "Base Freight",
                "code": "BAS",
                "currency": "USD",
                "containers": [],
            }
        ]

    def test_multiple_groups_and_multiple_charges_per_group_are_all_flattened(self):
        charge_groups = [
            {"label": "Ocean Freight", "data": [
                {"name": "Base Freight", "code": "BAS", "currency": "USD", "containers": []},
                {"name": "Bunker", "code": "BUC", "currency": "USD", "containers": []},
            ]},
            {"label": "Origin Charges", "data": [
                {"name": "THC", "code": "THC", "currency": "INR", "containers": []},
            ]},
        ]
        result = _parse_charge_groups(charge_groups)
        assert len(result) == 3
        assert [c["code"] for c in result] == ["BAS", "BUC", "THC"]

    def test_group_name_field_is_used_when_label_is_absent(self):
        charge_groups = [{"name": "SEA_FREIGHT", "data": [{"name": "Freight", "code": "F", "currency": "USD"}]}]
        result = _parse_charge_groups(charge_groups)
        assert result[0]["group"] == "SEA_FREIGHT"

    def test_label_takes_priority_over_name_for_group_field(self):
        charge_groups = [{"label": "Display Label", "name": "internal_name", "data": [{"name": "X"}]}]
        result = _parse_charge_groups(charge_groups)
        assert result[0]["group"] == "Display Label"


class TestParseChargeGroupsFailPath:
    """_parse_charge_groups skips malformed entries instead of raising."""

    def test_non_dict_groups_are_ignored(self):
        assert _parse_charge_groups(["not a dict", None, 42]) == []

    def test_empty_input_list_returns_empty_list(self):
        assert _parse_charge_groups([]) == []

    def test_group_with_missing_data_key_contributes_no_charges(self):
        assert _parse_charge_groups([{"label": "Empty Group"}]) == []

    def test_group_with_empty_data_list_contributes_no_charges(self):
        assert _parse_charge_groups([{"label": "Empty Group", "data": []}]) == []

    def test_charge_missing_optional_fields_still_produces_a_record_with_nones(self):
        result = _parse_charge_groups([{"label": "G", "data": [{}]}])
        assert result == [{"group": "G", "name": None, "code": None, "currency": None, "containers": None}]


class TestParseOfferV4HappyPath:
    """_parse_offer_v4 extracts route, cargo, and departures from a well-formed v4 offer payload."""

    def test_route_is_read_from_request_routings_when_present(self):
        data = {
            "request": {"routings": [{"startLocation": "INNSA", "endLocation": "SGSIN"}]},
            "offer": {},
        }
        parsed = _parse_offer_v4(data)
        assert parsed["originPort"] == "INNSA"
        assert parsed["destinationPort"] == "SGSIN"

    def test_route_falls_back_to_offer_routing_when_request_has_no_routings(self):
        data = {
            "request": {},
            "offer": {"routing": {"startLocation": "INNSA", "destinationLocation": "SGSIN"}},
        }
        parsed = _parse_offer_v4(data)
        assert parsed["originPort"] == "INNSA"
        assert parsed["destinationPort"] == "SGSIN"

    def test_cargo_container_and_commodity_fields_are_extracted(self):
        data = {
            "request": {
                "cargoDetails": {
                    "container": {
                        "containerType": "45GP",
                        "amount": 1,
                        "cargoWeightPerContainer": 20000,
                        "unitOfMeasure": "kg",
                    },
                    "commodityGroup": {"name": "FAK"},
                },
                "validFrom": "2026-07-09",
            },
            "offer": {"items": []},
        }
        parsed = _parse_offer_v4(data)
        assert parsed["containerType"] == "45GP"
        assert parsed["containerQuantity"] == 1
        assert parsed["weightPerContainer"] == 20000
        assert parsed["weightUnit"] == "kg"
        assert parsed["commodity"] == "FAK"
        assert parsed["validFrom"] == "2026-07-09"
        assert parsed["departures"] == []

    def test_departures_are_parsed_from_offer_items(self):
        data = {
            "request": {},
            "offer": {
                "items": [
                    {"departureDate": "2026-07-10", "productOffers": [{"offerId": "abc", "productType": "QQ"}]},
                ]
            },
        }
        parsed = _parse_offer_v4(data)
        assert len(parsed["departures"]) == 1
        assert parsed["departures"][0]["departureDate"] == "2026-07-10"
        assert parsed["departures"][0]["productOffers"][0]["offerId"] == "abc"


class TestParseOfferV4FailPath:
    """_parse_offer_v4 degrades gracefully (empty/None fields) when sections of the payload are absent."""

    def test_completely_empty_payload_does_not_raise(self):
        parsed = _parse_offer_v4({})
        assert parsed["originPort"] == ""
        assert parsed["destinationPort"] == ""
        assert parsed["departures"] == []

    def test_missing_cargo_details_omits_container_fields_without_raising(self):
        parsed = _parse_offer_v4({"request": {}, "offer": {}})
        assert "containerType" not in parsed
        assert "commodity" not in parsed

    def test_non_dict_items_in_offer_items_are_skipped(self):
        data = {"request": {}, "offer": {"items": ["not-a-dict", None, {"departureDate": "2026-07-10"}]}}
        parsed = _parse_offer_v4(data)
        assert len(parsed["departures"]) == 1

    def test_missing_offer_items_key_returns_empty_departures(self):
        parsed = _parse_offer_v4({"request": {}, "offer": {}})
        assert parsed["departures"] == []


class TestParseOfferItemHappyPath:
    """_parse_offer_item extracts the departure date and parses each nested product offer."""

    def test_departure_date_and_product_offers_are_extracted(self):
        item = {
            "departureDate": "2026-07-10",
            "productOffers": [{"offerId": "abc", "productType": "QQ_MONTHLY"}],
        }
        result = _parse_offer_item(item)
        assert result["departureDate"] == "2026-07-10"
        assert len(result["productOffers"]) == 1
        assert result["productOffers"][0]["offerId"] == "abc"

    def test_multiple_product_offers_for_the_same_departure_are_all_parsed(self):
        item = {
            "departureDate": "2026-07-10",
            "productOffers": [{"offerId": "a"}, {"offerId": "b"}],
        }
        result = _parse_offer_item(item)
        assert [po["offerId"] for po in result["productOffers"]] == ["a", "b"]


class TestParseOfferItemFailPath:
    """_parse_offer_item tolerates missing/malformed productOffers rather than raising."""

    def test_missing_product_offers_key_returns_empty_list(self):
        result = _parse_offer_item({"departureDate": "2026-07-10"})
        assert result["productOffers"] == []

    def test_non_dict_product_offers_are_skipped(self):
        item = {"departureDate": "2026-07-10", "productOffers": ["not-a-dict", None, 42]}
        result = _parse_offer_item(item)
        assert result["productOffers"] == []

    def test_missing_departure_date_returns_none(self):
        result = _parse_offer_item({"productOffers": []})
        assert result["departureDate"] is None


class TestParseProductOfferHappyPath:
    """_parse_product_offer extracts pricing metadata, legs, charges, and ocean freight breakdown."""

    def test_top_level_pricing_metadata_fields_are_extracted(self):
        po = {
            "offerId": "abc123",
            "productType": "QQ_MONTHLY",
            "departureDate": "2026-07-10",
            "arrivalDate": "2026-08-01",
            "estimatedDaysOfTransport": 22,
            "cutOffDateTime": "2026-07-09T12:00:00Z",
            "offerValidTo": "2026-07-15",
        }
        result = _parse_product_offer(po)
        assert result["offerId"] == "abc123"
        assert result["productType"] == "QQ_MONTHLY"
        assert result["estimatedDaysOfTransport"] == 22

    def test_legs_are_parsed_with_coerced_port_names(self):
        po = {
            "legs": [
                {
                    "modeOfTransport": "VESSEL",
                    "departureLocation": {"name": "Nhava Sheva"},
                    "departureDateTime": "2026-07-10T00:00:00Z",
                    "arrivalLocation": {"locode": "SGSIN"},
                    "arrivalDateTime": "2026-07-20T00:00:00Z",
                    "serviceName": "IN2",
                    "voyageNumber": "123W",
                    "transitTime": 10,
                    "vesselName": "MV Example",
                }
            ]
        }
        result = _parse_product_offer(po)
        assert len(result["legs"]) == 1
        assert result["legs"][0]["departureLocation"] == "Nhava Sheva"
        assert result["legs"][0]["arrivalLocation"] == "SGSIN"
        assert result["legs"][0]["vesselName"] == "MV Example"

    def test_charges_prefer_usd_section_over_local(self):
        po = {
            "sections": {
                "USD": [{"label": "Ocean Freight", "data": [{"name": "Base", "code": "BAS", "currency": "USD"}]}],
                "LOCAL": [{"label": "Ocean Freight", "data": [{"name": "Base", "code": "BAS", "currency": "INR"}]}],
            }
        }
        result = _parse_product_offer(po)
        assert result["charges"][0]["currency"] == "USD"

    def test_charges_fall_back_to_local_section_when_usd_absent(self):
        po = {
            "sections": {
                "LOCAL": [{"label": "Ocean Freight", "data": [{"name": "Base", "code": "BAS", "currency": "INR"}]}],
            }
        }
        result = _parse_product_offer(po)
        assert result["charges"][0]["currency"] == "INR"

    def test_ocean_freight_per_container_is_extracted_from_sea_freight_group(self):
        po = {
            "sections": {
                "USD": [
                    {
                        "name": "SEA_FREIGHT",
                        "data": [
                            {
                                "currency": "USD",
                                "containers": [
                                    {"containerType": "45GP", "amount": 1200},
                                    {"containerType": "22G0", "amount": 800},
                                ],
                            }
                        ],
                    }
                ]
            }
        }
        result = _parse_product_offer(po)
        assert result["ocean_freight_per_container"] == [
            {"container_type": "45GP", "amount": 1200, "currency": "USD"},
            {"container_type": "22G0", "amount": 800, "currency": "USD"},
        ]


class TestParseProductOfferFailPath:
    """_parse_product_offer tolerates a minimal/malformed payload rather than raising."""

    def test_empty_payload_produces_all_none_metadata_fields(self):
        result = _parse_product_offer({})
        assert result["offerId"] is None
        assert result["productType"] is None

    def test_missing_legs_key_omits_legs_from_result(self):
        result = _parse_product_offer({})
        assert "legs" not in result

    def test_empty_legs_list_omits_legs_from_result(self):
        result = _parse_product_offer({"legs": []})
        assert "legs" not in result

    def test_missing_sections_key_produces_empty_charges_and_no_ocean_freight(self):
        result = _parse_product_offer({})
        assert result["charges"] == []
        assert "ocean_freight_per_container" not in result

    def test_sections_without_sea_freight_group_produces_no_ocean_freight_key(self):
        po = {"sections": {"USD": [{"name": "ORIGIN_CHARGES", "data": [{"name": "THC"}]}]}}
        result = _parse_product_offer(po)
        assert "ocean_freight_per_container" not in result

    def test_sea_freight_group_with_empty_data_produces_no_ocean_freight_key(self):
        po = {"sections": {"USD": [{"name": "SEA_FREIGHT", "data": []}]}}
        result = _parse_product_offer(po)
        assert "ocean_freight_per_container" not in result


class TestParseApiResponsesHappyPath:
    """parse_api_responses assembles the full api_data dict from a set of captured responses."""

    def test_extracts_route_from_request_body(self):
        request_bodies = {
            "https://api.hapag-lloyd.com/api/v4/offers/offer": {
                "originPort": "INNSA",
                "destinationPort": "SGSIN",
            }
        }
        result = parse_api_responses([], request_bodies)
        assert result["search_request"] == {
            "originPort": "INNSA",
            "destinationPort": "SGSIN",
        }

    def test_v3_offer_request_url_is_also_recognized_for_search_request(self):
        request_bodies = {
            "https://api.hapag-lloyd.com/api/v3/offers/offer": {"originPort": "INNSA", "destinationPort": "SGSIN"},
        }
        result = parse_api_responses([], request_bodies)
        assert result["search_request"] == {"originPort": "INNSA", "destinationPort": "SGSIN"}

    def test_parses_offer_created_response(self):
        responses = [
            {
                "url": "https://api.hapag-lloyd.com/api/v3/offers/offer",
                "data": {"offerId": "abc123", "status": "CREATED", "unused": "x"},
            }
        ]
        result = parse_api_responses(responses)
        assert result["offer_created"] == {"offerId": "abc123", "status": "CREATED"}

    def test_parses_status_response_once(self):
        responses = [
            {"url": "https://api.hapag-lloyd.com/api/v3/offers/1/status", "data": {"status": "PENDING"}},
            {"url": "https://api.hapag-lloyd.com/api/v3/offers/1/status", "data": {"status": "DONE"}},
        ]
        result = parse_api_responses(responses)
        # Only the first status response should be kept.
        assert result["offer_status"] == {"status": "PENDING"}

    def test_parses_offer_v4_response(self):
        responses = [
            {
                "url": "https://api.hapag-lloyd.com/api/v4/offers/xyz",
                "data": {
                    "request": {
                        "routings": [{"startLocation": "INNSA", "endLocation": "SGSIN"}],
                        "cargoDetails": {
                            "container": {
                                "containerType": "45GP",
                                "amount": 1,
                                "cargoWeightPerContainer": 20000,
                                "unitOfMeasure": "kg",
                            },
                            "commodityGroup": {"name": "FAK"},
                        },
                        "validFrom": "2026-07-09",
                    },
                    "offer": {"items": []},
                },
            }
        ]
        result = parse_api_responses(responses)
        offer_v4 = result["offer_v4"]
        assert offer_v4["originPort"] == "INNSA"
        assert offer_v4["destinationPort"] == "SGSIN"
        assert offer_v4["containerType"] == "45GP"
        assert offer_v4["containerQuantity"] == 1
        assert offer_v4["commodity"] == "FAK"
        assert offer_v4["validFrom"] == "2026-07-09"
        assert offer_v4["departures"] == []

    def test_all_four_result_keys_can_be_populated_from_one_response_set(self):
        request_bodies = {
            "https://api.hapag-lloyd.com/api/v4/offers/offer": {"originPort": "INNSA", "destinationPort": "SGSIN"},
        }
        responses = [
            {"url": "https://api.hapag-lloyd.com/api/v3/offers/offer", "data": {"offerId": "abc", "status": "CREATED"}},
            {"url": "https://api.hapag-lloyd.com/api/v3/offers/abc/status", "data": {"status": "DONE"}},
            {"url": "https://api.hapag-lloyd.com/api/v4/offers/abc", "data": {"request": {}, "offer": {"items": []}}},
        ]
        result = parse_api_responses(responses, request_bodies)
        assert set(result.keys()) == {"search_request", "offer_created", "offer_status", "offer_v4"}

    def test_status_url_excludes_offers_v4_endpoint(self):
        """A '/status' URL should not also match the '/api/v4/offers/' branch check for offer_v4
        when it explicitly contains '/status'."""
        responses = [
            {
                "url": "https://api.hapag-lloyd.com/api/v4/offers/xyz/status",
                "data": {"status": "PENDING"},
            }
        ]
        result = parse_api_responses(responses)
        assert "offer_v4" not in result
        assert result["offer_status"] == {"status": "PENDING"}


class TestParseApiResponsesFailPath:
    """parse_api_responses returns partial/empty results rather than raising on missing or bad input."""

    def test_no_responses_and_no_request_bodies_returns_empty_dict(self):
        assert parse_api_responses([]) == {}

    def test_none_request_bodies_defaults_to_empty_and_does_not_raise(self):
        assert parse_api_responses([], None) == {}

    def test_skips_non_dict_response_data(self):
        responses = [{"url": "https://api.hapag-lloyd.com/api/v4/offers/1", "data": "not a dict"}]
        assert parse_api_responses(responses) == {}

    def test_response_with_unrecognized_url_is_ignored(self):
        responses = [{"url": "https://api.hapag-lloyd.com/api/v9/unknown", "data": {"foo": "bar"}}]
        assert parse_api_responses(responses) == {}

    def test_response_missing_url_key_defaults_to_empty_string_and_is_ignored(self):
        responses = [{"data": {"status": "DONE"}}]
        assert parse_api_responses(responses) == {}

    def test_response_missing_data_key_defaults_to_empty_dict_not_an_error(self):
        # "data" defaults to {} (still a dict), so a v4 URL is still parsed — just into an
        # empty-shell offer_v4 record rather than being skipped like a non-dict "data" would be.
        responses = [{"url": "https://api.hapag-lloyd.com/api/v4/offers/1"}]
        result = parse_api_responses(responses)
        assert result["offer_v4"]["originPort"] == ""
        assert result["offer_v4"]["departures"] == []

    def test_request_body_url_not_matching_offer_endpoint_leaves_search_request_unset(self):
        request_bodies = {"https://api.hapag-lloyd.com/api/v4/other/endpoint": {"originPort": "INNSA"}}
        result = parse_api_responses([], request_bodies)
        assert "search_request" not in result
