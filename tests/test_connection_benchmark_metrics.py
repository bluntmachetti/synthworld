"""Truth-directed metrics for the raw public connection benchmarks."""

from __future__ import annotations

import hashlib
from importlib.resources import files

import pytest
from pydantic import ValidationError

from synthworld.connection import (
    AdversarialPackKind,
    ConnectionAnswerKey,
    ConnectionBenchmark,
    PublicAssociationKind,
    PublicConnectionCorpus,
    PublicIdentityAttributeKind,
    PublicRelationshipTruth,
    PublicTruthRelationshipKind,
    UnilateralAssociationControl,
)
from synthworld.connection_generator import (
    generate_adversarial_connection_benchmark,
    generate_relationship_connection_benchmark,
)
from synthworld.connection_metrics import (
    ConnectionBenchmarkMetrics,
    evaluate_connection_benchmarks,
)
from synthworld.connection_serialization import (
    connection_benchmark_to_json,
    load_golden_connection_benchmark,
    load_golden_public_connection_corpus,
    public_connection_corpus_to_json,
)
from synthworld.generator import generate_world

_SEED = 20_260_719


@pytest.mark.parametrize(
    (
        "persona_count",
        "identity_count",
        "property_count",
        "profile_count",
        "neighbors",
        "social",
    ),
    [
        (10, 10, 5, 3, 2, 1),
        (100, 100, 41, 39, 20, 19),
    ],
)
def test_connection_benchmark_metrics_freeze_honest_denominators(
    persona_count: int,
    identity_count: int,
    property_count: int,
    profile_count: int,
    neighbors: int,
    social: int,
) -> None:
    adversarial = generate_adversarial_connection_benchmark(seed=_SEED)
    relationships = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=persona_count,
    )

    metrics = evaluate_connection_benchmarks(adversarial, relationships)

    assert isinstance(metrics, ConnectionBenchmarkMetrics)
    assert metrics.adversarial_record_count == 18
    assert metrics.truth_entity_count == 10
    assert metrics.possible_record_pair_count == 153
    assert metrics.same_entity_pair_count == 9
    assert metrics.different_entity_pair_count == 144
    assert {
        item.pack: (
            item.record_count,
            item.entity_count,
            item.same_entity_pair_count,
            item.different_entity_pair_count,
        )
        for item in metrics.packs
    } == {
        AdversarialPackKind.COMMON_NAME: (4, 2, 2, 4),
        AdversarialPackKind.UNICODE_DIACRITICS: (3, 2, 1, 2),
        AdversarialPackKind.TWINS_SHARED_ADDRESS: (4, 2, 2, 4),
        AdversarialPackKind.MAIDEN_NAME: (3, 2, 1, 2),
        AdversarialPackKind.MISSPELLING_ALIAS: (4, 2, 3, 3),
    }
    assert metrics.public_identity_record_count == identity_count
    assert metrics.property_adjacency_record_count == property_count
    assert metrics.profile_link_record_count == profile_count
    assert metrics.neighbor_relationship_count == neighbors
    assert metrics.social_relationship_count == social
    assert metrics.unilateral_property_control_count == 1
    assert metrics.unilateral_profile_control_count == 1
    assert metrics.membership_integrity == 1.0
    assert metrics.pack_integrity == 1.0
    assert metrics.neighbor_reciprocal_evidence_coverage == 1.0
    assert metrics.social_reciprocal_evidence_coverage == 1.0
    assert metrics.unilateral_control_integrity == 1.0
    assert metrics.public_reference_integrity == 1.0
    assert metrics.safely_fake_record_rate == 1.0
    assert metrics.deterministic_replay_integrity == 1.0
    assert metrics.manifest_integrity == 1.0
    assert metrics.answer_key_separation_integrity == 1.0


