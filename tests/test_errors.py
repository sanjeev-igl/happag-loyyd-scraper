"""Unit tests for hapag_lloyd.errors."""

from hapag_lloyd.errors import (
    InvalidLocationError,
    LocationDropdownError,
    NoOffersFoundError,
    ScrapeError,
    SearchFormNotFoundError,
    classify_exception,
    format_checkpoint_error,
)


class TestClassifyExceptionScrapeErrorHappyPath:
    """A ScrapeError subclass is classified by its own stable `reason` tag,
    regardless of its message text."""

    def test_search_form_not_found_error_uses_its_reason_tag(self):
        assert classify_exception(SearchFormNotFoundError("form missing")) == "search_form_not_found"

    def test_location_dropdown_error_uses_its_reason_tag(self):
        assert classify_exception(LocationDropdownError()) == "location_dropdown_timeout"

    def test_invalid_location_error_uses_its_reason_tag(self):
        assert classify_exception(InvalidLocationError("bad port")) == "invalid_location"

    def test_no_offers_found_error_uses_its_reason_tag(self):
        assert classify_exception(NoOffersFoundError()) == "no_offers_found"

    def test_base_scrape_error_uses_the_default_unknown_reason(self):
        assert classify_exception(ScrapeError("something")) == "unknown_error"


class TestClassifyExceptionTimeoutHappyPath:
    """A raw Playwright/asyncio TimeoutError is pattern-matched on its message
    to a more specific reason before falling back to a generic timeout tag."""

    def test_connection_refused_message_in_a_timeout_is_network_unavailable(self):
        exc = TimeoutError("net::ERR_CONNECTION_REFUSED at https://example.com")
        assert classify_exception(exc) == "network_unavailable"

    def test_name_not_resolved_message_in_a_timeout_is_network_unavailable(self):
        exc = TimeoutError("net::ERR_NAME_NOT_RESOLVED")
        assert classify_exception(exc) == "network_unavailable"

    def test_intercepts_pointer_events_message_is_ui_blocked_by_overlay(self):
        exc = TimeoutError("element subtree intercepts pointer events")
        assert classify_exception(exc) == "ui_blocked_by_overlay"

    def test_plain_timeout_message_falls_back_to_playwright_timeout(self):
        exc = TimeoutError("Timeout 15000ms exceeded waiting for selector")
        assert classify_exception(exc) == "playwright_timeout"

    def test_matching_is_case_insensitive(self):
        exc = TimeoutError("NET::ERR_CONNECTION_REFUSED")
        assert classify_exception(exc) == "network_unavailable"


class TestClassifyExceptionNonTimeoutHappyPath:
    """Non-timeout exceptions are classified by message content alone."""

    def test_connection_refused_is_connection_refused(self):
        assert classify_exception(Exception("net::ERR_CONNECTION_REFUSED")) == "connection_refused"

    def test_connection_closed_is_connection_refused(self):
        assert classify_exception(Exception("net::ERR_CONNECTION_CLOSED")) == "connection_refused"

    def test_name_not_resolved_is_network_unavailable(self):
        assert classify_exception(Exception("net::ERR_NAME_NOT_RESOLVED")) == "network_unavailable"

    def test_internet_disconnected_is_network_unavailable(self):
        assert classify_exception(Exception("net::ERR_INTERNET_DISCONNECTED")) == "network_unavailable"

    def test_econnreset_is_connection_reset(self):
        assert classify_exception(Exception("ECONNRESET")) == "connection_reset"

    def test_socket_hang_up_is_connection_reset(self):
        assert classify_exception(Exception("socket hang up")) == "connection_reset"

    def test_target_closed_message_is_browser_closed(self):
        assert classify_exception(Exception("Target page, context or browser has been closed")) == "browser_closed"

    def test_short_target_closed_message_is_browser_closed(self):
        assert classify_exception(Exception("target closed")) == "browser_closed"

    def test_navigation_and_timeout_together_is_navigation_timeout(self):
        assert classify_exception(Exception("navigation timeout of 30000ms exceeded")) == "navigation_timeout"


class TestClassifyExceptionFailPath:
    """Unrecognized exceptions never raise — they degrade to an 'unclassified:<Type>' tag."""

    def test_unrecognized_exception_is_unclassified_with_type_name(self):
        class WeirdError(Exception):
            pass

        assert classify_exception(WeirdError("mystery")) == "unclassified:WeirdError"

    def test_generic_exception_with_unrelated_message_is_unclassified(self):
        assert classify_exception(Exception("something totally unrelated")) == "unclassified:Exception"

    def test_navigation_without_timeout_is_not_navigation_timeout(self):
        assert classify_exception(Exception("navigation to page failed")) == "unclassified:Exception"


class TestFormatCheckpointError:
    """format_checkpoint_error prefixes the exception message with its classified reason tag."""

    def test_scrape_error_is_formatted_as_reason_colon_message(self):
        assert format_checkpoint_error(SearchFormNotFoundError("no form")) == "search_form_not_found: no form"

    def test_raw_exception_is_formatted_with_its_classified_reason(self):
        assert format_checkpoint_error(Exception("ECONNRESET")) == "connection_reset: ECONNRESET"

    def test_exception_with_empty_message_still_includes_the_reason_prefix(self):
        assert format_checkpoint_error(NoOffersFoundError()) == "no_offers_found: "
