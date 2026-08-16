"""Public canonical serialization and digest helpers for enterprise artifacts."""

from __future__ import annotations

from pydantic import BaseModel

from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
    synthetic_digest,
)
from synthworld.enterprise.models import SyntheticDigestV1


def build_enterprise_model[ModelT: BaseModel](
    model_type: type[ModelT], data: object
) -> ModelT:
    """Build a strict enterprise model from ordinary JSON-shaped Python data."""

    return model_type.model_validate_json(canonical_json_value_bytes(data))


def canonical_enterprise_model_bytes(model: BaseModel) -> bytes:
    """Serialize a model exactly as enterprise exporters and evaluators do."""

    return canonical_json_bytes(model)


def digest_enterprise_model(model: BaseModel) -> SyntheticDigestV1:
    """Return the canonical SHA-256 binding used by enterprise contracts."""

    return synthetic_digest(canonical_enterprise_model_bytes(model))


def digest_enterprise_artifact(payload: bytes) -> SyntheticDigestV1:
    """Digest already-serialized artifact bytes without rewriting them."""

    return synthetic_digest(payload)


__all__ = [
    "build_enterprise_model",
    "canonical_enterprise_model_bytes",
    "digest_enterprise_artifact",
    "digest_enterprise_model",
]
