from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from synthworld import (
    AdversarialCase,
    AdversarialPackKind,
    ConnectionAnswerKey,
    ConnectionBenchmark,
    PublicAssociationKind,
    PublicAssociationRecord,
    PublicConnectionCorpus,
    PublicIdentityAttribute,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    PublicRelationshipTruth,
    PublicTruthRelationshipKind,
    RecordMembership,
    UnilateralAssociationControl,
    connection_benchmark_to_json,
    generate_adversarial_connection_benchmark,
    generate_public_relationship_connection_corpus,
    generate_relationship_connection_benchmark,
    generate_world,
    public_connection_corpus_to_json,
)

_SEED = 20_260_719
_PERSONA_ID = re.compile(r"\bpersona-\d{4}\b")


def test_public_relationship_helper_projects_only_public_observations() -> None:
    benchmark = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )

    assert (
        generate_public_relationship_connection_corpus(
            seed=_SEED,
            persona_count=10,
        )
        == benchmark.public
    )


@pytest.mark.parametrize(
    ("pack", "records", "entities", "same_pairs", "different_pairs"),
    [
        (AdversarialPackKind.COMMON_NAME, 4, 2, 2, 4),
        (AdversarialPackKind.UNICODE_DIACRITICS, 3, 2, 1, 2),
        (AdversarialPackKind.TWINS_SHARED_ADDRESS, 4, 2, 2, 4),
        (AdversarialPackKind.MAIDEN_NAME, 3, 2, 1, 2),
        (AdversarialPackKind.MISSPELLING_ALIAS, 4, 2, 3, 3),
    ],
)
def test_adversarial_packs_have_exact_independent_pair_denominators(
    pack: AdversarialPackKind,
    records: int,
    entities: int,
    same_pairs: int,
    different_pairs: int,
) -> None:
    benchmark = generate_adversarial_connection_benchmark(seed=_SEED)
    case = next(
        item for item in benchmark.answer_key.adversarial_cases if item.pack is pack
    )
    membership = {
        item.record_id: item.entity_id
        for item in benchmark.answer_key.record_memberships
    }
    pairs = tuple(combinations(case.record_ids, 2))

    assert len(case.record_ids) == records
    assert len(case.entity_ids) == entities
    assert (
        sum(membership[left] == membership[right] for left, right in pairs)
        == same_pairs
    )
    assert (
        sum(membership[left] != membership[right] for left, right in pairs)
        == different_pairs
    )


def test_adversarial_corpus_has_exact_global_truth_and_case_semantics() -> None:
    benchmark = generate_adversarial_connection_benchmark(seed=_SEED)
    membership = {
        item.record_id: item.entity_id
        for item in benchmark.answer_key.record_memberships
    }
    records = benchmark.public.identity_records
    all_pairs = tuple(combinations(records, 2))
    names_by_pack = {
        case.pack: {
            record.display_name for record in records if record.id in case.record_ids
        }
        for case in benchmark.answer_key.adversarial_cases
    }

    assert len(records) == 18
    assert len(membership) == 18
    assert len(set(membership.values())) == 10
    assert len(all_pairs) == 153
    assert (
        sum(membership[left.id] == membership[right.id] for left, right in all_pairs)
        == 9
    )
    assert (
        sum(membership[left.id] != membership[right.id] for left, right in all_pairs)
        == 144
    )
    assert names_by_pack[AdversarialPackKind.COMMON_NAME] == {"Jordan Smith"}
    assert names_by_pack[AdversarialPackKind.UNICODE_DIACRITICS] == {
        "Zoë García",
        "Zoe Garcia",
    }
    assert names_by_pack[AdversarialPackKind.TWINS_SHARED_ADDRESS] == {
        "Lina Mercer",
        "Mina Mercer",
    }
    assert names_by_pack[AdversarialPackKind.MAIDEN_NAME] == {
        "Amina Mensah",
        "Amina Okafor",
    }
    assert names_by_pack[AdversarialPackKind.MISSPELLING_ALIAS] == {
        "Katherine O'Connor",
        "Katherin Oconor",
        "Kathryn O'Connor",
        "Katie Oconnor",
    }

    twin_case = next(
        item
        for item in benchmark.answer_key.adversarial_cases
        if item.pack is AdversarialPackKind.TWINS_SHARED_ADDRESS
    )
    twin_records = [item for item in records if item.id in twin_case.record_ids]
    twin_addresses = {
        attribute.value
        for record in twin_records
        for attribute in record.attributes
        if attribute.kind is PublicIdentityAttributeKind.FULL_ADDRESS
    }
    twin_birth_dates = {
        attribute.value
        for record in twin_records
        for attribute in record.attributes
        if attribute.kind is PublicIdentityAttributeKind.DATE_OF_BIRTH
    }
    assert twin_addresses == {"505|Adversarial Example Avenue|Testville|00000|ZZ"}
    assert twin_birth_dates == {"2000-01-01"}


