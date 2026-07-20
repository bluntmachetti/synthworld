from __future__ import annotations

import hashlib
import re
from collections import Counter
from importlib.resources import files
from itertools import chain, combinations
from urllib.parse import urlparse
from uuid import UUID

from pydantic import Field

from synthworld.connection import (
    AdversarialCase,
    AdversarialPackKind,
    ConnectionBenchmark,
    PublicAssociationKind,
    PublicAssociationRecord,
    PublicIdentityAttribute,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    PublicRelationshipTruth,
    PublicTruthRelationshipKind,
)
from synthworld.connection_generator import (
    generate_adversarial_connection_benchmark,
    generate_relationship_connection_benchmark,
)
from synthworld.connection_serialization import connection_benchmark_to_json
from synthworld.generator import generate_world
from synthworld.models import RelationshipKind, SyntheticModel, SynthWorld

_EMAIL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._+-]*@example\.test$")
_FAMILY_NAME_PATTERN = re.compile(r"^[^\W\d_]+(?:[ '-][^\W\d_]+)*$")
_USERNAME_PATTERN = re.compile(r"^synth_[a-z0-9_]+$")
_PHONE_PATTERN = re.compile(r"^\+1-[0-9]{3}-555-01[0-9]{2}$")
_ADDRESS_PATTERN = re.compile(
    r"^[1-9][0-9]*\|(?:[1-9][0-9]*|Adversarial) "
    r"Example Avenue\|Testville\|00000\|ZZ$"
)
_DATE_PATTERN = re.compile(
    r"^(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])$"
)
_EMPLOYER_PATTERN = re.compile(r"^Example [A-Za-z0-9][A-Za-z0-9 .'-]*$")
_SCHOOL_YEAR_PATTERN = re.compile(r"^Test University [0-9]{4}\|(?:19|20|21)[0-9]{2}$")
_ROUTING_ORACLE_PATTERN = re.compile(
    r"\b(?:persona|entity|relationship)-[0-9]{4}\b",
    re.IGNORECASE,
)
_FORBIDDEN_ORACLE_TOKENS = frozenset(
    {
        "actual_persona_id",
        "answer_key",
        "connected_person_ids",
        "expected_cluster",
        "match_kind",
        *(item.value for item in AdversarialPackKind),
    }
)
_EXPECTED_PACKS = {
    AdversarialPackKind.COMMON_NAME: (4, 2, 2, 4),
    AdversarialPackKind.UNICODE_DIACRITICS: (3, 2, 1, 2),
    AdversarialPackKind.TWINS_SHARED_ADDRESS: (4, 2, 2, 4),
    AdversarialPackKind.MAIDEN_NAME: (3, 2, 1, 2),
    AdversarialPackKind.MISSPELLING_ALIAS: (4, 2, 3, 3),
}


class AdversarialPackMetrics(SyntheticModel):
    pack: AdversarialPackKind
    record_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    same_entity_pair_count: int = Field(ge=0)
    different_entity_pair_count: int = Field(ge=0)


class ConnectionBenchmarkMetrics(SyntheticModel):
    adversarial_record_count: int = Field(ge=0)
    truth_entity_count: int = Field(ge=0)
    possible_record_pair_count: int = Field(ge=0)
    same_entity_pair_count: int = Field(ge=0)
    different_entity_pair_count: int = Field(ge=0)
    packs: tuple[AdversarialPackMetrics, ...]
    membership_integrity: float = Field(ge=0.0, le=1.0)
    pack_integrity: float = Field(ge=0.0, le=1.0)
    public_identity_record_count: int = Field(ge=0)
    property_adjacency_record_count: int = Field(ge=0)
    profile_link_record_count: int = Field(ge=0)
    neighbor_relationship_count: int = Field(ge=0)
    social_relationship_count: int = Field(ge=0)
    unilateral_property_control_count: int = Field(ge=0)
    unilateral_profile_control_count: int = Field(ge=0)
    neighbor_reciprocal_evidence_coverage: float = Field(ge=0.0, le=1.0)
    social_reciprocal_evidence_coverage: float = Field(ge=0.0, le=1.0)
    unilateral_control_integrity: float = Field(ge=0.0, le=1.0)
    public_reference_integrity: float = Field(ge=0.0, le=1.0)
    safely_fake_record_rate: float = Field(ge=0.0, le=1.0)
    deterministic_replay_integrity: float = Field(ge=0.0, le=1.0)
    manifest_integrity: float = Field(ge=0.0, le=1.0)
    answer_key_separation_integrity: float = Field(ge=0.0, le=1.0)


