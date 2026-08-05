"""Frozen artifacts for the ambiguity pack, with the two truths kept apart.

Issue #41 requires canonical entity truth and public-evidence disposition to be
*separately serialized*, and the separation is not cosmetic. A consumer building a
resolver should be able to hold the public corpus without either truth; a consumer
scoring clusters needs memberships and not dispositions; a consumer scoring
abstention needs dispositions and not memberships. One file containing all three
makes every one of those a matter of discipline rather than of access.

The v2 functions follow the same split for generated packs. A v2 pack has no frozen
golden artifacts - it is keyed, and its truth is never shipped with its public task -
so the serializers here are projections, kept separate so a pipeline cannot reach a
truth while holding only the other half.
"""

from __future__ import annotations

import hashlib
from importlib.resources import files
from uuid import UUID

from synthworld.ambiguity import (
    AMBIGUITY_SCHEMA_VERSION,
    AmbiguityAnswerKey,
    AmbiguityBenchmark,
    PairDisposition,
    PairTruth,
    PublicAmbiguityTask,
)
from synthworld.ambiguity_v2 import (
    AMBIGUITY_V2_SCHEMA_VERSION,
    DerivedPairTruth,
    PublicAmbiguityTaskV2,
)
from synthworld.connection import RecordMembership
from synthworld.models import SyntheticModel

_PUBLIC_FILENAME = "ambiguity-public-v1.json"
_MEMBERSHIP_FILENAME = "ambiguity-memberships-v1.json"
_DISPOSITION_FILENAME = "ambiguity-dispositions-v1.json"
_MANIFEST = "AMBIGUITY_SHA256SUMS"


class AmbiguityIntegrityError(ValueError):
    """Raised when a frozen ambiguity artifact fails its integrity gate."""


class MembershipTruth(SyntheticModel):
    """Canonical entity membership, alone."""

    schema_version: str = AMBIGUITY_SCHEMA_VERSION
    record_memberships: tuple[RecordMembership, ...]


class DispositionTruth(SyntheticModel):
    """What the public evidence justifies, alone."""

    schema_version: str = AMBIGUITY_SCHEMA_VERSION
    pairs: tuple[PairTruth, ...]


def ambiguity_artifacts(benchmark: AmbiguityBenchmark) -> dict[str, bytes]:
    """Return the three canonical artifacts, physically separate."""

    return {
        _PUBLIC_FILENAME: ambiguity_public_to_json(benchmark.public),
        _MEMBERSHIP_FILENAME: membership_truth_to_json(
            MembershipTruth(record_memberships=benchmark.answer_key.record_memberships)
        ),
        _DISPOSITION_FILENAME: disposition_truth_to_json(
            DispositionTruth(pairs=benchmark.answer_key.pairs)
        ),
    }


def ambiguity_manifest(artifacts: dict[str, bytes]) -> str:
    """A sha256sum-format manifest, one line per artifact."""

    return "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(artifacts.items())
    )


def _verified_payload(name: str) -> bytes:
    directory = files("synthworld.benchmarks")
    manifest = directory.joinpath(_MANIFEST).read_text(encoding="utf-8")
    expected = dict(
        (fields[1], fields[0])
        for fields in (line.split() for line in manifest.strip().splitlines())
        if len(fields) == 2
    )
    if set(expected) != {
        _PUBLIC_FILENAME,
        _MEMBERSHIP_FILENAME,
        _DISPOSITION_FILENAME,
    }:
        raise AmbiguityIntegrityError("frozen ambiguity manifest is incomplete")

    content = directory.joinpath(name).read_bytes()
    if hashlib.sha256(content).hexdigest() != expected[name]:
        raise AmbiguityIntegrityError(f"{name} checksum differs")
    return content


def load_golden_ambiguity_public_task() -> PublicAmbiguityTask:
    """Load only checksum-verified public input, without reading either truth."""

    return PublicAmbiguityTask.model_validate_json(_verified_payload(_PUBLIC_FILENAME))


def load_golden_ambiguity_membership_truth() -> MembershipTruth:
    """Load only checksum-verified canonical membership truth."""

    return MembershipTruth.model_validate_json(_verified_payload(_MEMBERSHIP_FILENAME))


def load_golden_ambiguity_disposition_truth() -> DispositionTruth:
    """Load only checksum-verified evidence-disposition truth."""

    return DispositionTruth.model_validate_json(
        _verified_payload(_DISPOSITION_FILENAME)
    )


def load_golden_ambiguity_benchmark() -> AmbiguityBenchmark:
    """Load and verify all three frozen artifacts before recombining them."""

    public = load_golden_ambiguity_public_task()
    memberships = load_golden_ambiguity_membership_truth()
    dispositions = load_golden_ambiguity_disposition_truth()

    return AmbiguityBenchmark(
        seed=public.corpus.seed,
        public=public,
        answer_key=AmbiguityAnswerKey(
            record_memberships=memberships.record_memberships,
            pairs=dispositions.pairs,
        ),
    )


def _payload(model: SyntheticModel) -> bytes:
    return f"{model.model_dump_json(indent=2)}\n".encode()


