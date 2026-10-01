from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

import httpx

from app.models import SearchResponse, SearchResult
from app.services.common import (
    MAX_QUERY_LENGTH,
    SearchError,
    SearchNotConfigured,
    SearchProviderError,
    validate_query,
)


SERPAPI_URL = "https://serpapi.com/search.json"


def normalize_results(payload: dict[str, Any]) -> list[SearchResult]:
    """Keep only valid organic web results and preserve provider order."""
    results: list[SearchResult] = []
    for item in payload.get("organic_results", []):
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        link = item.get("link")
        if not isinstance(title, str) or not isinstance(link, str):
            continue
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        snippet = item.get("snippet")
        results.append(
            SearchResult(
                position=len(results) + 1,
                title=title,
                url=link,
                snippet=snippet if isinstance(snippet, str) else "",
            )
        )
    return results


class SerpApiSearchService:
    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        self.api_key = api_key if api_key is not None else os.getenv("SERPAPI_API_KEY", "")
        self.client = client

    async def search(self, query: str) -> SearchResponse:
        query = validate_query(query)
        if not self.api_key:
            raise SearchNotConfigured("Vyhledávání není nakonfigurované. Nastavte SERPAPI_API_KEY.")

        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "location": os.getenv("SERPAPI_LOCATION", "Prague, Czechia"),
            "hl": os.getenv("SERPAPI_LANGUAGE", "cs"),
            "gl": os.getenv("SERPAPI_COUNTRY", "cz"),
            "num": 10,
        }
        try:
            if self.client:
                response = await self.client.get(SERPAPI_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            else:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(SERPAPI_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchProviderError("Služba vyhledávání je dočasně nedostupná.") from exc

        if not isinstance(payload, dict) or payload.get("error"):
            raise SearchProviderError("Služba vyhledávání vrátila chybu.")
        return SearchResponse(query=query, results=normalize_results(payload))


def response_dict(response: SearchResponse) -> dict[str, Any]:
    return {"query": response.query, "results": [asdict(result) for result in response.results]}


def results_to_csv(response: SearchResponse) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["position", "title", "url", "snippet"])
    writer.writeheader()
    writer.writerows(asdict(result) for result in response.results)
    return output.getvalue()


def results_to_json(response: SearchResponse) -> str:
    return json.dumps(response_dict(response), ensure_ascii=False, indent=2)