def evaluate_connection_benchmarks(
    adversarial: ConnectionBenchmark,
    relationships: ConnectionBenchmark,
) -> ConnectionBenchmarkMetrics:
    """Measure only the frozen corpus and public-input claims in spec 010."""

    record_ids = tuple(item.id for item in adversarial.public.identity_records)
    memberships = adversarial.answer_key.record_memberships
    membership_record_ids = tuple(item.record_id for item in memberships)
    membership_integrity = float(
        len(membership_record_ids) == len(set(membership_record_ids))
        and len(membership_record_ids) == len(record_ids)
        and set(membership_record_ids) == set(record_ids)
    )
    entity_by_record = {item.record_id: item.entity_id for item in memberships}
    entity_counts = Counter(entity_by_record.values())
    possible_pairs = _pair_count(len(record_ids))
    same_pairs = sum(_pair_count(count) for count in entity_counts.values())
    pack_metrics = tuple(
        _evaluate_pack(item, entity_by_record)
        for item in adversarial.answer_key.adversarial_cases
    )
    cases = adversarial.answer_key.adversarial_cases
    pack_integrity = float(
        {item.pack: _pack_values(item) for item in pack_metrics} == _EXPECTED_PACKS
        and Counter(chain.from_iterable(item.record_ids for item in cases))
        == Counter(record_ids)
        and _pack_entities_are_consistent(
            cases,
            entity_by_record,
            set(entity_counts),
        )
    )

    public = relationships.public
    associations = public.association_records
    property_records = tuple(
        item
        for item in associations
        if item.kind is PublicAssociationKind.PROPERTY_ADJACENCY
    )
    profile_records = tuple(
        item for item in associations if item.kind is PublicAssociationKind.PROFILE_LINK
    )
    neighbor_truth = tuple(
        item
        for item in relationships.answer_key.relationships
        if item.kind is PublicTruthRelationshipKind.NEIGHBOR
    )
    social_truth = tuple(
        item
        for item in relationships.answer_key.relationships
        if item.kind is PublicTruthRelationshipKind.SOCIAL
    )
    property_controls = tuple(
        item
        for item in relationships.answer_key.unilateral_controls
        if item.kind is PublicAssociationKind.PROPERTY_ADJACENCY
    )
    profile_controls = tuple(
        item
        for item in relationships.answer_key.unilateral_controls
        if item.kind is PublicAssociationKind.PROFILE_LINK
    )
    public_corpora = (adversarial.public, relationships.public)
    all_identity_records = tuple(
        chain.from_iterable(item.identity_records for item in public_corpora)
    )
    all_association_records = tuple(
        chain.from_iterable(item.association_records for item in public_corpora)
    )
    safe_records = sum(_identity_record_is_safe(item) for item in all_identity_records)
    safe_records += sum(
        _association_record_is_safe(item) for item in all_association_records
    )
    public_record_count = len(all_identity_records) + len(all_association_records)
    world = _relationship_world(relationships)
    expected_neighbor_truth = _expected_relationship_keys(
        world,
        PublicTruthRelationshipKind.NEIGHBOR,
    )
    expected_social_truth = _expected_relationship_keys(
        world,
        PublicTruthRelationshipKind.SOCIAL,
    )

    return ConnectionBenchmarkMetrics(
        adversarial_record_count=len(record_ids),
        truth_entity_count=len(entity_counts),
        possible_record_pair_count=possible_pairs,
        same_entity_pair_count=same_pairs,
        different_entity_pair_count=possible_pairs - same_pairs,
        packs=pack_metrics,
        membership_integrity=membership_integrity,
        pack_integrity=pack_integrity,
        public_identity_record_count=len(public.identity_records),
        property_adjacency_record_count=len(property_records),
        profile_link_record_count=len(profile_records),
        neighbor_relationship_count=len(neighbor_truth),
        social_relationship_count=len(social_truth),
        unilateral_property_control_count=len(property_controls),
        unilateral_profile_control_count=len(profile_controls),
        neighbor_reciprocal_evidence_coverage=_relationship_coverage(
            neighbor_truth,
            relationships,
            expected_neighbor_truth,
        ),
        social_reciprocal_evidence_coverage=_relationship_coverage(
            social_truth,
            relationships,
            expected_social_truth,
        ),
        unilateral_control_integrity=_control_integrity(relationships, world),
        public_reference_integrity=_reference_integrity(relationships),
        safely_fake_record_rate=_rate(
            safe_records,
            public_record_count,
            empty=0.0,
        ),
        deterministic_replay_integrity=_deterministic_replay_integrity(
            adversarial, relationships
        ),
        manifest_integrity=_manifest_integrity(adversarial),
        answer_key_separation_integrity=float(
            _public_shape_is_exact(adversarial)
            and _public_shape_is_exact(relationships)
            and _public_content_is_oracle_free(adversarial)
            and _public_content_is_oracle_free(relationships)
        ),
    )