@pytest.mark.parametrize(
    ("persona_count", "identity_count", "property_count", "profile_count"),
    [(10, 10, 5, 3), (100, 100, 41, 39)],
)
def test_relationship_corpus_has_exact_reciprocal_evidence_and_controls(
    persona_count: int,
    identity_count: int,
    property_count: int,
    profile_count: int,
) -> None:
    benchmark = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=persona_count,
    )
    associations = {item.id: item for item in benchmark.public.association_records}
    truth_counts = Counter(item.kind for item in benchmark.answer_key.relationships)
    public_counts = Counter(item.kind for item in associations.values())

    assert len(benchmark.public.identity_records) == identity_count
    assert public_counts == {
        PublicAssociationKind.PROPERTY_ADJACENCY: property_count,
        PublicAssociationKind.PROFILE_LINK: profile_count,
    }
    assert truth_counts == {
        PublicTruthRelationshipKind.NEIGHBOR: (persona_count - 1 + 4) // 5,
        PublicTruthRelationshipKind.SOCIAL: (persona_count - 1) // 5,
    }
    assert Counter(item.kind for item in benchmark.answer_key.unilateral_controls) == {
        PublicAssociationKind.PROPERTY_ADJACENCY: 1,
        PublicAssociationKind.PROFILE_LINK: 1,
    }

    for truth in benchmark.answer_key.relationships:
        first, second = (
            associations[item] for item in truth.reciprocal_association_ids
        )
        assert first.kind.value == second.kind.value
        assert first.source_reference == second.target_reference
        assert first.target_reference == second.source_reference
        assert first.id != second.id
        assert first.source_url != second.source_url

    reciprocal_pairs = {
        (item.kind, item.source_reference, item.target_reference)
        for item in associations.values()
    }
    for control in benchmark.answer_key.unilateral_controls:
        record = associations[control.association_id]
        assert (
            record.kind,
            record.target_reference,
            record.source_reference,
        ) not in reciprocal_pairs


@pytest.mark.parametrize("persona_count", [10, 100])
def test_relationship_identity_records_expose_exact_family_name_observations(
    persona_count: int,
) -> None:
    world = generate_world(seed=_SEED, persona_count=persona_count)
    benchmark = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=persona_count,
    )
    family_by_email = {
        persona.emails[0].value: persona.family_name for persona in world.personas
    }

    for record in benchmark.public.identity_records:
        values = defaultdict(list)
        for attribute in record.attributes:
            values[attribute.kind].append(attribute.value)
        email = values[PublicIdentityAttributeKind.EMAIL][0]

        assert values[PublicIdentityAttributeKind.FAMILY_NAME] == [
            family_by_email[email]
        ]
        assert len(record.attributes) == 9


def test_public_references_are_resolvable_safe_and_oracle_free() -> None:
    for benchmark in (
        generate_adversarial_connection_benchmark(seed=_SEED),
        generate_relationship_connection_benchmark(seed=_SEED, persona_count=100),
    ):
        public_json = public_connection_corpus_to_json(benchmark.public)
        values = {
            attribute.value
            for record in benchmark.public.identity_records
            for attribute in record.attributes
        }

        assert _PERSONA_ID.search(public_json) is None
        assert "answer_key" not in public_json
        assert "relationship" not in public_json
        assert "adversarial" not in public_json
        _assert_public_schema(benchmark.public.model_dump(mode="json"))
        for record in benchmark.public.identity_records:
            assert _reserved(record.source_url)
            for attribute in record.attributes:
                if attribute.kind is PublicIdentityAttributeKind.EMAIL:
                    assert attribute.value.endswith("@example.test")
                elif attribute.kind is PublicIdentityAttributeKind.PHONE:
                    assert re.fullmatch(r"\+1-\d{3}-555-01\d{2}", attribute.value)
                elif attribute.kind is PublicIdentityAttributeKind.FULL_ADDRESS:
                    assert "Example Avenue|Testville|00000|ZZ" in attribute.value
                elif attribute.kind is PublicIdentityAttributeKind.SOCIAL_PROFILE:
                    assert _reserved(attribute.value)
        for association in benchmark.public.association_records:
            assert _reserved(association.source_url)
            assert association.source_reference in values
            assert association.target_reference in values


