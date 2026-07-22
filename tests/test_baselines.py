from __future__ import annotations

from uuid import NAMESPACE_DNS, uuid5

from synthworld.baselines import (
    BaselineResult,
    _prf,
    _reciprocal_edges,
    _reference_index,
    run_all_baselines,
)
from synthworld.connection import (
    PublicAssociationKind,
    PublicAssociationRecord,
    PublicConnectionCorpus,
    PublicIdentityAttribute,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    PublicIdentitySourceType,
)

_NAMESPACE = uuid5(NAMESPACE_DNS, "synthworld-baseline-test")

_EXPECTED = {
    "Regex extractor": (
        "Exact-span PII extraction",
        "span F1",
        0.6301,
        "P=1.00 R=0.46 over 150 gold spans; regex catches email, phone, and "
        "national-ID patterns and misses address, date-of-birth, username, "
        "employer, and education spans",
    ),
    "Exact-string entity matcher": (
        "Entity resolution (adversarial pack)",
        "pairwise F1",
        0.5,
        "P=1.00 R=0.33 over 9 same-entity pairs; exact strong-identifier "
        "matching is precise but links only records that already share an "
        "email or username",
    ),
    "Normalised/fuzzy entity matcher": (
        "Entity resolution (adversarial pack)",
        "pairwise F1",
        0.5455,
        "P=0.38 R=1.00 over 9 same-entity pairs; fuzzy name and shared-address "
        "matching recovers more links but over-merges common names and twins "
        "at one address",
    ),
    "Reciprocity relationship heuristic": (
        "Relationship inference",
        "edge F1",
        1.0,
        "P=1.00 R=1.00 over 3 planted edges; 0 false edges — requiring "
        "reciprocal evidence correctly rejects the unilateral association "
        "controls",
    ),
    "Severity-only risk adapter": (
        "Breach-risk calibration",
        "band accuracy",
        0.4,
        "4/10 bands correct, mean absolute score error 21.0; ignoring "
        "data-class weight under-calibrates against the documented formula",
    ),
}


def test_all_baselines_match_frozen_reference_scores() -> None:
    results = run_all_baselines()

    assert [result.name for result in results] == list(_EXPECTED)
    for result in results:
        assert isinstance(result, BaselineResult)
        task, metric, score, detail = _EXPECTED[result.name]
        assert (result.task, result.metric, result.score, result.detail) == (
            task,
            metric,
            score,
            detail,
        )


def test_prf_handles_empty_prediction_truth_and_denominator() -> None:
    empty: set[int] = set()
    assert _prf(empty, empty) == (0.0, 0.0, 0.0)
    assert _prf(empty, {1}) == (0.0, 0.0, 0.0)
    assert _prf({1}, empty) == (0.0, 0.0, 0.0)


def test_reference_index_skips_records_missing_a_reference() -> None:
    record = PublicIdentityRecord(
        id=_NAMESPACE,
        source_type=PublicIdentitySourceType.DIRECTORY,
        source_url="https://records.example.test/identity/1",
        display_name="Example Person",
        confidence=1.0,
        attributes=(
            PublicIdentityAttribute(
                kind=PublicIdentityAttributeKind.FULL_ADDRESS,
                value="1|Example Avenue|Testville|00000|ZZ",
                confidence=1.0,
            ),
        ),
    )

    index = _reference_index((record,))

    assert index == {"1|Example Avenue|Testville|00000|ZZ": record.id}


def test_reciprocal_edges_ignores_unmapped_references() -> None:
    forward = PublicAssociationRecord(
        id=uuid5(_NAMESPACE, "forward"),
        kind=PublicAssociationKind.PROFILE_LINK,
        source_url="https://associations.example.test/records/1",
        source_reference="unmapped-a",
        target_reference="unmapped-b",
        confidence=1.0,
    )
    reverse = PublicAssociationRecord(
        id=uuid5(_NAMESPACE, "reverse"),
        kind=PublicAssociationKind.PROFILE_LINK,
        source_url="https://associations.example.test/records/2",
        source_reference="unmapped-b",
        target_reference="unmapped-a",
        confidence=1.0,
    )
    corpus = PublicConnectionCorpus(
        seed=1,
        identity_records=(),
        association_records=(forward, reverse),
    )

    assert _reciprocal_edges(corpus, {}) == set()