def _evaluate_pack(
    case: AdversarialCase,
    entity_by_record: dict[UUID, str],
) -> AdversarialPackMetrics:
    pack = case.pack
    record_ids = case.record_ids
    entities = [
        entity_by_record[record_id]
        for record_id in record_ids
        if record_id in entity_by_record
    ]
    counts = Counter(entities)
    possible_pairs = _pair_count(len(record_ids))
    same_pairs = sum(_pair_count(count) for count in counts.values())
    return AdversarialPackMetrics(
        pack=pack,
        record_count=len(record_ids),
        entity_count=len(set(entities)),
        same_entity_pair_count=same_pairs,
        different_entity_pair_count=possible_pairs - same_pairs,
    )


def _pack_values(item: AdversarialPackMetrics) -> tuple[int, int, int, int]:
    return (
        item.record_count,
        item.entity_count,
        item.same_entity_pair_count,
        item.different_entity_pair_count,
    )


def _pack_entities_are_consistent(
    cases: tuple[AdversarialCase, ...],
    entity_by_record: dict[UUID, str],
    expected_entities: set[str],
) -> bool:
    derived_entities = tuple(
        {
            entity_by_record[record_id]
            for record_id in case.record_ids
            if record_id in entity_by_record
        }
        for case in cases
    )
    declared_entities = tuple(set(case.entity_ids) for case in cases)
    declared_match = all(
        declared == derived
        for declared, derived in zip(declared_entities, derived_entities, strict=True)
    )
    declared_union = set().union(*declared_entities) if declared_entities else set()
    return (
        declared_match
        and sum(map(len, declared_entities)) == len(declared_union)
        and declared_union == expected_entities
    )


type RelationshipKey = tuple[str, str, PublicTruthRelationshipKind]


def _relationship_world(benchmark: ConnectionBenchmark) -> SynthWorld | None:
    persona_count = len(benchmark.answer_key.record_memberships)
    if not 2 <= persona_count <= 1_000:
        return None
    return generate_world(seed=benchmark.seed, persona_count=persona_count)


def _expected_relationship_keys(
    world: SynthWorld | None,
    kind: PublicTruthRelationshipKind,
) -> frozenset[RelationshipKey]:
    if world is None:
        return frozenset()
    source_kind = RelationshipKind(kind.value)
    return frozenset(
        _canonical_relationship_key(
            edge.source_person_id,
            edge.target_person_id,
            kind,
        )
        for edge in world.relationships
        if edge.kind is source_kind
    )


def _relationship_coverage(
    truth: tuple[PublicRelationshipTruth, ...],
    benchmark: ConnectionBenchmark,
    expected_truth: frozenset[RelationshipKey],
) -> float:
    entity_by_record = {
        item.record_id: item.entity_id
        for item in benchmark.answer_key.record_memberships
    }
    seen: set[RelationshipKey] = set()
    valid: set[RelationshipKey] = set()
    unexpected = 0
    for item in truth:
        key = _relationship_key(item, entity_by_record)
        if key is None or key not in expected_truth or key in seen:
            unexpected += 1
            continue
        seen.add(key)
        if _relationship_has_reciprocal_evidence(item, benchmark):
            valid.add(key)
    return _rate(
        len(valid),
        len(expected_truth) + unexpected,
        empty=0.0,
    )