def test_generation_is_deterministic_seeded_canonical_and_truth_separated() -> None:
    first = generate_adversarial_connection_benchmark(seed=_SEED)
    replay = generate_adversarial_connection_benchmark(seed=_SEED)
    changed = generate_adversarial_connection_benchmark(seed=_SEED + 1)
    reversed_public = PublicConnectionCorpus(
        seed=first.public.seed,
        identity_records=tuple(reversed(first.public.identity_records)),
        association_records=tuple(reversed(first.public.association_records)),
    )
    poisoned = first.model_copy(
        update={
            "answer_key": first.answer_key.model_copy(
                update={"record_memberships": (), "adversarial_cases": ()}
            )
        }
    )

    assert connection_benchmark_to_json(first) == connection_benchmark_to_json(replay)
    assert connection_benchmark_to_json(first) != connection_benchmark_to_json(changed)
    assert public_connection_corpus_to_json(
        first.public
    ) == public_connection_corpus_to_json(reversed_public)
    assert public_connection_corpus_to_json(
        first.public
    ) == public_connection_corpus_to_json(poisoned.public)


def test_connection_public_models_reject_unsafe_or_ambiguous_records() -> None:
    benchmark = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )
    identity = benchmark.public.identity_records[0]
    association = benchmark.public.association_records[0]
    membership = benchmark.answer_key.record_memberships[0]
    case = generate_adversarial_connection_benchmark(
        seed=_SEED
    ).answer_key.adversarial_cases[0]
    relationship = benchmark.answer_key.relationships[0]
    control = benchmark.answer_key.unilateral_controls[0]

    with pytest.raises(ValidationError, match="nonblank"):
        PublicIdentityAttribute(
            kind=PublicIdentityAttributeKind.EMAIL,
            value=" ",
            confidence=1.0,
        )
    with pytest.raises(ValidationError, match="reserved HTTPS"):
        identity.model_copy(
            update={"source_url": "http://records.example.test"}
        ).model_dump()
        PublicIdentityRecord.model_validate(
            {**identity.model_dump(), "source_url": "http://records.example.test"}
        )
    with pytest.raises(ValidationError, match="reserved HTTPS"):
        PublicIdentityRecord.model_validate(
            {**identity.model_dump(), "source_url": "https://example.invalid"}
        )
    exact_reserved = PublicIdentityRecord.model_validate(
        {**identity.model_dump(), "source_url": "https://example.test/record"}
    )
    assert exact_reserved.source_url.startswith("https://example.test")
    with pytest.raises(ValidationError, match="display names"):
        PublicIdentityRecord.model_validate(
            {**identity.model_dump(), "display_name": " "}
        )
    with pytest.raises(ValidationError, match="attributes must be unique"):
        PublicIdentityRecord.model_validate(
            {
                **identity.model_dump(),
                "attributes": (*identity.attributes, identity.attributes[0]),
            }
        )
    with pytest.raises(ValidationError, match="reserved HTTPS"):
        PublicAssociationRecord.model_validate(
            {**association.model_dump(), "source_url": "https://example.invalid"}
        )
    with pytest.raises(ValidationError, match="references must be nonblank"):
        PublicAssociationRecord.model_validate(
            {**association.model_dump(), "source_reference": " "}
        )
    with pytest.raises(ValidationError, match="distinct references"):
        PublicAssociationRecord.model_validate(
            {
                **association.model_dump(),
                "target_reference": association.source_reference,
            }
        )
    with pytest.raises(ValidationError, match="identity records require unique"):
        PublicConnectionCorpus(
            seed=_SEED,
            identity_records=(identity, identity),
            association_records=(),
        )
    with pytest.raises(ValidationError, match="association records require unique"):
        PublicConnectionCorpus(
            seed=_SEED,
            identity_records=(identity,),
            association_records=(association, association),
        )
    with pytest.raises(ValidationError, match="entity ID"):
        RecordMembership(record_id=membership.record_id, entity_id=" ")
    with pytest.raises(ValidationError, match="case records require unique"):
        AdversarialCase(
            pack=case.pack,
            record_ids=(case.record_ids[0], case.record_ids[0]),
            entity_ids=case.entity_ids,
        )
    with pytest.raises(ValidationError, match="nonblank and unique"):
        AdversarialCase(
            pack=case.pack,
            record_ids=case.record_ids,
            entity_ids=(case.entity_ids[0], case.entity_ids[0]),
        )
    with pytest.raises(ValidationError, match="two association records"):
        PublicRelationshipTruth(
            source_record_id=relationship.source_record_id,
            target_record_id=relationship.target_record_id,
            kind=relationship.kind,
            reciprocal_association_ids=(
                relationship.reciprocal_association_ids[0],
                relationship.reciprocal_association_ids[0],
            ),
        )
    with pytest.raises(ValidationError, match="canonical order"):
        PublicRelationshipTruth(
            source_record_id=relationship.target_record_id,
            target_record_id=relationship.source_record_id,
            kind=relationship.kind,
            reciprocal_association_ids=relationship.reciprocal_association_ids,
        )
    with pytest.raises(ValidationError, match="distinct identity"):
        PublicRelationshipTruth(
            source_record_id=relationship.source_record_id,
            target_record_id=relationship.source_record_id,
            kind=relationship.kind,
            reciprocal_association_ids=relationship.reciprocal_association_ids,
        )
    _assert_answer_key_duplicate_guards(
        benchmark.answer_key,
        membership,
        case,
        relationship,
        control,
    )
    with pytest.raises(ValidationError, match="seeds must match"):
        ConnectionBenchmark(
            seed=_SEED + 1,
            public=benchmark.public,
            answer_key=benchmark.answer_key,
        )
    with pytest.raises(ValueError, match="at least 3"):
        generate_relationship_connection_benchmark(seed=_SEED, persona_count=2)


