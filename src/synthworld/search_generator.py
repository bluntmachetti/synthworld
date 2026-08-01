"""Deterministic generation of the oracle-free search projection.

Every behaviour issue #42 lists is planted deliberately and is assertable from the
artifacts: a test names each one and fails if a seed stops producing it. Generating
them by chance would mean a variant could quietly lose a case and still look busy.

Nothing here is a model of any search engine's ranking. It emulates the *data
boundary* and a set of controlled failure modes - the shapes that break consumers -
which is what can be tested offline and what a live provider cannot give you
reproducibly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import blake2b, sha256
from typing import Literal
from uuid import UUID

from pydantic import Field

from synthworld.exposures import DataClass
from synthworld.models import SyntheticModel
from synthworld.search import (
    SEARCH_SCHEMA_VERSION,
    PublicSearchResponse,
    PublicSearchResult,
    SearchMatchTruth,
    SearchResultTruth,
    SearchTruthBundle,
)

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_SUBJECTS = (
    ("persona-0001", "Ana Sørensen", "Ana Sorensen"),
    ("persona-0002", "Renée Blackwood", "Renee Blackwood"),
    ("persona-0003", "Yusuf Çelik", "Yusuf Celik"),
)
_NOISE_TITLES = (
    "Example directory listing",
    "Test community notice",
    "Sample conference programme",
)


@dataclass(frozen=True)
class _Planned:
    """One planted result: what the provider shows, and what is true about it."""

    key: str
    url: str
    title: str
    snippet: str | None
    observed_at: datetime
    source_name: str
    subject_persona_id: str
    actual_persona_id: str | None
    match: SearchMatchTruth
    planted_data_classes: tuple[DataClass, ...]
    syndication_group: str | None
    query_id: str
    difficulty: int
    stale: bool


class SearchConfig(SyntheticModel):
    page_size: int = Field(default=5, ge=3, le=20)
    #: Enough pages to serve every planted result. Fewer would drop planted cases,
    #: and *which* ones would depend on the seed - so declared prevalence would not
    #: survive a seed change, which is the property issue #42 asks variants to keep.
    #: The provider's cap is represented instead by `total_results_reported`, which
    #: is deliberately larger than what any page serves.
    pages_per_query: int = Field(default=3, ge=1, le=5)


class SearchProjection(SyntheticModel):
    """Public responses and the physically separate truth they are joined to."""

    schema_version: Literal["1.0.0"] = SEARCH_SCHEMA_VERSION
    seed: int
    responses: tuple[PublicSearchResponse, ...] = Field(min_length=1)
    truth: SearchTruthBundle


def _draw(seed: int, purpose: str, index: int) -> int:
    material = f"search|{seed}|{purpose}|{index}"
    return int.from_bytes(blake2b(material.encode(), digest_size=8).digest(), "big")


def _result_id(seed: int, key: str) -> UUID:
    return UUID(bytes=blake2b(f"{seed}|{key}".encode(), digest_size=16).digest())


def generate_search_projection(
    *, seed: int, config: SearchConfig | None = None
) -> SearchProjection:
    """Generate every required SERP behaviour for a seed, deterministically."""

    settings = config if config is not None else SearchConfig()
    responses: list[PublicSearchResponse] = []
    truth: list[SearchResultTruth] = []

    for subject_index, (persona, display, transliterated) in enumerate(_SUBJECTS):
        query_id = f"query-{subject_index + 1:03d}"
        planned = _planned_results(
            seed=seed,
            subject_index=subject_index,
            persona=persona,
            display=display,
            transliterated=transliterated,
            query_id=query_id,
        )
        # Rank and order change with the seed while the planted set does not, so a
        # consumer keyed on position rather than content breaks here.
        ordered = sorted(
            planned, key=lambda item: _draw(seed, f"rank:{item.key}", subject_index)
        )
        size = settings.page_size
        # BOTH spellings of the same identity, not one spelling each for different
        # people. An earlier revision alternated by subject, so a consumer that
        # normalises one direction and not the other was never exercised - and the
        # comment claimed the opposite, which is worse than the gap itself.
        for spelling, query in enumerate((display, transliterated)):
            for page in range(1, settings.pages_per_query + 1):
                window = ordered[(page - 1) * size : page * size]
                if not window:
                    continue
                results = []
                for offset, item in enumerate(window):
                    identifier = _result_id(seed, f"{spelling}:{item.key}")
                    results.append(
                        PublicSearchResult(
                            id=identifier,
                            rank=(page - 1) * size + offset + 1,
                            url=item.url,
                            title=item.title,
                            snippet=item.snippet,
                            observed_at=item.observed_at,
                            source_name=item.source_name,
                        )
                    )
                    truth.append(
                        SearchResultTruth(
                            result_id=identifier,
                            subject_persona_id=item.subject_persona_id,
                            actual_persona_id=item.actual_persona_id,
                            match=item.match,
                            planted_data_classes=item.planted_data_classes,
                            syndication_group=item.syndication_group,
                            query_id=query_id,
                            difficulty=item.difficulty,
                            stale=item.stale,
                        )
                    )
                responses.append(
                    PublicSearchResponse(
                        query=query,
                        page=page,
                        page_size=size,
                        # Deliberately larger than what is returned: providers
                        # report a total they do not serve, and a consumer that
                        # treats the cap as the whole result set is wrong in a way
                        # worth catching.
                        total_results_reported=len(ordered) + 7,
                        results=tuple(results),
                    )
                )
    ordered_responses = tuple(responses)
    return SearchProjection(
        seed=seed,
        responses=ordered_responses,
        truth=SearchTruthBundle(
            public_digest=public_digest(ordered_responses), results=tuple(truth)
        ),
    )


def public_digest(responses: tuple[PublicSearchResponse, ...]) -> str:
    """Digest the public half exactly as a consumer would receive it."""

    joined = "\n".join(item.model_dump_json() for item in responses)
    return sha256(joined.encode("utf-8")).hexdigest()


def _planned_results(
    *,
    seed: int,
    subject_index: int,
    persona: str,
    display: str,
    transliterated: str,
    query_id: str,
) -> list[_Planned]:
    """One planted set per subject, covering every required behaviour."""

    other = _SUBJECTS[(subject_index + 1) % len(_SUBJECTS)][0]
    stamp = _EPOCH + timedelta(days=_draw(seed, "when", subject_index) % 300)
    stale_stamp = _EPOCH - timedelta(days=900)
    domain = f"records{subject_index}.example.test"
    plan: list[_Planned] = []

    def add(
        key: str,
        *,
        title: str,
        snippet: str | None,
        match: SearchMatchTruth,
        actual: str | None,
        classes: tuple[DataClass, ...] = (),
        group: str | None = None,
        observed: datetime | None = None,
        stale: bool = False,
        difficulty: int = 1,
        path: str | None = None,
    ) -> None:
        plan.append(
            _Planned(
                key=f"{query_id}:{key}",
                url=f"https://{domain}/{path or key}",
                title=title,
                snippet=snippet,
                observed_at=observed if observed is not None else stamp,
                source_name="Example Records",
                subject_persona_id=persona,
                actual_persona_id=actual,
                match=match,
                planted_data_classes=classes,
                syndication_group=group,
                query_id=query_id,
                difficulty=difficulty,
                stale=stale,
            )
        )

    add(
        "true-profile",
        title=f"{display} - profile",
        snippet=f"{display} works at Example Works.",
        match=SearchMatchTruth.TRUE_MATCH,
        actual=persona,
        classes=(DataClass.EMPLOYER,),
    )
    # Literal same-name collision: identical rendered name, different person.
    add(
        "collision",
        title=f"{display} - directory entry",
        snippet=f"{display} lives in Sampleton.",
        match=SearchMatchTruth.FALSE_MATCH,
        actual=other,
        classes=(DataClass.ADDRESS,),
        difficulty=3,
    )
    # Insufficient: plausible, and the public text cannot settle it.
    add(
        "ambiguous",
        title=f"{display} mentioned in a notice",
        snippet=None,
        match=SearchMatchTruth.INSUFFICIENT_EVIDENCE,
        actual=None,
        difficulty=3,
    )
    # Syndication: one source, three aggregators. Counting them separately
    # overstates exposure threefold.
    for copy in range(3):
        add(
            f"syndicated-{copy}",
            title=f"{display} - listing",
            snippet=f"Contact {display} via Example Records.",
            match=SearchMatchTruth.TRUE_MATCH,
            actual=persona,
            classes=(DataClass.EMAIL,),
            group=f"{query_id}:syndicated",
            path=f"syndicated/{copy}",
        )
    # Truncated snippet, then a missing one.
    add(
        "truncated",
        title=f"{display} - archived record",
        snippet=f"{display} previously listed at Example Aven…",
        match=SearchMatchTruth.TRUE_MATCH,
        actual=persona,
        classes=(DataClass.ADDRESS,),
        difficulty=2,
    )
    # Stale: observed long ago, and flagged as such in truth only.
    add(
        "stale",
        title=f"{display} - old profile",
        snippet=f"{display} at a former employer.",
        match=SearchMatchTruth.TRUE_MATCH,
        actual=persona,
        classes=(DataClass.EMPLOYER,),
        observed=stale_stamp,
        stale=True,
        difficulty=2,
    )
    # Transliterated rendering of the same person.
    add(
        "transliterated",
        title=f"{transliterated} - alumni note",
        snippet=f"{transliterated} graduated from Test Academy.",
        match=SearchMatchTruth.TRUE_MATCH,
        actual=persona,
        classes=(DataClass.EDUCATION,),
        difficulty=2,
    )
    # Noise: about nobody in the population.
    for index, title in enumerate(_NOISE_TITLES):
        add(
            f"noise-{index}",
            title=title,
            snippet="An unrelated example page.",
            match=SearchMatchTruth.FALSE_MATCH,
            actual=f"persona-unrelated-{index}",
            path=f"noise/{index}",
        )
    return plan


__all__ = [
    "SearchConfig",
    "SearchProjection",
    "generate_search_projection",
    "public_digest",
]
