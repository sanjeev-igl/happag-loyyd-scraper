"""XHR / Fetch response listener that captures Hapag-Lloyd quote API payloads."""

import json as _json
from playwright.async_api import Page, Request, Response

_KEYWORDS = ("quote", "offer", "rate", "freight")


class NetworkCapture:
    """Attach to a page and accumulate matching JSON API responses and request bodies."""

    def __init__(self) -> None:
        self.responses: list[dict] = []
        self.request_bodies: dict[str, dict] = {}  # url -> parsed POST body

    def attach(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    async def _on_request(self, request: Request) -> None:
        if request.method != "POST":
            return
        url = request.url
        if not any(kw in url.lower() for kw in _KEYWORDS):
            return
        try:
            raw = request.post_data
            if raw:
                self.request_bodies[url] = _json.loads(raw)
        except Exception:
            pass

    async def _on_response(self, response: Response) -> None:
        url = response.url
        if not any(kw in url.lower() for kw in _KEYWORDS):
            return
        if "application/json" not in response.headers.get("content-type", ""):
            return
        try:
            body = await response.json()
            self.responses.append({"url": url, "data": body})
            print(f"  [api] captured: {url}")
        except Exception:
            pass
