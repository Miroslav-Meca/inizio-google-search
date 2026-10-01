from pathlib import Path

import httpx
import pytest

from app.models import SearchResponse
from app.services.google_client import GOOGLE_SEARCH_URL, GoogleHttpClient
from app.services.google_parser import GoogleBlockedError, GooglePageFormatError, parse_google_results
from app.services.google_search import GoogleSearchService
from app.services.search import SearchProviderError


FIXTURE = Path(__file__).parent / "fixtures" / "google_results.html"


def test_parser_extracts_organic_results_in_order_and_skips_ad():
    results = parse_google_results(FIXTURE.read_text(encoding="utf-8"))
    assert [result.position for result in results] == [1, 2, 3]
    assert [result.title for result in results] == [
        "Kavárna Příklad – Praha",
        "Kam na kávu v Praze",
        "Třetí výsledek",
    ]
    assert [result.url for result in results] == [
        "https://www.kavarna-priklad.cz/",
        "https://www.druhy-priklad.cz/clanek",
        "https://www.treti-priklad.cz/",
    ]
    assert results[0].snippet == "Výběrová káva a domácí dezerty v centru Prahy."
    assert results[2].snippet == ""
    assert all("Sponzorovaná" not in result.title for result in results)


@pytest.mark.parametrize("html", ["", "   ", "not html"])
def test_parser_returns_empty_for_empty_or_unrecognized_html(html):
    assert parse_google_results(html) == []


def test_parser_does_not_confuse_unknown_html_with_empty_results():
    with pytest.raises(GooglePageFormatError, match="nerozpoznal výsledkovou stránku"):
        parse_google_results("<html><title>Google Search</title><body>some unknown markup</body></html>")


def test_parser_accepts_google_explicit_no_results_message():
    assert parse_google_results(
        "<html><body>Your search did not match any documents.</body></html>"
    ) == []


@pytest.mark.parametrize(
    "html",
    [
        "<html><title>Before you continue to Google</title></html>",
        '<html><body>Our systems have detected unusual traffic</body></html>',
        '<html><body><div class="g-recaptcha"></div></body></html>',
        '<html><body>SG_REL<script>document.cookie="SG_SS=x"</script><a href="/httpservice/retry">retry</a></body></html>',
    ],
)
def test_parser_identifies_google_challenge_pages(html):
    with pytest.raises(GoogleBlockedError):
        parse_google_results(html)


@pytest.mark.asyncio
async def test_google_http_client_requests_search_html_directly():
    async def handler(request):
        assert str(request.url).startswith(GOOGLE_SEARCH_URL)
        assert request.url.params["q"] == "test dotaz"
        assert request.url.params["num"] == "10"
        assert "Firefox" in request.headers["user-agent"]
        return httpx.Response(200, text=FIXTURE.read_text(encoding="utf-8"), headers={"content-type": "text/html; charset=utf-8"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        html = await GoogleHttpClient(client).fetch_html(" test dotaz ")
    assert "Kavárna Příklad" in html


@pytest.mark.asyncio
async def test_google_http_client_reports_http_errors_without_fallback():
    async def handler(request):
        return httpx.Response(503, text="unavailable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SearchProviderError, match="HTTP 503"):
            await GoogleHttpClient(client).fetch_html("dotaz")


@pytest.mark.asyncio
async def test_google_http_client_reports_connection_failure():
    async def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SearchProviderError, match="Přímé spojení"):
            await GoogleHttpClient(client).fetch_html("dotaz")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 403, 429])
async def test_google_http_client_stops_on_redirect_or_access_limit(status):
    async def handler(request):
        return httpx.Response(status, headers={"location": "https://consent.google.com/"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        with pytest.raises(GoogleBlockedError, match="HTTP"):
            await GoogleHttpClient(client).fetch_html("dotaz")


@pytest.mark.asyncio
async def test_google_service_returns_shared_result_structure():
    fixture_html = FIXTURE.read_text(encoding="utf-8")

    class FakeGoogleClient:
        async def fetch_html(self, query):
            assert query == "kavárna Praha"
            return fixture_html

    response = await GoogleSearchService(FakeGoogleClient()).search("kavárna Praha")
    assert isinstance(response, SearchResponse)
    assert response.query == "kavárna Praha"
    assert response.results[0].position == 1
    assert response.results[0].title == "Kavárna Příklad – Praha"
    assert response.results[0].url.startswith("https://")
