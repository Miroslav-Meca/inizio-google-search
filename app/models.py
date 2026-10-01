from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    position: int
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class SearchResponse:
    query: str
    results: list[SearchResult]
