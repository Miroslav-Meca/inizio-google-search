from __future__ import annotations

from app.models import SearchResponse
from app.services.google_client import GoogleHttpClient
from app.services.google_parser import parse_google_results
from app.services.search import validate_query


class GoogleSearchService:
    def __init__(self, client: GoogleHttpClient | None = None):
        self.client = client or GoogleHttpClient()

    async def search(self, query: str) -> SearchResponse:
        query = validate_query(query)
        html = await self.client.fetch_html(query)
        return SearchResponse(query=query, results=parse_google_results(html))
