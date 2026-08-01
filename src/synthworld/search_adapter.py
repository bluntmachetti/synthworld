"""A worked adapter from the provider-neutral projection to a consumer shape.

Issue #42 asks for one adapter mapping the neutral result to Idcognito's public
organic-result shape "without adding truth fields". The interesting part is the
*without*: an adapter is exactly where a truth field gets added by someone trying
to be helpful, because the truth is right there in the same process.

So the adapter takes only :class:`PublicSearchResponse` and cannot see truth at
all. The signature is the guarantee, and a contract test asserts the mapped shape
carries no forbidden name.
"""

from __future__ import annotations

from typing import Any

from synthworld.search import PublicSearchResponse, PublicSearchResult


def to_organic_result(result: PublicSearchResult) -> dict[str, Any]:
    """Map one neutral result to a typical consumer organic-result shape."""

    return {
        "position": result.rank,
        "link": result.url,
        "title": result.title,
        # Consumers generally expect a string; the neutral model keeps the
        # distinction between "absent" and "empty" and the adapter is where it is
        # deliberately collapsed, so the loss is visible in one place.
        "snippet": result.snippet or "",
        "source": result.source_name,
    }


def to_organic_response(response: PublicSearchResponse) -> dict[str, Any]:
    """Map one page. Takes public input only, so truth cannot be attached."""

    return {
        "search_query": response.query,
        "page": response.page,
        "organic_results": [to_organic_result(item) for item in response.results],
    }


__all__ = ["to_organic_response", "to_organic_result"]
