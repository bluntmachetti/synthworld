"""Versions, limits, and stable identifiers for contextual-access v1."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid5

from synthworld.enterprise.canonical import encode_parts

CONTEXTUAL_ACCESS_CONFIG_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
CONTEXTUAL_ACCESS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
CONTEXTUAL_ACCESS_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"
CONTEXTUAL_ACCESS_PROFILE_VERSION: Literal["contextual-access-smoke-1.0.0"] = (
    "contextual-access-smoke-1.0.0"
)
CONTEXTUAL_ACCESS_EVENT_SCHEDULE_VERSION: Literal[
    "contextual-access-schedule-1.0.0"
] = "contextual-access-schedule-1.0.0"
CONTEXTUAL_ACCESS_PROTOCOL_VERSION: Literal["synthworld-contextual-access-1.0.0"] = (
    "synthworld-contextual-access-1.0.0"
)
CONTEXTUAL_ACCESS_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"

_CONTEXTUAL_PROFILE_NAMESPACE_V1 = UUID("ad9ad595-0e77-52a5-880d-e231773d9474")
_CONTEXTUAL_KIND_NAMESPACE_V1 = UUID("19b0a348-c965-5c8a-bbce-a645fa5efec5")
_CONTEXTUAL_FACT_KEY_NAMESPACE_V1 = UUID("619ca604-bad4-5a1f-8c52-d71266dce888")


def contextual_profile_namespace(*, universe_sha256: str, seed: int) -> UUID:
    """Bind generated IDs to profile, selected universe, and explicit seed."""

    return uuid5(
        _CONTEXTUAL_PROFILE_NAMESPACE_V1,
        encode_parts((CONTEXTUAL_ACCESS_PROFILE_VERSION, universe_sha256, str(seed))),
    )


def stable_contextual_id(
    profile_namespace: UUID,
    kind: str,
    *components: str,
) -> str:
    """Derive a kind-separated ID that is independent of tuple position."""

    kind_namespace = uuid5(_CONTEXTUAL_KIND_NAMESPACE_V1, kind)
    return str(
        uuid5(
            kind_namespace,
            encode_parts((str(profile_namespace), *components)),
        )
    )


def stable_contextual_fact_key(kind: str, *components: str) -> str:
    """Derive the exact canonical key for one contextual fact identity."""

    return str(
        uuid5(
            _CONTEXTUAL_FACT_KEY_NAMESPACE_V1,
            encode_parts((CONTEXTUAL_ACCESS_PROFILE_VERSION, kind, *components)),
        )
    )


__all__ = [name for name in globals() if not name.startswith("_")]