def test_connection_metric_mutations_move_in_the_required_direction() -> None:
    adversarial = generate_adversarial_connection_benchmark(seed=_SEED)
    relationships = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )
    baseline = evaluate_connection_benchmarks(adversarial, relationships)
    memberships = adversarial.answer_key.record_memberships

    missing_membership = _answer_key_copy(
        adversarial,
        record_memberships=memberships[:-1],
    )
    duplicate_key = ConnectionAnswerKey.model_construct(
        record_memberships=(*memberships, memberships[0]),
        adversarial_cases=adversarial.answer_key.adversarial_cases,
        relationships=adversarial.answer_key.relationships,
        unilateral_controls=adversarial.answer_key.unilateral_controls,
    )
    duplicate_membership = adversarial.model_copy(update={"answer_key": duplicate_key})
    changed_case = adversarial.answer_key.adversarial_cases[0].model_copy(
        update={
            "record_ids": adversarial.answer_key.adversarial_cases[0].record_ids[:-1]
        }
    )
    changed_pack = _answer_key_copy(
        adversarial,
        adversarial_cases=(changed_case, *adversarial.answer_key.adversarial_cases[1:]),
    )
    poisoned_case = adversarial.answer_key.adversarial_cases[0].model_copy(
        update={"entity_ids": ("poison-a", "poison-b")}
    )
    poisoned_entities = _answer_key_copy(
        adversarial,
        adversarial_cases=(
            poisoned_case,
            *adversarial.answer_key.adversarial_cases[1:],
        ),
    )

    assert (
        evaluate_connection_benchmarks(
            missing_membership, relationships
        ).membership_integrity
        < baseline.membership_integrity
    )
    assert (
        evaluate_connection_benchmarks(
            duplicate_membership, relationships
        ).membership_integrity
        < baseline.membership_integrity
    )
    assert (
        evaluate_connection_benchmarks(changed_pack, relationships).pack_integrity
        < baseline.pack_integrity
    )
    assert (
        evaluate_connection_benchmarks(poisoned_entities, relationships).pack_integrity
        < baseline.pack_integrity
    )


def test_relationship_truth_completeness_penalizes_missing_and_extra_truth() -> None:
    adversarial = generate_adversarial_connection_benchmark(seed=_SEED)
    relationships = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )
    baseline = evaluate_connection_benchmarks(adversarial, relationships)
    without_neighbors = _answer_key_copy(
        relationships,
        relationships=tuple(
            item
            for item in relationships.answer_key.relationships
            if item.kind is not PublicTruthRelationshipKind.NEIGHBOR
        ),
    )
    neighbor = next(
        item
        for item in relationships.answer_key.relationships
        if item.kind is PublicTruthRelationshipKind.NEIGHBOR
    )
    extra_social = PublicRelationshipTruth(
        source_record_id=neighbor.source_record_id,
        target_record_id=neighbor.target_record_id,
        kind=PublicTruthRelationshipKind.SOCIAL,
        reciprocal_association_ids=neighbor.reciprocal_association_ids,
    )
    with_extra_social = _answer_key_copy(
        relationships,
        relationships=(*relationships.answer_key.relationships, extra_social),
    )

    missing_score = evaluate_connection_benchmarks(adversarial, without_neighbors)
    extra_score = evaluate_connection_benchmarks(adversarial, with_extra_social)

    assert missing_score.neighbor_relationship_count == 0
    assert missing_score.neighbor_reciprocal_evidence_coverage == 0.0
    assert (
        extra_score.social_reciprocal_evidence_coverage
        < baseline.social_reciprocal_evidence_coverage
    )


def test_relationship_metrics_fail_closed_for_unusable_or_incomplete_membership() -> (
    None
):
    adversarial = generate_adversarial_connection_benchmark(seed=_SEED)
    relationships = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )
    no_membership = _answer_key_copy(relationships, record_memberships=())
    two_memberships = _answer_key_copy(
        relationships,
        record_memberships=relationships.answer_key.record_memberships[:2],
    )
    persona_one_membership = next(
        item
        for item in relationships.answer_key.record_memberships
        if item.entity_id == "persona-0001"
    )
    public_without_control_endpoint = relationships.public.model_copy(
        update={
            "identity_records": tuple(
                item
                for item in relationships.public.identity_records
                if item.id != persona_one_membership.record_id
            )
        }
    )
    missing_control_endpoint = relationships.model_copy(
        update={"public": public_without_control_endpoint}
    )

    no_membership_score = evaluate_connection_benchmarks(adversarial, no_membership)
    two_membership_score = evaluate_connection_benchmarks(
        adversarial,
        two_memberships,
    )
    missing_endpoint_score = evaluate_connection_benchmarks(
        adversarial,
        missing_control_endpoint,
    )

    assert no_membership_score.neighbor_reciprocal_evidence_coverage == 0.0
    assert no_membership_score.social_reciprocal_evidence_coverage == 0.0
    assert no_membership_score.unilateral_control_integrity == 0.0
    assert two_membership_score.unilateral_control_integrity == 0.0
    assert missing_endpoint_score.unilateral_control_integrity == 0.0