def _relationship_key(
    truth: PublicRelationshipTruth,
    entity_by_record: dict[UUID, str],
) -> RelationshipKey | None:
    source = entity_by_record.get(truth.source_record_id)
    target = entity_by_record.get(truth.target_record_id)
    if source is None or target is None:
        return None
    return _canonical_relationship_key(source, target, truth.kind)


def _canonical_relationship_key(
    source: str,
    target: str,
    kind: PublicTruthRelationshipKind,
) -> RelationshipKey:
    first, second = sorted((source, target))
    return first, second, kind


def _relationship_has_reciprocal_evidence(
    truth: PublicRelationshipTruth,
    benchmark: ConnectionBenchmark,
) -> bool:
    records = {item.id: item for item in benchmark.public.identity_records}
    associations = {item.id: item for item in benchmark.public.association_records}
    if truth.source_record_id not in records or truth.target_record_id not in records:
        return False
    evidence = tuple(
        associations[item]
        for item in truth.reciprocal_association_ids
        if item in associations
    )
    if len(evidence) != 2:
        return False
    association_kind, attribute_kind = _truth_kinds(truth.kind)
    source_references = _attribute_values(
        records[truth.source_record_id], attribute_kind
    )
    target_references = _attribute_values(
        records[truth.target_record_id], attribute_kind
    )
    directions = {
        (item.source_reference, item.target_reference)
        for item in evidence
        if item.kind is association_kind
    }
    return directions == {
        (source, target) for source in source_references for target in target_references
    } | {
        (target, source) for source in source_references for target in target_references
    }


def _truth_kinds(
    kind: PublicTruthRelationshipKind,
) -> tuple[PublicAssociationKind, PublicIdentityAttributeKind]:
    if kind is PublicTruthRelationshipKind.NEIGHBOR:
        return (
            PublicAssociationKind.PROPERTY_ADJACENCY,
            PublicIdentityAttributeKind.FULL_ADDRESS,
        )
    return (
        PublicAssociationKind.PROFILE_LINK,
        PublicIdentityAttributeKind.SOCIAL_PROFILE,
    )


def _attribute_values(
    record: PublicIdentityRecord,
    kind: PublicIdentityAttributeKind,
) -> set[str]:
    return {item.value for item in record.attributes if item.kind is kind}


def _control_integrity(
    benchmark: ConnectionBenchmark,
    world: SynthWorld | None,
) -> float:
    associations = {item.id: item for item in benchmark.public.association_records}
    truth_ids = {
        item
        for truth in benchmark.answer_key.relationships
        for item in truth.reciprocal_association_ids
    }
    expected_references = _expected_control_references(benchmark, world)
    valid = 0
    controls = benchmark.answer_key.unilateral_controls
    for control in controls:
        association = associations.get(control.association_id)
        if association is None:
            continue
        reverse_exists = any(
            item.kind is association.kind
            and item.source_reference == association.target_reference
            and item.target_reference == association.source_reference
            for item in associations.values()
        )
        valid += (
            association.kind is control.kind
            and association.id not in truth_ids
            and not reverse_exists
            and frozenset((association.source_reference, association.target_reference))
            == expected_references.get(control.kind, frozenset())
        )
    expected_counts = Counter(
        (
            PublicAssociationKind.PROPERTY_ADJACENCY,
            PublicAssociationKind.PROFILE_LINK,
        )
    )
    actual_counts = Counter(item.kind for item in controls)
    return float(valid == len(controls) and actual_counts == expected_counts)


