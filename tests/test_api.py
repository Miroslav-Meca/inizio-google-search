import httpx
import pytest
import pytest_asyncio
from pathlib import Path

from app.main import create_app
from app.services.google_client import GoogleHttpClient
from app.services.google_parser import GoogleBlockedError, GooglePageFormatError
from app.services.google_search import GoogleSearchService
from app.services.search import SearchNotConfigured, SearchProviderError, SearchResponse, SearchResult, SerpApiSearchService


class MockSearchService:
    async def search(self, query):
        if query == "provider-error":
            raise SearchProviderError("Služba vyhledávání je dočasně nedostupná.")
        if query == "not-configured":
            raise SearchNotConfigured("Nastavte SERPAPI_API_KEY.")
        if query == "google-blocked":
            raise GoogleBlockedError("Google vrátil ochrannou nebo consent stránku.")
        if query == "unknown-google-html":
            raise GooglePageFormatError("Google vrátil HTML, ale parser v něm nerozpoznal výsledkovou stránku.")
        return SearchResponse(query, [
            SearchResult(1, "Výsledek A", "https://a.example", "Popis A"),
            SearchResult(2, "Výsledek B", "https://b.example", "Popis B"),
        ])


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app(MockSearchService()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_index_is_served(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Přirozené výsledky Google" in response.text


@pytest.mark.asyncio
async def test_search_endpoint_returns_ordered_results(client):
    response = await client.get("/api/search", params={"q": "  kavárna  "})
    assert response.status_code == 200
    assert [item["position"] for item in response.json()["results"]] == [1, 2]
    assert [item["title"] for item in response.json()["results"]] == ["Výsledek A", "Výsledek B"]
    assert set(response.json()["results"][0]) == {"position", "title", "url", "snippet"}
    assert response.json()["query"] == "kavárna"


@pytest.mark.parametrize("query", ["", "   "])
@pytest.mark.asyncio
async def test_search_endpoint_rejects_empty_query(client, query):
    assert (await client.get("/api/search", params={"q": query})).status_code == 422


@pytest.mark.asyncio
async def test_search_endpoint_rejects_long_query(client):
    assert (await client.get("/api/search", params={"q": "x" * 201})).status_code == 422


@pytest.mark.asyncio
async def test_search_endpoint_returns_provider_errors_as_safe_messages(client):
    response = await client.get("/api/search", params={"q": "provider-error"})
    assert response.status_code == 502
    assert response.json()["detail"] == "Služba vyhledávání je dočasně nedostupná."


@pytest.mark.asyncio
async def test_search_endpoint_reports_missing_api_key(client):
    assert (await client.get("/api/search", params={"q": "not-configured"})).status_code == 503


@pytest.mark.asyncio
async def test_default_active_provider_reports_missing_key_without_external_request(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "")
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        response = await api_client.get("/api/search", params={"q": "dotaz"})
    assert response.status_code == 503
    assert "SERPAPI_API_KEY" in response.json()["detail"]


@pytest.mark.asyncio
async def test_csv_endpoint_sets_download_headers_and_preserves_results(client):
    response = await client.get("/api/search", params={"q": "dotaz", "format": "csv"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert "Výsledek A" in response.text and "Výsledek B" in response.text


@pytest.mark.asyncio
async def test_unknown_export_format_is_rejected(client):
    assert (await client.get("/api/search", params={"q": "dotaz", "format": "xml"})).status_code == 422


@pytest.mark.asyncio
async def test_search_endpoint_reports_google_protection_without_fallback(client):
    response = await client.get("/api/search", params={"q": "google-blocked"})
    assert response.status_code == 502
    assert "ochrannou nebo consent" in response.json()["detail"]


@pytest.mark.asyncio
async def test_search_endpoint_does_not_report_unrecognized_html_as_empty_results(client):
    response = await client.get("/api/search", params={"q": "unknown-google-html"})
    assert response.status_code == 502
    assert "nerozpoznal výsledkovou stránku" in response.json()["detail"]


def test_serpapi_is_the_active_default_provider():
    assert isinstance(create_app().state.search_service, SerpApiSearchService)


@pytest.mark.asyncio
async def test_api_endpoint_runs_google_html_through_parser():
    fixture_path = Path(__file__).parent / "fixtures" / "google_results.html"
    fixture_html = fixture_path.read_text(encoding="utf-8")

    async def handler(request):
        return httpx.Response(200, text=fixture_html, headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as google_http:
        service = GoogleSearchService(GoogleHttpClient(google_http))
        api_transport = httpx.ASGITransport(app=create_app(service))
        async with httpx.AsyncClient(transport=api_transport, base_url="http://test") as api_client:
            response = await api_client.get("/api/search", params={"q": "kavárna Praha"})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "kavárna Praha"
    assert body["results"][0] == {
        "position": 1,
        "title": "Kavárna Příklad – Praha",
        "url": "https://www.kavarna-priklad.cz/",
        "snippet": "Výběrová káva a domácí dezerty v centru Prahy.",
    }


@pytest.mark.asyncio
async def test_api_endpoint_uses_mocked_serpapi_organic_results_only():
    async def handler(request):
        assert request.url.params["api_key"] == "test-key"
        return httpx.Response(200, json={
            "organic_results": [
                {"title": "Přirozený titul", "link": "https://result.example/", "snippet": "Výsledek."},
            ],
            "ads": [{"title": "Reklama", "link": "https://ad.example/"}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider_client:
        service = SerpApiSearchService(api_key="test-key", client=provider_client)
        api_transport = httpx.ASGITransport(app=create_app(service))
        async with httpx.AsyncClient(transport=api_transport, base_url="http://test") as api_client:
            response = await api_client.get("/api/search", params={"q": "Hrabyně"})

    assert response.status_code == 200
    assert response.json() == {
        "query": "Hrabyně",
        "results": [{
            "position": 1,
            "title": "Přirozený titul",
            "url": "https://result.example/",
            "snippet": "Výsledek.",
        }],
    }