def test_relationship_control_mutations_move_in_the_required_direction() -> None:
    adversarial = generate_adversarial_connection_benchmark(seed=_SEED)
    relationships = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )
    baseline = evaluate_connection_benchmarks(adversarial, relationships)
    first_truth = relationships.answer_key.relationships[0]
    missing_association_id = first_truth.reciprocal_association_ids[0]
    public_without_reciprocal = relationships.public.model_copy(
        update={
            "association_records": tuple(
                item
                for item in relationships.public.association_records
                if item.id != missing_association_id
            )
        }
    )
    missing_reciprocal = relationships.model_copy(
        update={"public": public_without_reciprocal}
    )
    public_without_truth_endpoint = relationships.public.model_copy(
        update={
            "identity_records": tuple(
                item
                for item in relationships.public.identity_records
                if item.id != first_truth.source_record_id
            )
        }
    )
    missing_truth_endpoint = relationships.model_copy(
        update={"public": public_without_truth_endpoint}
    )
    mislabeled_control = _answer_key_copy(
        relationships,
        unilateral_controls=(
            UnilateralAssociationControl(
                association_id=first_truth.reciprocal_association_ids[0],
                kind=PublicAssociationKind.PROPERTY_ADJACENCY,
            ),
            relationships.answer_key.unilateral_controls[1],
        ),
    )
    first_association = relationships.public.association_records[0]
    broken_association = first_association.model_copy(
        update={"source_reference": "missing-reference@example.test"}
    )
    broken_public = relationships.public.model_copy(
        update={
            "association_records": (
                broken_association,
                *relationships.public.association_records[1:],
            )
        }
    )
    broken_reference = relationships.model_copy(update={"public": broken_public})
    first_control_id = relationships.answer_key.unilateral_controls[0].association_id
    public_without_control = relationships.public.model_copy(
        update={
            "association_records": tuple(
                item
                for item in relationships.public.association_records
                if item.id != first_control_id
            )
        }
    )
    missing_control = relationships.model_copy(
        update={"public": public_without_control}
    )
    world = generate_world(seed=_SEED, persona_count=10)
    classmate = next(
        item for item in world.relationships if item.kind.value == "classmate"
    )
    record_id_by_persona = {
        item.entity_id: item.record_id
        for item in relationships.answer_key.record_memberships
    }
    records_by_id = {item.id: item for item in relationships.public.identity_records}

    def address_for(persona_id: str) -> str:
        record = records_by_id[record_id_by_persona[persona_id]]
        return next(
            item.value
            for item in record.attributes
            if item.kind is PublicIdentityAttributeKind.FULL_ADDRESS
        )

    property_control = next(
        item
        for item in relationships.answer_key.unilateral_controls
        if item.kind is PublicAssociationKind.PROPERTY_ADJACENCY
    )
    control_on_edge_records = tuple(
        item.model_copy(
            update={
                "source_reference": address_for(classmate.source_person_id),
                "target_reference": address_for(classmate.target_person_id),
            }
        )
        if item.id == property_control.association_id
        else item
        for item in relationships.public.association_records
    )
    control_on_edge = relationships.model_copy(
        update={
            "public": relationships.public.model_copy(
                update={"association_records": control_on_edge_records}
            )
        }
    )

    changed_coverage = evaluate_connection_benchmarks(adversarial, missing_reciprocal)
    assert (
        changed_coverage.neighbor_reciprocal_evidence_coverage
        < baseline.neighbor_reciprocal_evidence_coverage
        or changed_coverage.social_reciprocal_evidence_coverage
        < baseline.social_reciprocal_evidence_coverage
    )
    endpoint_coverage = evaluate_connection_benchmarks(
        adversarial, missing_truth_endpoint
    )
    assert (
        endpoint_coverage.neighbor_reciprocal_evidence_coverage
        < baseline.neighbor_reciprocal_evidence_coverage
        or endpoint_coverage.social_reciprocal_evidence_coverage
        < baseline.social_reciprocal_evidence_coverage
    )
    assert (
        evaluate_connection_benchmarks(
            adversarial, mislabeled_control
        ).unilateral_control_integrity
        < baseline.unilateral_control_integrity
    )
    assert (
        evaluate_connection_benchmarks(
            adversarial, missing_control
        ).unilateral_control_integrity
        < baseline.unilateral_control_integrity
    )
    assert (
        evaluate_connection_benchmarks(
            adversarial, broken_reference
        ).public_reference_integrity
        < baseline.public_reference_integrity
    )
    assert (
        evaluate_connection_benchmarks(
            adversarial, control_on_edge
        ).unilateral_control_integrity
        < baseline.unilateral_control_integrity
    )