def _expected_control_references(
    benchmark: ConnectionBenchmark,
    world: SynthWorld | None,
) -> dict[PublicAssociationKind, frozenset[str]]:
    if world is None:
        return {}
    edge_pairs = {
        frozenset((item.source_person_id, item.target_person_id))
        for item in world.relationships
    }
    control_pairs = tuple(
        (source.id, target.id)
        for source, target in combinations(world.personas, 2)
        if frozenset((source.id, target.id)) not in edge_pairs
    )
    if not control_pairs:
        return {}
    records_by_id = {item.id: item for item in benchmark.public.identity_records}
    records_by_entity = {
        membership.entity_id: records_by_id[membership.record_id]
        for membership in benchmark.answer_key.record_memberships
        if membership.record_id in records_by_id
    }
    if any(
        entity_id not in records_by_entity
        for control_pair in control_pairs
        for entity_id in control_pair
    ):
        return {}
    addresses = {
        entity_id: _attribute_values(
            record,
            PublicIdentityAttributeKind.FULL_ADDRESS,
        )
        for entity_id, record in records_by_entity.items()
    }
    address_counts = Counter(
        value for record_addresses in addresses.values() for value in record_addresses
    )
    property_pair = next(
        (
            pair
            for pair in control_pairs
            if all(
                len(addresses[entity_id]) == 1
                and address_counts[next(iter(addresses[entity_id]))] == 1
                for entity_id in pair
            )
        ),
        control_pairs[0],
    )
    profile_pair = control_pairs[0]

    def references_for(
        pair: tuple[str, str],
        kind: PublicIdentityAttributeKind,
    ) -> frozenset[str]:
        return frozenset(
            value
            for entity_id in pair
            for value in _attribute_values(records_by_entity[entity_id], kind)
        )

    return {
        PublicAssociationKind.PROPERTY_ADJACENCY: references_for(
            property_pair,
            PublicIdentityAttributeKind.FULL_ADDRESS,
        ),
        PublicAssociationKind.PROFILE_LINK: references_for(
            profile_pair,
            PublicIdentityAttributeKind.SOCIAL_PROFILE,
        ),
    }


def _reference_integrity(benchmark: ConnectionBenchmark) -> float:
    references: dict[PublicAssociationKind, set[str]] = {
        PublicAssociationKind.PROPERTY_ADJACENCY: set(),
        PublicAssociationKind.PROFILE_LINK: set(),
    }
    for record in benchmark.public.identity_records:
        references[PublicAssociationKind.PROPERTY_ADJACENCY].update(
            _attribute_values(record, PublicIdentityAttributeKind.FULL_ADDRESS)
        )
        references[PublicAssociationKind.PROFILE_LINK].update(
            _attribute_values(record, PublicIdentityAttributeKind.SOCIAL_PROFILE)
        )
    valid = sum(
        item.source_reference in references[item.kind]
        and item.target_reference in references[item.kind]
        for item in benchmark.public.association_records
    )
    return _rate(
        valid,
        len(benchmark.public.association_records),
        empty=0.0,
    )


def _identity_record_is_safe(record: PublicIdentityRecord) -> bool:
    return (
        record.synthetic is True
        and _is_reserved_url(record.source_url)
        and all(
            item.synthetic is True and _attribute_is_safe(item)
            for item in record.attributes
        )
    )


def _attribute_is_safe(attribute: PublicIdentityAttribute) -> bool:
    if attribute.kind is PublicIdentityAttributeKind.EMAIL:
        return _EMAIL_PATTERN.fullmatch(attribute.value) is not None
    if attribute.kind is PublicIdentityAttributeKind.FAMILY_NAME:
        return _FAMILY_NAME_PATTERN.fullmatch(attribute.value) is not None
    if attribute.kind is PublicIdentityAttributeKind.USERNAME:
        return _USERNAME_PATTERN.fullmatch(attribute.value) is not None
    if attribute.kind is PublicIdentityAttributeKind.PHONE:
        return _PHONE_PATTERN.fullmatch(attribute.value) is not None
    if attribute.kind is PublicIdentityAttributeKind.FULL_ADDRESS:
        return _address_is_safe(attribute.value)
    if attribute.kind is PublicIdentityAttributeKind.DATE_OF_BIRTH:
        return _DATE_PATTERN.fullmatch(attribute.value) is not None
    if attribute.kind is PublicIdentityAttributeKind.EMPLOYER:
        return _EMPLOYER_PATTERN.fullmatch(attribute.value) is not None
    if attribute.kind is PublicIdentityAttributeKind.SCHOOL_YEAR:
        return _SCHOOL_YEAR_PATTERN.fullmatch(attribute.value) is not None
    return _is_reserved_url(attribute.value)


