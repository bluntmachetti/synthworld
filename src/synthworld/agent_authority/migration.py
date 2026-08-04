"""Lossless field ownership for the superseded run-manifest draft.

The ``0.1.0-draft`` did not contain enough provenance or typed protocol data to
construct receipt v2 and agent-authority v1 artifacts by itself.  This module
therefore performs the safe part of migration: it validates the draft field
surface, assigns every source field to its authoritative successor artifact, and
preserves every value unchanged.  A migration caller must then supply the newer
contracts' additional required data explicitly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from synthworld.agent_authority.common import AgentAuthorityOperatorModel

LEGACY_RUN_MANIFEST_VERSION: Literal["0.1.0-draft"] = "0.1.0-draft"

_RECEIPT_V2_FIELDS = (
    "manifest_version",
    "run_id",
    "created_at",
    "completed_at",
    "operator",
    "benchmark_identity",
    "scoring",
    "build_provenance",
    "adapter",
    "systems_under_test",
)
_RUN_PLAN_FIELDS = (
    "run_layer",
    "controls_exercised",
    "topology",
    "authority_critical_dependencies",
    "declared_bounds",
    "review",
    "conflicts_declared",
)
_OBSERVATION_FIELDS = ("limitations",)
_KNOWN_FIELDS = frozenset(
    (*_RECEIPT_V2_FIELDS, *_RUN_PLAN_FIELDS, *_OBSERVATION_FIELDS)
)
_REQUIRED_FIELDS = frozenset(
    {
        "manifest_version",
        "run_id",
        "created_at",
        "run_layer",
        "benchmark_identity",
        "scoring",
        "build_provenance",
        "systems_under_test",
    }
)


class LegacyDraftMigrationError(ValueError):
    """The source is not a supported ``0.1.0-draft`` field surface."""


class LegacyDraftFieldV1(AgentAuthorityOperatorModel):
    """One source field retained byte-semantically under its original name."""

    name: str = Field(min_length=1)
    value: JsonValue


class LegacyDraftRunManifestPartitionV1(AgentAuthorityOperatorModel):
    """Deterministic ownership plan for all fields in one legacy document."""

    source_manifest_version: Literal["0.1.0-draft"] = LEGACY_RUN_MANIFEST_VERSION
    receipt_v2_fields: tuple[LegacyDraftFieldV1, ...]
    run_plan_fields: tuple[LegacyDraftFieldV1, ...]
    observation_fields: tuple[LegacyDraftFieldV1, ...]

    def reconstruct_source(self) -> dict[str, JsonValue]:
        """Reconstruct the exact parsed source mapping for losslessness checks."""

        return {
            field.name: field.value
            for field in (
                *self.receipt_v2_fields,
                *self.run_plan_fields,
                *self.observation_fields,
            )
        }


def partition_legacy_draft_manifest(
    document: object,
) -> LegacyDraftRunManifestPartitionV1:
    """Assign every supported draft field to its successor artifact family.

    This deliberately rejects extension fields instead of dropping them.  It does
    not invent the provenance, digests, coverage rows, stimuli, or observations
    that the executable successor contracts require.
    """

    if not isinstance(document, dict) or any(
        not isinstance(key, str) for key in document
    ):
        raise LegacyDraftMigrationError("legacy run manifest must be a JSON object")
    unknown = sorted(set(document) - _KNOWN_FIELDS)
    if unknown:
        raise LegacyDraftMigrationError(
            "unsupported legacy run-manifest field(s): " + ", ".join(unknown)
        )
    missing = sorted(_REQUIRED_FIELDS - set(document))
    if missing:
        raise LegacyDraftMigrationError(
            "legacy run manifest is missing required field(s): " + ", ".join(missing)
        )
    if document["manifest_version"] != LEGACY_RUN_MANIFEST_VERSION:
        raise LegacyDraftMigrationError(
            f"unsupported legacy run-manifest version: {document['manifest_version']!r}"
        )

    def fields(names: tuple[str, ...]) -> tuple[LegacyDraftFieldV1, ...]:
        return tuple(
            LegacyDraftFieldV1(name=name, value=document[name])
            for name in names
            if name in document
        )

    return LegacyDraftRunManifestPartitionV1(
        receipt_v2_fields=fields(_RECEIPT_V2_FIELDS),
        run_plan_fields=fields(_RUN_PLAN_FIELDS),
        observation_fields=fields(_OBSERVATION_FIELDS),
    )


__all__ = [
    "LEGACY_RUN_MANIFEST_VERSION",
    "LegacyDraftFieldV1",
    "LegacyDraftMigrationError",
    "LegacyDraftRunManifestPartitionV1",
    "partition_legacy_draft_manifest",
]
