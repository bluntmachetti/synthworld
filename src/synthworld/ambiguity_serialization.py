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
        _PUBLIC_FILENAME: _payload(benchmark.public),
        _MEMBERSHIP_FILENAME: _payload(
            MembershipTruth(record_memberships=benchmark.answer_key.record_memberships)
        ),
        _DISPOSITION_FILENAME: _payload(
            DispositionTruth(pairs=benchmark.answer_key.pairs)
        ),
    }


def ambiguity_manifest(artifacts: dict[str, bytes]) -> str:
    """A sha256sum-format manifest, one line per artifact."""

    return "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(artifacts.items())
    )


def load_golden_ambiguity_benchmark() -> AmbiguityBenchmark:
    """Load and verify all three frozen artifacts before recombining them."""

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

    payloads: dict[str, bytes] = {}
    for name, digest in expected.items():
        content = directory.joinpath(name).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise AmbiguityIntegrityError(f"{name} checksum differs")
        payloads[name] = content

    return AmbiguityBenchmark(
        seed=PublicAmbiguityTask.model_validate_json(
            payloads[_PUBLIC_FILENAME]
        ).corpus.seed,
        public=PublicAmbiguityTask.model_validate_json(payloads[_PUBLIC_FILENAME]),
        answer_key=AmbiguityAnswerKey(
            record_memberships=MembershipTruth.model_validate_json(
                payloads[_MEMBERSHIP_FILENAME]
            ).record_memberships,
            pairs=DispositionTruth.model_validate_json(
                payloads[_DISPOSITION_FILENAME]
            ).pairs,
        ),
    )


def _payload(model: SyntheticModel) -> bytes:
    return f"{model.model_dump_json(indent=2)}\n".encode()


__all__ = [
    "AmbiguityIntegrityError",
    "DispositionTruth",
    "MembershipTruth",
    "ambiguity_artifacts",
    "ambiguity_manifest",
    "load_golden_ambiguity_benchmark",
]