def _association_record_is_safe(record: PublicAssociationRecord) -> bool:
    references_are_safe = (
        _address_is_safe(record.source_reference)
        and _address_is_safe(record.target_reference)
        if record.kind is PublicAssociationKind.PROPERTY_ADJACENCY
        else _is_reserved_url(record.source_reference)
        and _is_reserved_url(record.target_reference)
    )
    return (
        record.synthetic is True
        and _is_reserved_url(record.source_url)
        and references_are_safe
    )


def _address_is_safe(value: str) -> bool:
    return _ADDRESS_PATTERN.fullmatch(value) is not None


def _is_reserved_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and (
        parsed.hostname == "example.test"
        or (parsed.hostname or "").endswith(".example.test")
    )


def _deterministic_replay_integrity(
    adversarial: ConnectionBenchmark,
    relationships: ConnectionBenchmark,
) -> float:
    expected_adversarial = generate_adversarial_connection_benchmark(
        seed=adversarial.seed
    )
    expected_relationships = generate_relationship_connection_benchmark(
        seed=relationships.seed,
        persona_count=len(relationships.public.identity_records),
    )
    return float(
        connection_benchmark_to_json(adversarial)
        == connection_benchmark_to_json(expected_adversarial)
        and connection_benchmark_to_json(relationships)
        == connection_benchmark_to_json(expected_relationships)
    )


def _manifest_integrity(adversarial: ConnectionBenchmark) -> float:
    benchmark_directory = files("synthworld.benchmarks")
    benchmark_bytes = benchmark_directory.joinpath(
        "connection-golden-v1.json"
    ).read_bytes()
    manifest = benchmark_directory.joinpath("CONNECTION_SHA256SUMS").read_text(
        encoding="utf-8"
    )
    expected_hash, filename = manifest.strip().split(maxsplit=1)
    return float(
        filename == "connection-golden-v1.json"
        and hashlib.sha256(benchmark_bytes).hexdigest() == expected_hash
        and connection_benchmark_to_json(adversarial).encode() == benchmark_bytes
    )


def _public_shape_is_exact(benchmark: ConnectionBenchmark) -> bool:
    public = benchmark.public.model_dump(mode="json")
    return (
        set(public)
        == {
            "synthetic",
            "schema_version",
            "seed",
            "identity_records",
            "association_records",
        }
        and all(
            set(record)
            == {
                "synthetic",
                "id",
                "source_type",
                "source_url",
                "display_name",
                "confidence",
                "attributes",
            }
            and all(
                set(attribute) == {"synthetic", "kind", "value", "confidence"}
                for attribute in record["attributes"]
            )
            for record in public["identity_records"]
        )
        and all(
            set(record)
            == {
                "synthetic",
                "id",
                "kind",
                "source_url",
                "source_reference",
                "target_reference",
                "confidence",
            }
            for record in public["association_records"]
        )
    )


def _public_content_is_oracle_free(benchmark: ConnectionBenchmark) -> bool:
    values = chain(
        (
            value
            for record in benchmark.public.identity_records
            for value in (record.source_url, record.display_name)
        ),
        (
            attribute.value
            for record in benchmark.public.identity_records
            for attribute in record.attributes
        ),
        (
            value
            for record in benchmark.public.association_records
            for value in (
                record.source_url,
                record.source_reference,
                record.target_reference,
            )
        ),
    )
    return not any(_contains_oracle(value) for value in values)


def _contains_oracle(value: str) -> bool:
    lowered = value.casefold()
    return _ROUTING_ORACLE_PATTERN.search(value) is not None or any(
        item in lowered for item in _FORBIDDEN_ORACLE_TOKENS
    )


def _pair_count(count: int) -> int:
    return count * (count - 1) // 2


def _rate(numerator: int, denominator: int, *, empty: float = 1.0) -> float:
    return numerator / denominator if denominator else empty


__all__ = [
    "AdversarialPackMetrics",
    "ConnectionBenchmarkMetrics",
    "evaluate_connection_benchmarks",
]
