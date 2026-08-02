"""An oracle-free, provider-shaped synthetic search projection.

Issue #42 names the defect precisely: :class:`synthworld.exposures.SearchExposure`
carries ``match_kind`` and ``actual_persona_id`` on the same object as the title and
the locator. That is fine inside generator truth and wrong as an *input contract* -
a consumer exercising a search-provider path reads the answer alongside the result,
so its provider boundary cannot be tested offline at the trust boundary a real SERP
integration has.

The existing exposure model is frozen and stays. This is a separate projection
whose public half contains only what a provider would actually return.

**The public model forbids extra fields.** Not documents-them-as-unwanted: rejects
them. ``extra="forbid"`` means an adapter that tries to smuggle ``match_kind``
through gets a validation error rather than a passing test and a silent oracle, and
a contract test enumerates every forbidden name from the issue so the guarantee is
checked rather than asserted.

Truth lives in a physically separate bundle, joined to the public results only by
opaque result id, and only after a consumer has finished processing.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from urllib.parse import urlparse
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from synthworld.exposures import DataClass
from synthworld.models import SyntheticModel

SEARCH_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"

#: Every field name the issue lists as oracle-bearing. Named here so the contract
#: test enumerates the real list rather than a remembered subset, and so adding a
#: truth field to the wrong model is a test failure with a name attached.
FORBIDDEN_PUBLIC_FIELDS = frozenset(
    {
        "subject_persona_id",
        "canonical_persona_id",
        "actual_persona_id",
        "match_kind",
        "relevance_label",
        "expected_disposition",
        "removal_outcome",
        "broker_outcome",
        "scenario",
        "scenario_id",
        "difficulty",
    }
)


class SearchMatchTruth(StrEnum):
    """What a result actually is. Evaluator-only."""

    TRUE_MATCH = "true_match"
    FALSE_MATCH = "false_match"
    #: The result plausibly concerns the subject and the public text cannot settle
    #: it. A consumer that confidently accepts or rejects these is guessing.
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class PublicSearchResult(SyntheticModel):
    """One organic result, as a provider would return it.

    ``extra="forbid"`` is the contract. A field not listed here cannot be attached,
    so truth cannot leak in by accident or by a well-meaning adapter.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    rank: int = Field(ge=1)
    url: str
    title: str
    #: Optional because real providers truncate and sometimes omit snippets, and a
    #: consumer that assumes one is present is broken in a way worth surfacing.
    snippet: str | None = None
    observed_at: datetime | None = None
    source_name: str | None = None

    @model_validator(mode="after")
    def require_reserved_locator(self) -> Self:
        # Parse the host rather than searching the string. `.example.` anywhere in
        # a URL is satisfied by https://real-site.com/path/.example.test, which
        # defeats the whole point of a reserved domain.
        parsed = urlparse(self.url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            raise ValueError("search result URLs must be https")
        if not (
            host == "example.test"
            or host.endswith((".example.test", ".example.invalid"))
        ):
            raise ValueError("search result URLs must use a reserved example domain")
        return self


class PublicSearchResponse(SyntheticModel):
    """One page of results for one query. The whole public surface."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = SEARCH_SCHEMA_VERSION
    query: str
    page: int = Field(ge=1)
    #: What the provider was asked for, so a consumer can tell a short page from a
    #: page that was capped - a distinction that changes how you read the results.
    page_size: int = Field(ge=1)
    total_results_reported: int = Field(ge=0)
    results: tuple[PublicSearchResult, ...]

    @model_validator(mode="after")
    def require_dense_ascending_ranks(self) -> Self:
        ranks = [item.rank for item in self.results]
        if ranks != sorted(ranks):
            raise ValueError("results must be ordered by ascending rank")
        if len(set(ranks)) != len(ranks):
            raise ValueError("result ranks must be unique within a page")
        if len(self.results) > self.page_size:
            raise ValueError("a page cannot hold more results than its page size")
        return self


class SearchResultTruth(SyntheticModel):
    """Evaluator-only truth for one public result, joined by opaque id."""

    result_id: UUID
    subject_persona_id: str
    #: Whom the result is really about. Differs from the subject on a false match,
    #: which is what makes name collisions scoreable rather than merely present.
    actual_persona_id: str | None
    match: SearchMatchTruth
    planted_data_classes: tuple[DataClass, ...]
    #: Results syndicated from one source share a group, so a consumer that counts
    #: three copies as three findings can be caught doing it.
    syndication_group: str | None
    query_id: str
    difficulty: int = Field(ge=1, le=3)
    stale: bool = False


class SearchTruthBundle(SyntheticModel):
    schema_version: Literal["1.0.0"] = SEARCH_SCHEMA_VERSION
    #: Which projection this describes. Evaluator-side, so recording it here leaks
    #: nothing, and a score that cannot name its own seed is not reproducible.
    seed: int
    #: sha256 over the serialized public responses this truth describes. Physical
    #: separation without binding lets a truth bundle be paired with a different
    #: run's responses and still look coherent; the digest makes that detectable.
    public_digest: str
    results: tuple[SearchResultTruth, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_results_and_coherent_matches(self) -> Self:
        seen: set[UUID] = set()
        for item in self.results:
            if item.result_id in seen:
                raise ValueError("truth rows must be unique per result")
            seen.add(item.result_id)
            if item.match is SearchMatchTruth.TRUE_MATCH and (
                item.actual_persona_id != item.subject_persona_id
            ):
                raise ValueError("a true match must concern the subject")
            if item.match is SearchMatchTruth.FALSE_MATCH and (
                item.actual_persona_id is None
                or item.actual_persona_id == item.subject_persona_id
            ):
                # `None` is not "someone else" - it is nobody. Allowing it produced
                # a false match that named no one, which cannot be scored as a
                # collision and quietly shrinks identity-based evaluation.
                raise ValueError("a false match must concern someone else")
        return self


__all__ = [
    "FORBIDDEN_PUBLIC_FIELDS",
    "SEARCH_SCHEMA_VERSION",
    "PublicSearchResponse",
    "PublicSearchResult",
    "SearchMatchTruth",
    "SearchResultTruth",
    "SearchTruthBundle",
]
