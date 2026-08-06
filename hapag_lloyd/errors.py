"""Specific exception types for scrape failures, so checkpoint.json records what
actually went wrong instead of a generic Playwright timeout message."""


class ScrapeError(Exception):
    """Base class for classified scrape failures. `reason` is a short, stable
    machine-readable tag (used as a prefix in the checkpoint error string) and
    stays constant even if the human-readable message text changes."""

    reason = "unknown_error"


class SearchFormNotFoundError(ScrapeError):
    reason = "search_form_not_found"


class LocationDropdownError(ScrapeError):
    reason = "location_dropdown_timeout"


class InvalidLocationError(ScrapeError):
    reason = "invalid_location"


class UIBlockedError(ScrapeError):
    reason = "ui_blocked_by_overlay"


class PermissionDeniedError(ScrapeError):
    reason = "permission_denied"


class OfferSelectionPageError(ScrapeError):
    reason = "offer_selection_page_not_loaded"


class NoOffersFoundError(ScrapeError):
    reason = "no_offers_found"


class NoSpotRateError(ScrapeError):
    reason = "no_spot_rate"


class LoginFailedError(ScrapeError):
    reason = "login_failed"


class NetworkUnavailableError(ScrapeError):
    reason = "network_unavailable"


def classify_exception(exc: Exception) -> str:
    """Best-effort classification for exceptions raised as raw Playwright/asyncio
    errors rather than one of the ScrapeError subclasses above (e.g. errors raised
    from deep inside Playwright itself). Returns a short reason tag."""
    if isinstance(exc, ScrapeError):
        return exc.reason

    msg = str(exc).lower()
    type_name = type(exc).__name__

    if "playwrighttimeouterror" in type_name.lower() or "timeouterror" in type_name.lower():
        if "net::err_connection" in msg or "net::err_name_not_resolved" in msg:
            return "network_unavailable"
        if "intercepts pointer events" in msg or "subtree intercepts pointer events" in msg:
            return "ui_blocked_by_overlay"
        return "playwright_timeout"
    if "net::err_connection_refused" in msg or "net::err_connection_closed" in msg:
        return "connection_refused"
    if "net::err_name_not_resolved" in msg or "net::err_internet_disconnected" in msg:
        return "network_unavailable"
    if "econnreset" in msg or "socket hang up" in msg:
        return "connection_reset"
    if "target page, context or browser has been closed" in msg or "target closed" in msg:
        return "browser_closed"
    if "navigation" in msg and "timeout" in msg:
        return "navigation_timeout"
    return f"unclassified:{type_name}"


def format_checkpoint_error(exc: Exception) -> str:
    """Build the string stored in checkpoint.json: '<reason_tag>: <message>'."""
    reason = classify_exception(exc)
    return f"{reason}: {exc}"
