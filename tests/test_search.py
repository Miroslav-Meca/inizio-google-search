import csv
import io
import json

import httpx
import pytest

from app.services.search import (
    SearchProviderError,
    SerpApiSearchService,
    normalize_results,
    results_to_csv,
    results_to_json,
    validate_query,
)


def test_validate_query_trims_valid_query():
    assert validate_query("  test dotaz  ") == "test dotaz"


@pytest.mark.parametrize("query", ["", "   "])
def test_validate_query_rejects_empty(query):
    with pytest.raises(ValueError):
        validate_query(query)


def test_validate_query_rejects_overlong_query():
    with pytest.raises(ValueError, match="200"):
        validate_query("x" * 201)


def test_normalize_results_keeps_organic_order_and_drops_bad_urls():
    results = normalize_results({"organic_results": [
        {"title": "První", "link": "https://example.cz/1", "snippet": "Popis 1"},
        {"title": "Reklama", "link": "javascript:alert(1)"},
        {"title": "Druhý", "link": "https://example.cz/2"},
    ], "ads": [{"title": "Nepatří sem", "link": "https://ad.example"}]})
    assert [(r.position, r.title) for r in results] == [(1, "První"), (2, "Druhý")]
    assert results[1].snippet == ""


def test_json_export_has_expected_structure():
    from app.services.search import SearchResponse, SearchResult
    response = SearchResponse("dotaz", [SearchResult(1, "T", "https://example.cz", "S")])
    assert json.loads(results_to_json(response)) == {
        "query": "dotaz",
        "results": [{"position": 1, "title": "T", "url": "https://example.cz", "snippet": "S"}],
    }


def test_csv_export_has_expected_fields_and_content():
    from app.services.search import SearchResponse, SearchResult
    response = SearchResponse("dotaz", [SearchResult(1, 'Název, "A"', "https://example.cz", "Řádek\ntext")])
    rows = list(csv.DictReader(io.StringIO(results_to_csv(response))))
    assert rows == [{"position": "1", "title": 'Název, "A"', "url": "https://example.cz", "snippet": "Řádek\ntext"}]


@pytest.mark.asyncio
async def test_provider_error_is_reported_without_leaking_details():
    async def handler(request):
        return httpx.Response(503, text="private provider detail")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = SerpApiSearchService(api_key="test-key", client=client)
        with pytest.raises(SearchProviderError, match="dočasně nedostupná"):
            await service.search("dotaz")


@pytest.mark.asyncio
async def test_serpapi_service_maps_only_ordered_organic_results():
    async def handler(request):
        assert request.url.path == "/search.json"
        assert request.url.params["engine"] == "google"
        assert request.url.params["q"] == "Hrabyně"
        assert request.url.params["api_key"] == "test-backend-key"
        return httpx.Response(200, json={
            "organic_results": [
                {"position": 1, "title": "První přirozený výsledek", "link": "https://one.example/", "snippet": "Popis první."},
                {"position": 2, "title": "Druhý přirozený výsledek", "link": "https://two.example/", "snippet": "Popis druhý."},
            ],
            "ads": [{"title": "Reklama", "link": "https://ad.example/"}],
            "shopping_results": [{"title": "Produkt", "link": "https://shop.example/"}],
            "knowledge_graph": {"title": "Panel znalostí"},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = SerpApiSearchService(api_key="test-backend-key", client=client)
        response = await service.search("Hrabyně")

    assert [(r.position, r.title, r.url, r.snippet) for r in response.results] == [
        (1, "První přirozený výsledek", "https://one.example/", "Popis první."),
        (2, "Druhý přirozený výsledek", "https://two.example/", "Popis druhý."),
    ]


@pytest.mark.asyncio
async def test_serpapi_service_requires_key_without_making_request():
    service = SerpApiSearchService(api_key="")
    from app.services.common import SearchNotConfigured
    with pytest.raises(SearchNotConfigured, match="SERPAPI_API_KEY"):
        await service.search("dotaz")
