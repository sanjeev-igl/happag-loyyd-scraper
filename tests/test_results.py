"""Unit tests for the pure (non-Playwright) helpers in hapag_lloyd.extractors.results."""

from hapag_lloyd.extractors.results import (
    _price_breakdown_from_api,
    _quick_quote_from_api,
    _route_from_api,
)


class TestRouteFromApiHappyPath:
    """_route_from_api formats an en-dash separated 'ORIGIN – DEST' string when both ports are present."""

    def test_both_ports_present_are_joined_with_en_dash(self):
        assert _route_from_api({"originPort": "Nhava Sheva", "destinationPort": "Singapore"}) == (
            "Nhava Sheva – Singapore"
        )


class TestRouteFromApiFailPath:
    """_route_from_api returns None (never raises) when either side of the route is missing."""

    def test_missing_origin_port_returns_none(self):
        assert _route_from_api({"destinationPort": "Singapore"}) is None

    def test_missing_destination_port_returns_none(self):
        assert _route_from_api({"originPort": "Nhava Sheva"}) is None

    def test_empty_dict_returns_none(self):
        assert _route_from_api({}) is None

    def test_empty_string_port_values_are_falsy_and_return_none(self):
        assert _route_from_api({"originPort": "", "destinationPort": "Singapore"}) is None


class TestQuickQuoteFromApiHappyPath:
    """_quick_quote_from_api summarizes validFrom + ocean freight for the earliest departure's first offer."""

    def test_valid_from_and_ocean_freight_are_extracted_from_first_departure_first_offer(self):
        offer_v4 = {
            "validFrom": "2026-07-09",
            "departures": [
                {
                    "productOffers": [
                        {"ocean_freight_per_container": [{"container_type": "45GP", "amount": 1200, "currency": "USD"}]},
                    ]
                }
            ],
        }
        result = _quick_quote_from_api(offer_v4)

        assert result["validFrom"] == "2026-07-09"
        assert result["ocean_freight_per_container"] == [
            {"container_type": "45GP", "amount": 1200, "currency": "USD"}
        ]

    def test_only_the_first_departure_and_first_offer_are_used(self):
        offer_v4 = {
            "validFrom": "2026-07-09",
            "departures": [
                {"productOffers": [{"ocean_freight_per_container": [{"container_type": "20DC", "amount": 500}]}]},
                {"productOffers": [{"ocean_freight_per_container": [{"container_type": "40HC", "amount": 900}]}]},
            ],
        }
        result = _quick_quote_from_api(offer_v4)

        assert result["ocean_freight_per_container"][0]["container_type"] == "20DC"


class TestQuickQuoteFromApiFailPath:
    """_quick_quote_from_api returns {} when there is no departure/offer data to summarize."""

    def test_empty_offer_v4_returns_empty_dict(self):
        assert _quick_quote_from_api({}) == {}

    def test_no_departures_returns_empty_dict(self):
        assert _quick_quote_from_api({"departures": []}) == {}

    def test_departure_with_no_product_offers_returns_empty_dict(self):
        assert _quick_quote_from_api({"departures": [{"productOffers": []}]}) == {}

    def test_missing_ocean_freight_key_omits_it_but_still_includes_valid_from(self):
        offer_v4 = {"validFrom": "2026-07-09", "departures": [{"productOffers": [{}]}]}
        result = _quick_quote_from_api(offer_v4)

        assert result == {"validFrom": "2026-07-09"}


class TestPriceBreakdownFromApiHappyPath:
    """_price_breakdown_from_api returns the charges list for the earliest departure's first offer."""

    def test_charges_are_extracted_from_first_departure_first_offer(self):
        offer_v4 = {
            "departures": [
                {"productOffers": [{"charges": [{"code": "BAS", "amount": 100}]}]},
            ]
        }
        result = _price_breakdown_from_api(offer_v4)

        assert result == {"charges": [{"code": "BAS", "amount": 100}]}

    def test_only_the_first_departure_and_first_offer_are_used(self):
        offer_v4 = {
            "departures": [
                {"productOffers": [{"charges": [{"code": "FIRST"}]}]},
                {"productOffers": [{"charges": [{"code": "SECOND"}]}]},
            ]
        }
        result = _price_breakdown_from_api(offer_v4)

        assert result["charges"] == [{"code": "FIRST"}]


class TestPriceBreakdownFromApiFailPath:
    """_price_breakdown_from_api returns {} or an empty charges list rather than raising."""

    def test_empty_offer_v4_returns_empty_dict(self):
        assert _price_breakdown_from_api({}) == {}

    def test_no_departures_returns_empty_dict(self):
        assert _price_breakdown_from_api({"departures": []}) == {}

    def test_departure_with_no_product_offers_returns_empty_dict(self):
        assert _price_breakdown_from_api({"departures": [{"productOffers": []}]}) == {}

    def test_missing_charges_key_on_the_offer_returns_empty_charges_list(self):
        offer_v4 = {"departures": [{"productOffers": [{}]}]}
        assert _price_breakdown_from_api(offer_v4) == {"charges": []}
