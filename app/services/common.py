MAX_QUERY_LENGTH = 200


class SearchError(Exception):
    """Base class for safe, user-facing search errors."""


class SearchNotConfigured(SearchError):
    pass


class SearchProviderError(SearchError):
    pass


def validate_query(query: str) -> str:
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("Zadejte klíčovou frázi.")
    if len(cleaned) > MAX_QUERY_LENGTH:
        raise ValueError(f"Dotaz může mít nejvýše {MAX_QUERY_LENGTH} znaků.")
    return cleaned
