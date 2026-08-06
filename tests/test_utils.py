"""Unit tests for hapag_lloyd.extractors.utils (sync helpers only)."""

from hapag_lloyd.extractors.utils import parse_amount


class TestParseAmountHappyPath:
    """parse_amount successfully extracts a float from well-formed strings."""

    def test_simple_decimal_number_is_parsed(self):
        assert parse_amount("17805.00") == 17805.00

    def test_currency_prefix_is_ignored(self):
        assert parse_amount("USD 10.00") == 10.00

    def test_thousands_separator_comma_is_stripped(self):
        assert parse_amount("17,805.00") == 17805.00

    def test_plain_integer_string_is_parsed_as_float(self):
        assert parse_amount("42") == 42.0

    def test_surrounding_whitespace_is_stripped(self):
        assert parse_amount("  99.50  ") == 99.50

    def test_multiple_thousands_separators_are_all_stripped(self):
        assert parse_amount("1,234,567.89") == 1234567.89

    def test_first_number_is_used_when_string_has_trailing_text(self):
        assert parse_amount("10.00 per container") == 10.00


class TestParseAmountFailPath:
    """parse_amount returns None (never raises) when no number can be found."""

    def test_no_digits_returns_none(self):
        assert parse_amount("no digits here") is None

    def test_empty_string_returns_none(self):
        assert parse_amount("") is None

    def test_whitespace_only_string_returns_none(self):
        assert parse_amount("   ") is None

    def test_currency_code_alone_returns_none(self):
        assert parse_amount("USD") is None
