from __future__ import annotations

import httpx

from app.services.common import SearchProviderError, validate_query
from app.services.google_parser import GoogleBlockedError


GOOGLE_SEARCH_URL = "https://www.google.com/search"
GOOGLE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
        "Gecko/20100101 Firefox/128.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}


class GoogleHttpClient:
    """Makes one direct request to Google Search without proxy or redirect use."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client

    async def fetch_html(self, query: str) -> str:
        query = validate_query(query)
        params = {"q": query, "num": 10, "hl": "cs", "gl": "cz"}
        try:
            if self.client:
                response = await self.client.get(
                    GOOGLE_SEARCH_URL, params=params, headers=GOOGLE_HEADERS
                )
            else:
                async with httpx.AsyncClient(
                    timeout=15.0,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    response = await client.get(
                        GOOGLE_SEARCH_URL, params=params, headers=GOOGLE_HEADERS
                    )
        except httpx.HTTPError as exc:
            raise SearchProviderError("Přímé spojení s Google Search selhalo.") from exc

        if response.status_code in {403, 429} or 300 <= response.status_code < 400:
            raise GoogleBlockedError(
                f"Google požadavek odmítl nebo přesměroval (HTTP {response.status_code})."
            )
        if response.status_code != 200:
            raise SearchProviderError(
                f"Google Search vrátil HTTP {response.status_code}."
            )
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            raise SearchProviderError("Google Search nevrátil HTML stránku.")
        return response.text