@pytest.mark.parametrize(
    ("kind", "unsafe_value"),
    [
        (PublicIdentityAttributeKind.EMAIL, "victim@gmail.com@example.test"),
        (PublicIdentityAttributeKind.FAMILY_NAME, "Family123"),
        (PublicIdentityAttributeKind.USERNAME, "real_handle"),
        (PublicIdentityAttributeKind.PHONE, "+1-212-555-9999"),
        (
            PublicIdentityAttributeKind.FULL_ADDRESS,
            "101|Real Example Avenue|Testville|00000|ZZ",
        ),
        (PublicIdentityAttributeKind.DATE_OF_BIRTH, "not-a-date"),
        (PublicIdentityAttributeKind.EMPLOYER, "Real Corporation"),
        (PublicIdentityAttributeKind.SCHOOL_YEAR, "Real University|2020"),
        (
            PublicIdentityAttributeKind.SOCIAL_PROFILE,
            "https://social.example.invalid/profile",
        ),
    ],
)
def test_safety_scores_both_corpora_and_strict_typed_values(
    kind: PublicIdentityAttributeKind,
    unsafe_value: str,
) -> None:
    adversarial = generate_adversarial_connection_benchmark(seed=_SEED)
    relationships = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )
    target = (
        adversarial
        if any(
            attribute.kind is kind
            for record in adversarial.public.identity_records
            for attribute in record.attributes
        )
        else relationships
    )
    records = list(target.public.identity_records)
    record_index, attribute_index = next(
        (record_index, attribute_index)
        for record_index, record in enumerate(records)
        for attribute_index, attribute in enumerate(record.attributes)
        if attribute.kind is kind
    )
    attributes = list(records[record_index].attributes)
    attributes[attribute_index] = attributes[attribute_index].model_copy(
        update={"value": unsafe_value}
    )
    records[record_index] = records[record_index].model_copy(
        update={"attributes": tuple(attributes)}
    )
    mutated = target.model_copy(
        update={
            "public": target.public.model_copy(
                update={"identity_records": tuple(records)}
            )
        }
    )
    mutated_adversarial = mutated if target is adversarial else adversarial
    mutated_relationships = mutated if target is relationships else relationships

    assert (
        evaluate_connection_benchmarks(
            mutated_adversarial,
            mutated_relationships,
        ).safely_fake_record_rate
        < 1.0
    )


