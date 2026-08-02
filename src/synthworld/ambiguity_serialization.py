"""Frozen artifacts for the ambiguity pack, with the two truths kept apart.

Issue #41 requires canonical entity truth and public-evidence disposition to be
*separately serialized*, and the separation is not cosmetic. A consumer building a
resolver should be able to hold the public corpus without either truth; a consumer
scoring clusters needs memberships and not dispositions; a consumer scoring
abstention needs dispositions and not memberships. One file containing all three
makes every one of those a matter of discipline rather than of access.
"""

from __future__ import annotations

import hashlib
from importlib.resources import files

from synthworld.ambiguity import (
    AMBIGUITY_SCHEMA_VERSION,
    AmbiguityAnswerKey,
    AmbiguityBenchmark,
    PairTruth,
    PublicAmbiguityTask,
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


__all__ = [
    "AmbiguityIntegrityError",
    "DispositionTruth",
    "MembershipTruth",
    "ambiguity_artifacts",
    "ambiguity_manifest",
    "ambiguity_public_to_json",
    "disposition_truth_to_json",
    "load_golden_ambiguity_benchmark",
    "load_golden_ambiguity_disposition_truth",
    "load_golden_ambiguity_membership_truth",
    "load_golden_ambiguity_public_task",
    "membership_truth_to_json",
]
