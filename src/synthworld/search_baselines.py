"""Reference decision policies for the search projection.

Three, because the trade only shows with a policy that can decline. All of them
consume the public response and the adapter output alone - none can see truth,
which is the property the signatures enforce rather than the comments.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable

from synthworld.search import PublicSearchResult
from synthworld.search_generator import SearchProjection
from synthworld.search_metrics import (
    ResultDecision,
    ResultJudgement,
    SearchEvaluation,
    evaluate_search_judgements,
)

Policy = Callable[[str, PublicSearchResult], ResultDecision]


def _folded(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(item for item in decomposed if not unicodedata.combining(item))


def accept_everything(_query: str, _result: PublicSearchResult) -> ResultDecision:
    """The floor. Finds every true match and every collision with it."""

    return ResultDecision.ACCEPT


def exact_name_in_title(query: str, result: PublicSearchResult) -> ResultDecision:
    """Accept when the query appears verbatim in the title.

    Fails the transliterated spelling of the same identity, which is the point of
    generating both.
    """

    return (
        ResultDecision.ACCEPT
        if query.casefold() in result.title.casefold()
        else ResultDecision.REJECT
    )


def folded_name_with_abstention(
    query: str, result: PublicSearchResult
) -> ResultDecision:
    """Normalise, then decline when the snippet gives nothing to corroborate.

    A result whose name matches but carries no snippet is exactly the case the
    public text cannot settle, so abstaining is the correct answer rather than a
    failure to answer.
    """

    if _folded(query) not in _folded(result.title):
        return ResultDecision.REJECT
    if not result.snippet:
        return ResultDecision.ABSTAIN
    return ResultDecision.ACCEPT


def run_search_baseline(
    policy: Policy, *, projection: SearchProjection
) -> SearchEvaluation:
    """Apply a policy across every page, then score. Truth is read only at the end."""

    judgements = [
        ResultJudgement(result_id=item.id, decision=policy(page.query, item))
        for page in projection.responses
        for item in page.results
    ]
    return evaluate_search_judgements(judgements, truth=projection.truth)


SEARCH_BASELINES: tuple[tuple[str, Policy], ...] = (
    ("Accept everything", accept_everything),
    ("Exact name in title", exact_name_in_title),
    ("Folded name, abstains without a snippet", folded_name_with_abstention),
)


__all__ = [
    "SEARCH_BASELINES",
    "Policy",
    "accept_everything",
    "exact_name_in_title",
    "folded_name_with_abstention",
    "run_search_baseline",
]
