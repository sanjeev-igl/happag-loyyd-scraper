"""Unit tests for hapag_lloyd.trade_lanes."""

import pytest

from hapag_lloyd.trade_lanes import _normalize_port, _parse_trade_lane, fetch_trade_lanes


class TestParseTradeLaneHappyPath:
    """_parse_trade_lane successfully splits well-formed 'Origin - Destination' strings."""

    def test_splits_on_hyphen_with_surrounding_spaces(self):
        assert _parse_trade_lane("Nhava Sheva - Singapore") == ("Nhava Sheva", "Singapore")

    def test_hyphens_within_the_destination_name_are_preserved(self):
        # Only the FIRST ' - ' separator is treated as the split point, so a
        # destination that itself contains ' - ' survives intact.
        assert _parse_trade_lane("Ho Chi Minh - Xi'an - Something") == (
            "Ho Chi Minh",
            "Xi'an - Something",
        )

    def test_leading_and_trailing_whitespace_around_each_side_is_stripped(self):
        assert _parse_trade_lane("  Origin  -  Destination  ") == ("Origin", "Destination")

    def test_single_word_port_names_on_both_sides(self):
        assert _parse_trade_lane("Mundra - Rotterdam") == ("Mundra", "Rotterdam")


class TestParseTradeLaneFailPath:
    """_parse_trade_lane returns None (never raises) for malformed input."""

    def test_missing_separator_returns_none(self):
        assert _parse_trade_lane("NoSeparatorHere") is None

    def test_empty_origin_side_returns_none(self):
        assert _parse_trade_lane(" - Singapore") is None

    def test_empty_destination_side_returns_none(self):
        assert _parse_trade_lane("Singapore - ") is None

    def test_empty_string_returns_none(self):
        assert _parse_trade_lane("") is None

    def test_bare_hyphen_with_no_port_names_returns_none(self):
        assert _parse_trade_lane("-") is None


class TestNormalizePortHappyPath:
    """_normalize_port maps known aliases/terminal codes to the site's recognized port name."""

    def test_jnpt_alias_maps_to_nhava_sheva(self):
        assert _normalize_port("JNPT") == "Nhava Sheva"

    def test_nhava_sheva_uppercase_maps_to_title_case(self):
        assert _normalize_port("NHAVA SHEVA") == "Nhava Sheva"

    def test_antwerpen_maps_to_antwerp(self):
        assert _normalize_port("Antwerpen") == "Antwerp"

    def test_pipavav_victor_port_maps_to_pipavav(self):
        assert _normalize_port("Pipavav (Victor) Port") == "Pipavav"

    def test_nsigt_terminal_code_maps_to_nhava_sheva(self):
        assert _normalize_port("NSIGT") == "Nhava Sheva"

    def test_nsict_terminal_code_maps_to_nhava_sheva(self):
        assert _normalize_port("NSICT") == "Nhava Sheva"

    def test_bmct_terminal_code_maps_to_nhava_sheva(self):
        assert _normalize_port("BMCT") == "Nhava Sheva"


class TestNormalizePortFailPath:
    """_normalize_port passes through anything not in PORT_NAME_MAP unchanged, rather than erroring."""

    def test_unknown_port_name_passes_through_unchanged(self):
        assert _normalize_port("Rotterdam") == "Rotterdam"

    def test_empty_string_passes_through_unchanged(self):
        assert _normalize_port("") == ""

    def test_lookup_is_case_sensitive_so_lowercase_alias_is_not_mapped(self):
        # Only the exact casing "JNPT" is in PORT_NAME_MAP; "jnpt" is treated as unknown.
        assert _normalize_port("jnpt") == "jnpt"


class TestFetchTradeLanesHappyPath:
    """fetch_trade_lanes reads a well-formed CSV into normalized, sorted lane dicts."""

    def test_parses_and_sorts_by_shipment_count_descending(self, tmp_path):
        csv_content = (
            "trade_lane,shipment_count\n"
            "JNPT - Singapore,10\n"
            "Antwerpen - Rotterdam,50\n"
        )
        csv_path = tmp_path / "lanes.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        lanes = fetch_trade_lanes(str(csv_path))

        assert lanes == [
            {"start_location": "Antwerp", "end_location": "Rotterdam", "shipment_count": 50},
            {"start_location": "Nhava Sheva", "end_location": "Singapore", "shipment_count": 10},
        ]

    def test_port_names_are_normalized_via_port_name_map(self, tmp_path):
        csv_path = tmp_path / "lanes.csv"
        csv_path.write_text("trade_lane,shipment_count\nNSIGT - Antwerpen,1\n", encoding="utf-8")

        lanes = fetch_trade_lanes(str(csv_path))

        assert lanes == [{"start_location": "Nhava Sheva", "end_location": "Antwerp", "shipment_count": 1}]

    def test_ties_in_shipment_count_preserve_relative_row_order(self, tmp_path):
        csv_content = (
            "trade_lane,shipment_count\n"
            "Origin1 - Dest1,20\n"
            "Origin2 - Dest2,20\n"
        )
        csv_path = tmp_path / "lanes.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        lanes = fetch_trade_lanes(str(csv_path))

        assert [l["start_location"] for l in lanes] == ["Origin1", "Origin2"]


class TestFetchTradeLanesFailPath:
    """fetch_trade_lanes tolerates bad rows/values, and only raises for a missing file."""

    def test_row_with_no_separator_is_skipped_not_raised(self, tmp_path):
        csv_path = tmp_path / "lanes.csv"
        csv_path.write_text(
            "trade_lane,shipment_count\nInvalidRowNoSeparator,5\nOrigin - Dest,1\n", encoding="utf-8",
        )

        lanes = fetch_trade_lanes(str(csv_path))

        assert lanes == [{"start_location": "Origin", "end_location": "Dest", "shipment_count": 1}]

    def test_row_with_empty_trade_lane_is_skipped(self, tmp_path):
        csv_path = tmp_path / "lanes.csv"
        csv_path.write_text("trade_lane,shipment_count\n,3\nOrigin - Dest,1\n", encoding="utf-8")

        lanes = fetch_trade_lanes(str(csv_path))

        assert lanes == [{"start_location": "Origin", "end_location": "Dest", "shipment_count": 1}]

    def test_missing_shipment_count_defaults_to_zero(self, tmp_path):
        csv_path = tmp_path / "lanes.csv"
        csv_path.write_text("trade_lane,shipment_count\nOrigin - Destination,\n", encoding="utf-8")

        lanes = fetch_trade_lanes(str(csv_path))

        assert lanes == [{"start_location": "Origin", "end_location": "Destination", "shipment_count": 0}]

    def test_non_numeric_shipment_count_defaults_to_zero(self, tmp_path):
        csv_path = tmp_path / "lanes.csv"
        csv_path.write_text("trade_lane,shipment_count\nOrigin - Destination,N/A\n", encoding="utf-8")

        lanes = fetch_trade_lanes(str(csv_path))

        assert lanes[0]["shipment_count"] == 0

    def test_empty_csv_with_only_header_returns_empty_list(self, tmp_path):
        csv_path = tmp_path / "lanes.csv"
        csv_path.write_text("trade_lane,shipment_count\n", encoding="utf-8")

        assert fetch_trade_lanes(str(csv_path)) == []

    def test_missing_file_raises_file_not_found_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            fetch_trade_lanes(str(tmp_path / "does_not_exist.csv"))
