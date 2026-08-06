"""Unit tests for the synchronous parts of hapag_lloyd.network.NetworkCapture
(construction and has_v4_offer — the keyword-filtered response/request capture
itself requires a live Playwright Page and is exercised end-to-end instead)."""

from hapag_lloyd.network import NetworkCapture


class TestNetworkCaptureInitHappyPath:
    """A freshly constructed NetworkCapture starts with empty response/body stores."""

    def test_responses_starts_empty(self):
        assert NetworkCapture().responses == []

    def test_request_bodies_starts_empty(self):
        assert NetworkCapture().request_bodies == {}


class TestHasV4OfferHappyPath:
    """has_v4_offer is True once a non-status /api/v4/offers/ response has been captured."""

    def test_true_when_a_v4_offer_response_is_present(self):
        capture = NetworkCapture()
        capture.responses.append({"url": "https://api.hapag-lloyd.com/api/v4/offers/abc123", "data": {}})

        assert capture.has_v4_offer() is True

    def test_true_when_v4_offer_is_one_of_several_captured_responses(self):
        capture = NetworkCapture()
        capture.responses.append({"url": "https://api.hapag-lloyd.com/api/v3/offers/offer", "data": {}})
        capture.responses.append({"url": "https://api.hapag-lloyd.com/api/v4/offers/abc123", "data": {}})

        assert capture.has_v4_offer() is True


class TestHasV4OfferFailPath:
    """has_v4_offer stays False for an empty capture, non-v4 URLs, or a v4 status-polling URL."""

    def test_false_when_no_responses_captured_yet(self):
        assert NetworkCapture().has_v4_offer() is False

    def test_false_for_v3_offer_responses_only(self):
        capture = NetworkCapture()
        capture.responses.append({"url": "https://api.hapag-lloyd.com/api/v3/offers/offer", "data": {}})

        assert capture.has_v4_offer() is False

    def test_false_for_a_v4_status_polling_url(self):
        # "/status" is explicitly excluded so in-flight polling isn't mistaken
        # for the final priced offer.
        capture = NetworkCapture()
        capture.responses.append({"url": "https://api.hapag-lloyd.com/api/v4/offers/abc123/status", "data": {}})

        assert capture.has_v4_offer() is False
