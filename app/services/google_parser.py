from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from app.models import SearchResult
from app.services.common import SearchProviderError


class GoogleBlockedError(Exception):
    """Google returned a consent, CAPTCHA, or other access challenge page."""


class GooglePageFormatError(SearchProviderError):
    """Google returned HTML that is not a recognized results page."""


_CHALLENGE_MARKERS = (
    "consent.google.com",
    "before you continue to google",
    "our systems have detected unusual traffic",
    "unusual traffic from your computer network",
    "/sorry/index",
    "g-recaptcha",
    "recaptcha/api.js",
    "sg_rel",
    "sg_ss=",
    "/httpservice/retry",
    "potíže s přístupem k vyhledávání google",
)
_NO_RESULTS_MARKERS = (
    "did not match any documents",
    "no results found",
    "nebyly nalezeny žádné dokumenty",
    "neodpovídá žádným dokumentům",
)
_AD_CLASSES = {"uEierd", "commercial-unit-desktop-top", "commercial-unit-desktop-rhs"}
_SNIPPET_CLASSES = ("VwiC3b", "aCOpRe", "IsZvec")


def _is_ad(card) -> bool:
    for ancestor in (card, *card.parents):
        classes = set(ancestor.get("class", []))
        if classes & _AD_CLASSES or ancestor.has_attr("data-text-ad"):
            return True
        for label in ancestor.select('[aria-label]'):
            value = label.get("aria-label", "").strip().lower()
            if value in {"ad", "sponsored", "sponzorováno", "reklama"}:
                return True
        # Do not climb out of a result card into the page-level containers.
        if ancestor.name == "div" and "MjjYud" in classes:
            break
    return False


def _result_url(href: str) -> str | None:
    parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"}:
        return None

    # Google sometimes wraps an outbound result in /url?q=... .
    if parsed.hostname and parsed.hostname.lower().endswith("google.com") and parsed.path == "/url":
        params = parse_qs(parsed.query)
        target = (params.get("q") or params.get("url") or [None])[0]
        if target:
            parsed = urlparse(target)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.hostname and parsed.hostname.lower().endswith("google.com"):
        return None
    return parsed.geturl()


def parse_google_results(html: str) -> list[SearchResult]:
    """Parse organic web result cards from a Google Search HTML response.

    This deliberately parses only recognizable organic result containers; it
    does not attempt to interpret other SERP modules as web results.
    """
    if not isinstance(html, str) or not html.strip():
        return []

    lowered = html.lower()
    if any(marker in lowered for marker in _CHALLENGE_MARKERS):
        raise GoogleBlockedError("Google vrátil ochrannou nebo consent stránku.")

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.MjjYud, div.g")
    results: list[SearchResult] = []
    seen: set[str] = set()

    for card in cards:
        if _is_ad(card):
            continue
        heading = card.select_one("a h3")
        if heading is None:
            continue
        link = heading.find_parent("a", href=True)
        if link is None:
            continue
        url = _result_url(link["href"])
        title = heading.get_text(" ", strip=True)
        if not title or not url or url in seen:
            continue

        snippet = ""
        for class_name in _SNIPPET_CLASSES:
            snippet_node = card.select_one(f".{class_name}")
            if snippet_node:
                snippet = snippet_node.get_text(" ", strip=True)
                if snippet:
                    break

        seen.add(url)
        results.append(SearchResult(len(results) + 1, title, url, snippet))

    if results:
        return results
    if any(marker in lowered for marker in _NO_RESULTS_MARKERS):
        return []
    # An empty parse of an unrecognized HTML page is not evidence that Google
    # returned an empty SERP. Fail visibly instead of telling the user no
    # organic results exist.
    if soup.find("html") or cards:
        raise GooglePageFormatError(
            "Google vrátil HTML, ale parser v něm nerozpoznal výsledkovou stránku."
        )
    return results