def ambiguity_public_to_json(public: PublicAmbiguityTask) -> bytes:
    return _payload(public)


def membership_truth_to_json(truth: MembershipTruth) -> bytes:
    return _payload(truth)


def disposition_truth_to_json(truth: DispositionTruth) -> bytes:
    return _payload(truth)


# ---------------------------------------------------------------------------
# v2 projections. A generated v2 pack carries no frozen golden artifacts - its
# truth is keyed and never shipped with the public task - so these serializers
# project the same two truths apart, physically, for consumers that hold one
# half without the other. The disposition truth drops the latent comparison
# vector: it is not needed to score dispositions, and shipping it would put the
# relations - the answer in a thinner disguise - one attribute access away.
# ---------------------------------------------------------------------------


class AmbiguityV2PairTruth(SyntheticModel):
    """One v2 pair's scored truth: what is the case, and what the evidence justifies."""

    left_record_id: UUID
    right_record_id: UUID
    same_entity: bool
    disposition: PairDisposition


class AmbiguityV2DispositionTruth(SyntheticModel):
    """What the public evidence justifies, for every pair of a generated pack."""

    schema_version: str = AMBIGUITY_V2_SCHEMA_VERSION
    pairs: tuple[AmbiguityV2PairTruth, ...]


class AmbiguityV2MembershipTruth(SyntheticModel):
    """Canonical entity membership for every record of a generated pack."""

    schema_version: str = AMBIGUITY_V2_SCHEMA_VERSION
    record_memberships: tuple[RecordMembership, ...]


def ambiguity_v2_truths(
    public: PublicAmbiguityTaskV2, truths: tuple[DerivedPairTruth, ...]
) -> tuple[AmbiguityV2DispositionTruth, AmbiguityV2MembershipTruth]:
    """Project derived truths to the two independent, separately-typed halves.

    Membership is union-find over the pairs that really are one person: a
    `same_entity` pair joins its records into one entity, and every record the
    pairs never join - a non-match pair's records, or distractors no pair asks
    about - is an entity of one. Entity ids are canonical: the least member's id,
    so the projection is a function of the truth and nothing else.
    """

    parent: dict[UUID, UUID] = {
        record.id: record.id for record in public.corpus.identity_records
    }

    def find(record: UUID) -> UUID:
        while parent[record] != record:
            parent[record] = parent[parent[record]]
            record = parent[record]
        return record

    for truth in truths:
        left_root, right_root = find(truth.left_record_id), find(truth.right_record_id)
        if truth.same_entity and left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    pairs = tuple(
        AmbiguityV2PairTruth(
            left_record_id=truth.left_record_id,
            right_record_id=truth.right_record_id,
            same_entity=truth.same_entity,
            disposition=truth.disposition,
        )
        for truth in truths
    )
    memberships = tuple(
        RecordMembership(record_id=record, entity_id=str(find(record)))
        for record in sorted(parent)
    )
    return (
        AmbiguityV2DispositionTruth(pairs=pairs),
        AmbiguityV2MembershipTruth(record_memberships=memberships),
    )


def ambiguity_v2_public_to_json(public: PublicAmbiguityTaskV2) -> bytes:
    return _payload(public)


def ambiguity_v2_disposition_truth_to_json(truth: AmbiguityV2DispositionTruth) -> bytes:
    return _payload(truth)


def ambiguity_v2_membership_truth_to_json(truth: AmbiguityV2MembershipTruth) -> bytes:
    return _payload(truth)


def ambiguity_v2_artifacts(
    public: PublicAmbiguityTaskV2, truths: tuple[DerivedPairTruth, ...]
) -> dict[str, bytes]:
    """The three v2 artifacts, physically separate, as bytes."""

    dispositions, memberships = ambiguity_v2_truths(public, truths)
    return {
        "ambiguity-v2-public.json": ambiguity_v2_public_to_json(public),
        "ambiguity-v2-memberships.json": ambiguity_v2_membership_truth_to_json(
            memberships
        ),
        "ambiguity-v2-dispositions.json": ambiguity_v2_disposition_truth_to_json(
            dispositions
        ),
    }


def ambiguity_v2_manifest(artifacts: dict[str, bytes]) -> str:
    """A sha256sum-format manifest, one line per artifact."""

    return ambiguity_manifest(artifacts)


__all__ = [
    "AmbiguityIntegrityError",
    "AmbiguityV2DispositionTruth",
    "AmbiguityV2MembershipTruth",
    "AmbiguityV2PairTruth",
    "DispositionTruth",
    "MembershipTruth",
    "ambiguity_artifacts",
    "ambiguity_manifest",
    "ambiguity_public_to_json",
    "ambiguity_v2_artifacts",
    "ambiguity_v2_disposition_truth_to_json",
    "ambiguity_v2_manifest",
    "ambiguity_v2_membership_truth_to_json",
    "ambiguity_v2_public_to_json",
    "ambiguity_v2_truths",
    "disposition_truth_to_json",
    "load_golden_ambiguity_benchmark",
    "load_golden_ambiguity_disposition_truth",
    "load_golden_ambiguity_membership_truth",
    "load_golden_ambiguity_public_task",
    "membership_truth_to_json",
]
