"""Canonical public/evaluator artifacts for generated enterprise-agentic worlds."""

from __future__ import annotations

import hashlib
from pathlib import Path

from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticArtifactDescriptorV1,
    EnterpriseAgenticGeneratedBenchmarkV1,
    EnterpriseAgenticGeneratedEvaluatorManifestV1,
    EnterpriseAgenticGeneratedEvaluatorV1,
    EnterpriseAgenticGeneratedPublicManifestV1,
    EnterpriseAgenticGeneratedPublicV1,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
)

_PUBLIC_INPUT_PATH = "public-input.json"
_PUBLIC_SCENARIO_PATH = "scenarios/enterprise-agentic-smoke-v1.json"
_PUBLIC_TOOL_SCHEMA_PATH = "tool_schemas/enterprise-agentic-actions-v1.json"
_EVALUATOR_TRUTH_PATH = "truth.json"


def generated_enterprise_agentic_public_artifacts(
    generated: EnterpriseAgenticGeneratedBenchmarkV1,
) -> dict[str, bytes]:
    """Return an oracle-free, self-checksummed public artifact tree."""

    public = EnterpriseAgenticGeneratedPublicV1(
        config=generated.config,
        identity=generated.identity,
        benchmark=generated.public,
    )
    artifacts = {
        _PUBLIC_INPUT_PATH: canonical_json_bytes(public),
        _PUBLIC_SCENARIO_PATH: canonical_json_bytes(generated.public.scenario),
        _PUBLIC_TOOL_SCHEMA_PATH: canonical_json_value_bytes(_tool_schema()),
    }
    manifest = EnterpriseAgenticGeneratedPublicManifestV1(
        artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(artifacts),
        artifacts=_descriptors(artifacts),
    )
    return {"manifest.json": canonical_json_bytes(manifest), **artifacts}


def generated_enterprise_agentic_evaluator_artifacts(
    generated: EnterpriseAgenticGeneratedBenchmarkV1,
) -> dict[str, bytes]:
    """Return evaluator truth cross-bound to the complete public artifact set."""

    public = generated_enterprise_agentic_public_artifacts(generated)
    public_digest = generated_enterprise_agentic_artifact_set_sha256(public)
    evaluator = EnterpriseAgenticGeneratedEvaluatorV1(
        identity=generated.identity,
        public_artifact_set_sha256=public_digest,
        benchmark=generated.evaluator,
        metrics=generated.metrics,
    )
    artifacts = {_EVALUATOR_TRUTH_PATH: canonical_json_bytes(evaluator)}
    manifest = EnterpriseAgenticGeneratedEvaluatorManifestV1(
        artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(artifacts),
        public_artifact_set_sha256=public_digest,
        artifacts=_descriptors(artifacts),
    )
    return {**artifacts, "manifest.json": canonical_json_bytes(manifest)}


def generated_enterprise_agentic_artifact_checksums(
    generated: EnterpriseAgenticGeneratedBenchmarkV1,
) -> tuple[tuple[str, str], ...]:
    """Return path-and-byte-bound digests for evaluation receipts."""

    public = generated_enterprise_agentic_public_artifacts(generated)
    evaluator = generated_enterprise_agentic_evaluator_artifacts(generated)
    return (
        (
            "public",
            generated_enterprise_agentic_artifact_set_sha256(public),
        ),
        (
            "evaluator",
            generated_enterprise_agentic_artifact_set_sha256(
                {
                    path: value
                    for path, value in evaluator.items()
                    if path != "manifest.json"
                }
            ),
        ),
    )


def export_generated_enterprise_agentic_benchmark(
    root: Path,
    generated: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    """Write new, physically separate public and evaluator trees."""

    if root.exists():
        raise FileExistsError("generated enterprise-agentic output already exists")
    for visibility, artifacts in (
        ("public", generated_enterprise_agentic_public_artifacts(generated)),
        ("evaluator", generated_enterprise_agentic_evaluator_artifacts(generated)),
    ):
        for relative_path, payload in artifacts.items():
            target = root / visibility / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)


def generated_enterprise_agentic_artifact_set_sha256(
    artifacts: dict[str, bytes],
) -> str:
    """Bind every canonical relative path and its exact bytes."""

    digest = hashlib.sha256()
    for path, payload in sorted(artifacts.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()


def _descriptors(
    artifacts: dict[str, bytes],
) -> tuple[EnterpriseAgenticArtifactDescriptorV1, ...]:
    return tuple(
        EnterpriseAgenticArtifactDescriptorV1(
            path=path,
            byte_size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        for path, payload in sorted(artifacts.items())
    )


def _tool_schema() -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://synthworld.example/schemas/enterprise-agentic-actions-v1.json",
        "title": "Synthetic enterprise agent action",
        "type": "object",
        "additionalProperties": False,
        "required": ["resource_id", "action", "requested_scope"],
        "properties": {
            "resource_id": {"type": "string"},
            "action": {"enum": ["read", "write"]},
            "requested_scope": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "uniqueItems": True,
            },
        },
    }


__all__ = [
    "export_generated_enterprise_agentic_benchmark",
    "generated_enterprise_agentic_artifact_checksums",
    "generated_enterprise_agentic_artifact_set_sha256",
    "generated_enterprise_agentic_evaluator_artifacts",
    "generated_enterprise_agentic_public_artifacts",
]
