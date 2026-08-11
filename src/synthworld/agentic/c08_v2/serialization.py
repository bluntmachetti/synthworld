"""Canonical, separately manifested C08 v2 artifact serialization."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from synthworld.agentic.c08_v2.models import (
    C08_EVALUATOR_ARTIFACT,
    C08_MANIFEST_ARTIFACT,
    C08_PUBLIC_ARTIFACT,
    C08_SCHEMA_VERSION,
    C08_SUBMISSION_ARTIFACT,
    C08ArtifactDescriptorV2,
    C08ArtifactManifestV2,
    C08ArtifactVisibility,
    C08AsteriaBenchmarkV2,
    C08AsteriaEvaluatorV2,
    C08AsteriaPublicInputV2,
    C08AsteriaSubmissionV2,
    C08BenchmarkId,
)
from synthworld.enterprise.canonical import canonical_json_bytes


class C08ArtifactError(ValueError):
    """Raised when a C08 artifact set is malformed or internally inconsistent."""


def _artifact_set_digest(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        payload = files[path]
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()


def _manifest_bytes(
    *,
    visibility: C08ArtifactVisibility,
    benchmark_id: C08BenchmarkId,
    path: str,
    payload: bytes,
) -> bytes:
    manifest = C08ArtifactManifestV2(
        schema_version=C08_SCHEMA_VERSION,
        benchmark_id=benchmark_id,
        visibility=visibility,
        artifact_set_digest=_artifact_set_digest({path: payload}),
        artifacts=(
            C08ArtifactDescriptorV2(
                path=path,
                byte_size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            ),
        ),
    )
    return canonical_json_bytes(manifest)


type _C08ArtifactModel = (
    C08AsteriaPublicInputV2 | C08AsteriaEvaluatorV2 | C08AsteriaSubmissionV2
)


def _build_artifacts(
    *, visibility: C08ArtifactVisibility, path: str, model: _C08ArtifactModel
) -> dict[str, bytes]:
    payload = canonical_json_bytes(model)
    return {
        path: payload,
        C08_MANIFEST_ARTIFACT: _manifest_bytes(
            visibility=visibility,
            benchmark_id=model.benchmark_id,
            path=path,
            payload=payload,
        ),
    }


def build_c08_public_artifacts(
    public: C08AsteriaPublicInputV2,
) -> dict[str, bytes]:
    return _build_artifacts(visibility="public", path=C08_PUBLIC_ARTIFACT, model=public)


def build_c08_evaluator_artifacts(
    evaluator: C08AsteriaEvaluatorV2,
) -> dict[str, bytes]:
    return _build_artifacts(
        visibility="evaluator", path=C08_EVALUATOR_ARTIFACT, model=evaluator
    )


def build_c08_submission_artifacts(
    submission: C08AsteriaSubmissionV2,
) -> dict[str, bytes]:
    return _build_artifacts(
        visibility="submission", path=C08_SUBMISSION_ARTIFACT, model=submission
    )


def _read_canonical[ModelT: BaseModel](
    artifacts: Mapping[str, bytes], path: str, model: type[ModelT]
) -> ModelT:
    try:
        payload = artifacts[path]
        parsed = model.model_validate_json(payload)
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise C08ArtifactError(f"invalid C08 {path}") from error
    if payload != canonical_json_bytes(parsed):
        raise C08ArtifactError(f"noncanonical C08 {path}")
    return parsed


def _load_artifacts[ModelT: BaseModel](
    artifacts: Mapping[str, bytes],
    *,
    visibility: str,
    path: str,
    model: type[ModelT],
) -> ModelT:
    if set(artifacts) != {path, C08_MANIFEST_ARTIFACT}:
        raise C08ArtifactError("C08 artifact inventory differs")
    parsed = _read_canonical(artifacts, path, model)
    manifest = _read_canonical(artifacts, C08_MANIFEST_ARTIFACT, C08ArtifactManifestV2)
    payload = artifacts[path]
    if (
        manifest.visibility != visibility
        or manifest.benchmark_id != parsed.model_dump(mode="json")["benchmark_id"]
        or manifest.artifact_set_digest != _artifact_set_digest({path: payload})
        or len(manifest.artifacts) != 1
        or manifest.artifacts[0].path != path
        or manifest.artifacts[0].byte_size != len(payload)
        or manifest.artifacts[0].sha256 != hashlib.sha256(payload).hexdigest()
    ):
        raise C08ArtifactError("C08 manifest binding differs")
    return parsed


def load_c08_public_artifacts(
    artifacts: Mapping[str, bytes],
) -> C08AsteriaPublicInputV2:
    return _load_artifacts(
        artifacts,
        visibility="public",
        path=C08_PUBLIC_ARTIFACT,
        model=C08AsteriaPublicInputV2,
    )


def load_c08_evaluator_artifacts(
    artifacts: Mapping[str, bytes],
) -> C08AsteriaEvaluatorV2:
    return _load_artifacts(
        artifacts,
        visibility="evaluator",
        path=C08_EVALUATOR_ARTIFACT,
        model=C08AsteriaEvaluatorV2,
    )


def load_c08_submission_artifacts(
    artifacts: Mapping[str, bytes],
    *,
    public: C08AsteriaPublicInputV2 | None = None,
) -> C08AsteriaSubmissionV2:
    submission = _load_artifacts(
        artifacts,
        visibility="submission",
        path=C08_SUBMISSION_ARTIFACT,
        model=C08AsteriaSubmissionV2,
    )
    if public is not None:
        public_digest = hashlib.sha256(canonical_json_bytes(public)).hexdigest()
        if submission.public_input_digest != public_digest:
            raise C08ArtifactError("C08 submission/public digest binding differs")
    return submission


def load_c08_bundle(
    public_artifacts: Mapping[str, bytes],
    evaluator_artifacts: Mapping[str, bytes],
    submission_artifacts: Mapping[str, bytes] | None = None,
) -> C08AsteriaBenchmarkV2:
    """Load both trees and cross-bind evaluator truth to public bytes."""

    public = load_c08_public_artifacts(public_artifacts)
    evaluator = load_c08_evaluator_artifacts(evaluator_artifacts)
    public_digest = hashlib.sha256(canonical_json_bytes(public)).hexdigest()
    if evaluator.public_input_digest != public_digest:
        raise C08ArtifactError("C08 evaluator/public digest binding differs")
    if submission_artifacts is not None:
        load_c08_submission_artifacts(submission_artifacts, public=public)
    return C08AsteriaBenchmarkV2(public=public, evaluator=evaluator)


__all__ = [
    "C08ArtifactError",
    "build_c08_evaluator_artifacts",
    "build_c08_public_artifacts",
    "build_c08_submission_artifacts",
    "load_c08_bundle",
    "load_c08_evaluator_artifacts",
    "load_c08_public_artifacts",
    "load_c08_submission_artifacts",
]