def _assert_answer_key_duplicate_guards(
    answer_key: ConnectionAnswerKey,
    membership: RecordMembership,
    case: AdversarialCase,
    relationship: PublicRelationshipTruth,
    control: UnilateralAssociationControl,
) -> None:
    with pytest.raises(ValidationError, match="record memberships require unique"):
        ConnectionAnswerKey(
            record_memberships=(membership, membership),
            adversarial_cases=(),
            relationships=(),
            unilateral_controls=(),
        )
    with pytest.raises(ValidationError, match="unique pack labels"):
        ConnectionAnswerKey(
            record_memberships=(),
            adversarial_cases=(case, case),
            relationships=(),
            unilateral_controls=(),
        )
    with pytest.raises(ValidationError, match="answer keys must be unique"):
        ConnectionAnswerKey(
            record_memberships=(),
            adversarial_cases=(),
            relationships=(relationship, relationship),
            unilateral_controls=(),
        )
    with pytest.raises(ValidationError, match="unilateral controls require unique"):
        ConnectionAnswerKey(
            record_memberships=(),
            adversarial_cases=(),
            relationships=(),
            unilateral_controls=(control, control),
        )


def _assert_public_schema(value: object) -> None:
    assert isinstance(value, dict)
    assert set(value) == {
        "synthetic",
        "schema_version",
        "seed",
        "identity_records",
        "association_records",
    }
    assert value["synthetic"] is True
    for record in value["identity_records"]:
        assert set(record) == {
            "synthetic",
            "id",
            "source_type",
            "source_url",
            "display_name",
            "confidence",
            "attributes",
        }
        assert record["synthetic"] is True
        for attribute in record["attributes"]:
            assert set(attribute) == {"synthetic", "kind", "value", "confidence"}
            assert attribute["synthetic"] is True
    for association in value["association_records"]:
        assert set(association) == {
            "synthetic",
            "id",
            "kind",
            "source_url",
            "source_reference",
            "target_reference",
            "confidence",
        }
        assert association["synthetic"] is True


def _reserved(value: str) -> bool:
    host = urlparse(value).hostname or ""
    return host == "example.test" or host.endswith(".example.test")


def test_public_json_is_valid_canonical_json() -> None:
    benchmark = generate_relationship_connection_benchmark(
        seed=_SEED,
        persona_count=10,
    )

    assert (
        json.loads(public_connection_corpus_to_json(benchmark.public))["synthetic"]
        is True
    )
    with pytest.raises(ValidationError):
        public_connection_corpus_to_json(benchmark)  # type: ignore[arg-type]
