"""The oracle-free search projection: what it must contain, and must not."""

from __future__ import annotations

from collections import Counter

import pytest
from pydantic import ValidationError

from synthworld.search import (
    FORBIDDEN_PUBLIC_FIELDS,
    PublicSearchResponse,
    PublicSearchResult,
    SearchMatchTruth,
    SearchResultTruth,
    SearchTruthBundle,
)
from synthworld.search_adapter import to_organic_response
from synthworld.search_generator import (
    SearchConfig,
    generate_search_projection,
    public_digest,
)

_SEEDS = (1, 2, 3)


def test_public_models_reject_every_oracle_field_the_issue_lists() -> None:
    """The contract, enumerated rather than remembered.

    `extra="forbid"` means an adapter cannot smuggle truth through, and naming the
    whole list here means a field added to the wrong model fails with a name
    attached instead of passing quietly.
    """

    from uuid import UUID

    base = {
        "id": UUID(int=1),
        "rank": 1,
        "url": "https://records.example.test/x",
        "title": "t",
    }
    for field in FORBIDDEN_PUBLIC_FIELDS:
        with pytest.raises(ValidationError, match=r"extra_forbidden|Extra inputs"):
            PublicSearchResult(**base, **{field: "leak"})  # type: ignore[arg-type]


def test_no_public_model_declares_a_forbidden_field() -> None:
    """The static half: forbidding extras is useless if truth is a declared field."""

    for model in (PublicSearchResult, PublicSearchResponse):
        assert not FORBIDDEN_PUBLIC_FIELDS & set(model.model_fields)


def test_truth_models_are_never_reachable_from_the_public_half() -> None:
    """Prevents a truth model becoming a public result input by annotation.

    A field typed as a truth model would carry the oracle regardless of
    `extra="forbid"`, so the check is on the annotations rather than the values.
    """

    truth_names = {"SearchResultTruth", "SearchTruthBundle", "SearchMatchTruth"}
    for model in (PublicSearchResult, PublicSearchResponse):
        for field in model.model_fields.values():
            assert str(field.annotation).split(".")[-1].strip("'>") not in truth_names


def test_the_public_organic_adapter_consumes_public_data_only() -> None:
    projection = generate_search_projection(seed=1)
    mapped = to_organic_response(projection.responses[0])

    serialized = str(mapped)
    for field in FORBIDDEN_PUBLIC_FIELDS:
        assert field not in serialized
    assert mapped["organic_results"][0]["position"] == 1