@pytest.mark.parametrize(
    ("kind", "unsafe_reference"),
    [
        (
            PublicAssociationKind.PROPERTY_ADJACENCY,
            "101|Real Example Avenue|Testville|00000|ZZ",
        ),
        (
            PublicAssociationKind.PROFILE_LINK,
            "https://social.example.invalid/profile",
        ),
    ],
)
def test_safety_validates_typed_association_references(
    kind: PublicAssociationKind,
    unsafe_reference: str,
) -> None:
    adversarial = generate_adversarial_connection_benchmark(seed=_SEED)
    relationships = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )
    associations = tuple(
        item.model_copy(update={"target_reference": unsafe_reference})
        if item.kind is kind
        else item
        for item in relationships.public.association_records
    )
    mutated = relationships.model_copy(
        update={
            "public": relationships.public.model_copy(
                update={"association_records": associations}
            )
        }
    )

    assert (
        evaluate_connection_benchmarks(
            adversarial,
            mutated,
        ).safely_fake_record_rate
        < 1.0
    )


@pytest.mark.parametrize(
    "leaked_value",
    [
        "persona-0001 entity-0001 relationship-0001",
        "common_name",
    ],
)
def test_allowed_public_fields_cannot_hide_oracle_content(
    leaked_value: str,
) -> None:
    adversarial = generate_adversarial_connection_benchmark(seed=_SEED)
    relationships = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )
    records = list(relationships.public.identity_records)
    records[0] = records[0].model_copy(update={"display_name": leaked_value})
    leaked = relationships.model_copy(
        update={
            "public": relationships.public.model_copy(
                update={"identity_records": tuple(records)}
            )
        }
    )

    assert (
        evaluate_connection_benchmarks(
            adversarial,
            leaked,
        ).answer_key_separation_integrity
        == 0.0
    )


def test_public_connection_schema_rejects_oracle_leakage_and_sorts_inputs() -> None:
    benchmark = generate_adversarial_connection_benchmark(seed=_SEED)
    public_payload = benchmark.public.model_dump(mode="json")
    public_payload["identity_records"][0]["expected_cluster"] = "oracle"

    with pytest.raises(ValidationError):
        PublicConnectionCorpus.model_validate(public_payload)

    reversed_public = PublicConnectionCorpus(
        seed=benchmark.public.seed,
        identity_records=tuple(reversed(benchmark.public.identity_records)),
        association_records=tuple(reversed(benchmark.public.association_records)),
    )
    reordered = benchmark.model_copy(update={"public": reversed_public})

    assert connection_benchmark_to_json(reordered) == connection_benchmark_to_json(
        benchmark
    )


def test_frozen_connection_benchmark_and_manifest_match_generation() -> None:
    generated = connection_benchmark_to_json(
        generate_adversarial_connection_benchmark(seed=_SEED)
    )
    benchmark_directory = files("synthworld.benchmarks")
    benchmark = benchmark_directory.joinpath("connection-golden-v1.json")
    manifest = benchmark_directory.joinpath("CONNECTION_SHA256SUMS").read_text(
        encoding="utf-8"
    )
    expected_hash, filename = manifest.strip().split(maxsplit=1)

    assert filename == "connection-golden-v1.json"
    assert benchmark.read_text(encoding="utf-8") == generated
    assert connection_benchmark_to_json(load_golden_connection_benchmark()) == generated
    assert hashlib.sha256(benchmark.read_bytes()).hexdigest() == expected_hash


def test_frozen_public_connection_corpus_is_physically_separate_and_checksummed() -> (
    None
):
    benchmark_directory = files("synthworld.benchmarks")
    public_artifact = benchmark_directory.joinpath("connection-public-golden-v1.json")
    manifest = benchmark_directory.joinpath("CONNECTION_PUBLIC_SHA256SUMS").read_text(
        encoding="utf-8"
    )
    expected_hash, filename = manifest.strip().split(maxsplit=1)
    serialized = public_artifact.read_text(encoding="utf-8")

    assert filename == "connection-public-golden-v1.json"
    assert "answer_key" not in serialized
    assert public_connection_corpus_to_json(
        load_golden_public_connection_corpus()
    ) == public_connection_corpus_to_json(load_golden_connection_benchmark().public)
    assert hashlib.sha256(public_artifact.read_bytes()).hexdigest() == expected_hash


def _answer_key_copy(
    benchmark: ConnectionBenchmark,
    **updates: object,
) -> ConnectionBenchmark:
    answer_key = benchmark.answer_key.model_copy(update=updates)
    return benchmark.model_copy(update={"answer_key": answer_key})