@pytest.mark.parametrize("seed", _SEEDS)
def test_every_required_serp_behaviour_is_present(seed: int) -> None:
    """Each behaviour issue #42 lists, asserted from the artifacts.

    Planted deliberately rather than left to chance, so a seed that stops producing
    one fails here instead of quietly shrinking the test surface.
    """

    projection = generate_search_projection(seed=seed)
    truth = {item.result_id: item for item in projection.truth.results}
    results = [item for page in projection.responses for item in page.results]
    matches = Counter(item.match for item in projection.truth.results)

    # true, false and insufficient in the same projection
    assert matches[SearchMatchTruth.TRUE_MATCH] > 0
    assert matches[SearchMatchTruth.FALSE_MATCH] > 0
    assert matches[SearchMatchTruth.INSUFFICIENT_EVIDENCE] > 0
    # literal same-name collisions: a false match whose title carries the query name
    collisions = [
        truth[item.id].actual_persona_id
        for item in results
        if truth[item.id].match is SearchMatchTruth.FALSE_MATCH
    ]
    assert any(
        other is not None and other.startswith("persona-00") for other in collisions
    )
    # syndicated duplicates
    groups = Counter(
        item.syndication_group
        for item in projection.truth.results
        if item.syndication_group
    )
    assert max(groups.values()) >= 3
    # missing and truncated snippets
    assert any(item.snippet is None for item in results)
    assert any(
        item.snippet is not None and item.snippet.endswith("…") for item in results
    )
    # noise
    unrelated = [
        item.actual_persona_id
        for item in projection.truth.results
        if item.actual_persona_id is not None
    ]
    assert any(other.startswith("persona-unrelated") for other in unrelated)
    # stale observations
    assert any(item.stale for item in projection.truth.results)
    # Unicode and transliterated variants of the SAME identity, not one spelling
    # each for different people - otherwise a consumer that normalises one
    # direction and not the other is never exercised.
    import unicodedata

    def folded(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        return "".join(item for item in decomposed if not unicodedata.combining(item))

    spellings: dict[str, set[str]] = {}
    for page in projection.responses:
        spellings.setdefault(folded(page.query), set()).add(page.query)
    assert any(len(values) > 1 for values in spellings.values())
    # pagination boundaries: more reported than served
    assert all(
        page.total_results_reported > len(page.results) for page in projection.responses
    )


def test_ranks_change_with_the_seed_while_the_planted_set_does_not() -> None:
    """A consumer keyed on position rather than content must break here."""

    def by_rank(seed: int) -> tuple[str, ...]:
        projection = generate_search_projection(seed=seed)
        return tuple(
            item.title for page in projection.responses for item in page.results
        )

    def planted(seed: int) -> Counter[SearchMatchTruth]:
        return Counter(
            item.match for item in generate_search_projection(seed=seed).truth.results
        )

    orders = {by_rank(seed) for seed in _SEEDS}
    prevalences = {tuple(sorted(planted(seed).items())) for seed in _SEEDS}

    assert len(orders) == len(_SEEDS)
    assert len(prevalences) == 1


@pytest.mark.parametrize("seed", _SEEDS)
def test_generation_is_byte_identical_for_a_seed(seed: int) -> None:
    assert (
        generate_search_projection(seed=seed).model_dump_json()
        == generate_search_projection(seed=seed).model_dump_json()
    )


def test_truth_is_bound_to_the_public_half_it_describes() -> None:
    """Physical separation without binding lets bundles be mismatched silently."""

    projection = generate_search_projection(seed=1)

    assert projection.truth.public_digest == public_digest(projection.responses)
    assert projection.truth.public_digest != public_digest(
        generate_search_projection(seed=2).responses
    )


def test_a_page_cannot_claim_more_results_than_it_holds() -> None:
    from uuid import UUID

    result = PublicSearchResult(
        id=UUID(int=1), rank=1, url="https://records.example.test/x", title="t"
    )
    with pytest.raises(ValidationError, match="more results than its page size"):
        PublicSearchResponse(
            query="q",
            page=1,
            page_size=1,
            total_results_reported=2,
            results=(result, result.model_copy(update={"rank": 2})),
        )


def test_results_must_be_ranked_and_uniquely_ordered() -> None:
    from uuid import UUID

    first = PublicSearchResult(
        id=UUID(int=1), rank=2, url="https://records.example.test/a", title="a"
    )
    second = first.model_copy(update={"id": UUID(int=2), "rank": 1})

    with pytest.raises(ValidationError, match="ascending rank"):
        PublicSearchResponse(
            query="q",
            page=1,
            page_size=5,
            total_results_reported=2,
            results=(first, second),
        )
    with pytest.raises(ValidationError, match="ranks must be unique"):
        PublicSearchResponse(
            query="q",
            page=1,
            page_size=5,
            total_results_reported=2,
            results=(first, first.model_copy(update={"id": UUID(int=3)})),
        )


def test_urls_must_use_a_reserved_domain() -> None:
    from uuid import UUID

    with pytest.raises(ValidationError, match="reserved example domain"):
        PublicSearchResult(
            id=UUID(int=1), rank=1, url="https://real-site.com/x", title="t"
        )


def test_truth_rows_must_be_coherent() -> None:
    from uuid import UUID

    def row(**overrides: object) -> SearchResultTruth:
        base: dict[str, object] = {
            "result_id": UUID(int=1),
            "subject_persona_id": "persona-0001",
            "actual_persona_id": "persona-0001",
            "match": SearchMatchTruth.TRUE_MATCH,
            "planted_data_classes": (),
            "syndication_group": None,
            "query_id": "query-001",
            "difficulty": 1,
        }
        return SearchResultTruth(**{**base, **overrides})  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="true match must concern the subject"):
        SearchTruthBundle(
            seed=1, public_digest="x", results=(row(actual_persona_id="persona-0002"),)
        )
    with pytest.raises(ValidationError, match="false match must concern someone else"):
        SearchTruthBundle(
            seed=1,
            public_digest="x",
            results=(row(match=SearchMatchTruth.FALSE_MATCH),),
        )
    with pytest.raises(ValidationError, match="unique per result"):
        SearchTruthBundle(seed=1, public_digest="x", results=(row(), row()))


def test_an_explicit_configuration_is_honoured() -> None:
    projection = generate_search_projection(
        seed=1, config=SearchConfig(page_size=3, pages_per_query=1)
    )

    assert all(len(page.results) <= 3 for page in projection.responses)
    assert {page.page for page in projection.responses} == {1}


def test_requesting_more_pages_than_there_are_results_emits_no_empty_page() -> None:
    """A provider does not return an empty page; it stops.

    Configuring more pages than the planted set fills is the pagination boundary,
    and emitting a page with no results would hand consumers a shape real providers
    never produce.
    """

    projection = generate_search_projection(
        seed=1, config=SearchConfig(page_size=5, pages_per_query=5)
    )

    assert all(page.results for page in projection.responses)
    assert max(page.page for page in projection.responses) < 5


def test_a_live_host_cannot_smuggle_a_reserved_domain_into_the_path() -> None:
    """The reserved-domain contract is about the host, not the string.

    `https://real-site.com/path/.example.test` satisfies a substring check and
    points at a real site, which is exactly what the safety rule exists to stop.
    """

    from uuid import UUID

    for url in (
        "https://real-site.com/path/.example.test",
        "https://example.test.evil.com/x",
        "http://records.example.test/x",
    ):
        with pytest.raises(ValidationError, match=r"reserved example domain|https"):
            PublicSearchResult(id=UUID(int=1), rank=1, url=url, title="t")


def test_a_false_match_must_name_someone_else_not_nobody() -> None:
    """`None` is not "someone else" - it is nobody.

    Allowing it produced a false match naming no one, which cannot be scored as a
    collision and quietly shrinks identity-based evaluation.
    """

    from uuid import UUID

    with pytest.raises(ValidationError, match="must concern someone else"):
        SearchTruthBundle(
            seed=1,
            public_digest="x",
            results=(
                SearchResultTruth(
                    result_id=UUID(int=1),
                    subject_persona_id="persona-0001",
                    actual_persona_id=None,
                    match=SearchMatchTruth.FALSE_MATCH,
                    planted_data_classes=(),
                    syndication_group=None,
                    query_id="query-001",
                    difficulty=1,
                ),
            ),
        )
