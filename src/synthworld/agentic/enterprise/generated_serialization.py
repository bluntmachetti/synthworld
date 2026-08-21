"""Canonical public/evaluator artifacts for generated enterprise-agentic worlds."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

from pydantic import BaseModel, ValidationError

from synthworld.agentic.enterprise.errors import EnterpriseAgenticArtifactError
from synthworld.agentic.enterprise.generated import (
    derive_enterprise_agentic_integrity_metrics,
    generate_enterprise_agentic_world,
)
from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticArtifactDescriptorV1,
    EnterpriseAgenticGeneratedBenchmarkV1,
    EnterpriseAgenticGeneratedEvaluatorManifestV1,
    EnterpriseAgenticGeneratedEvaluatorV1,
    EnterpriseAgenticGeneratedPublicManifestV1,
    EnterpriseAgenticGeneratedPublicV1,
)
from synthworld.agentic.errors import AgenticReplayError
from synthworld.agentic.models import AgenticBenchmark, PublicScenario
from synthworld.agentic.projection import build_agentic_benchmark
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
)

_PUBLIC_INPUT_PATH = "public-input.json"
_PUBLIC_SCENARIO_PATH = "scenarios/enterprise-agentic-smoke-v1.json"
_PUBLIC_TOOL_SCHEMA_PATH = "tool_schemas/enterprise-agentic-actions-v1.json"
_EVALUATOR_TRUTH_PATH = "truth.json"
_MANIFEST_PATH = "manifest.json"
_PUBLIC_BASE_PATHS = {
    _PUBLIC_INPUT_PATH,
    _PUBLIC_SCENARIO_PATH,
    _PUBLIC_TOOL_SCHEMA_PATH,
}
_PUBLIC_TREE_PATHS = {_MANIFEST_PATH, *_PUBLIC_BASE_PATHS}
_EVALUATOR_BASE_PATHS = {_EVALUATOR_TRUTH_PATH}
_EVALUATOR_TREE_PATHS = {_MANIFEST_PATH, *_EVALUATOR_BASE_PATHS}


def _public_tree_artifacts(
    public: EnterpriseAgenticGeneratedPublicV1,
) -> dict[str, bytes]:
    artifacts = {
        _PUBLIC_INPUT_PATH: canonical_json_bytes(public),
        _PUBLIC_SCENARIO_PATH: canonical_json_bytes(public.benchmark.scenario),
        _PUBLIC_TOOL_SCHEMA_PATH: canonical_json_value_bytes(_tool_schema()),
    }
    manifest = EnterpriseAgenticGeneratedPublicManifestV1(
        artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(artifacts),
        artifacts=_descriptors(artifacts),
    )
    return {"manifest.json": canonical_json_bytes(manifest), **artifacts}


def generated_enterprise_agentic_public_artifact_set_sha256(
    public: EnterpriseAgenticGeneratedPublicV1,
) -> str:
    """Return the complete public-tree digest, including its manifest.

    This is the digest the evaluator manifest, evaluator truth artifact, and
    evaluation receipts use as ``public_artifact_set_sha256``, so a projection
    recording it can be correlated with every published cross-binding.
    """

    return generated_enterprise_agentic_artifact_set_sha256(
        _public_tree_artifacts(public)
    )


def generated_enterprise_agentic_public_artifacts(
    generated: EnterpriseAgenticGeneratedBenchmarkV1,
) -> dict[str, bytes]:
    """Return an oracle-free, self-checksummed public artifact tree."""

    return _public_tree_artifacts(
        EnterpriseAgenticGeneratedPublicV1(
            config=generated.config,
            identity=generated.identity,
            benchmark=generated.public,
        )
    )


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


def load_public_generated_enterprise_agentic_benchmark(
    root: Path,
) -> EnterpriseAgenticGeneratedPublicV1:
    """Load only the public tree and verify its self-contained contract.

    This function deliberately never lists, opens, or otherwise traverses the
    evaluator tree. Its checks establish public-tree consistency, not provenance;
    deterministic generator conformance is enforced by the complete loader.
    """

    return load_generated_enterprise_agentic_public_tree(root / "public")


def load_generated_enterprise_agentic_public_tree(
    public_tree: Path,
) -> EnterpriseAgenticGeneratedPublicV1:
    """Load one public tree directly, with the same public-only guarantees."""

    return _load_public_artifacts(_read_exact_tree(public_tree, _PUBLIC_TREE_PATHS))


def _load_public_artifacts(
    public_artifacts: dict[str, bytes],
) -> EnterpriseAgenticGeneratedPublicV1:
    base_artifacts = {
        path: public_artifacts[path] for path in sorted(_PUBLIC_BASE_PATHS)
    }
    manifest = _read_canonical_model(
        public_artifacts[_MANIFEST_PATH],
        EnterpriseAgenticGeneratedPublicManifestV1,
    )
    expected_manifest = EnterpriseAgenticGeneratedPublicManifestV1(
        artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(
            base_artifacts
        ),
        artifacts=_descriptors(base_artifacts),
    )
    if manifest != expected_manifest:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic public manifest differs"
        )

    public = _read_canonical_model(
        public_artifacts[_PUBLIC_INPUT_PATH], EnterpriseAgenticGeneratedPublicV1
    )
    scenario = _read_canonical_model(
        public_artifacts[_PUBLIC_SCENARIO_PATH], PublicScenario
    )
    if scenario != public.benchmark.scenario:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic public scenario differs"
        )
    tool_schema = _read_canonical_json_value(public_artifacts[_PUBLIC_TOOL_SCHEMA_PATH])
    if tool_schema != _tool_schema():
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic tool schema differs"
        )
    return public


def load_generated_enterprise_agentic_benchmark(
    root: Path,
) -> EnterpriseAgenticGeneratedBenchmarkV1:
    """Load a complete generated tree and prove its declared generator origin."""

    _require_exact_entries(
        root,
        expected_files=set(),
        expected_directories={"public", "evaluator"},
    )
    return load_generated_enterprise_agentic_trees(
        public_tree=root / "public",
        evaluator_tree=root / "evaluator",
    )


def load_generated_enterprise_agentic_trees(
    *,
    public_tree: Path,
    evaluator_tree: Path,
) -> EnterpriseAgenticGeneratedBenchmarkV1:
    """Load explicit public and evaluator trees with full generator conformance."""

    public_artifacts = _read_exact_tree(public_tree, _PUBLIC_TREE_PATHS)
    public = _load_public_artifacts(public_artifacts)
    evaluator_artifacts = _read_exact_tree(evaluator_tree, _EVALUATOR_TREE_PATHS)
    evaluator_base = {
        path: evaluator_artifacts[path] for path in sorted(_EVALUATOR_BASE_PATHS)
    }
    public_digest = generated_enterprise_agentic_artifact_set_sha256(public_artifacts)
    evaluator_manifest = _read_canonical_model(
        evaluator_artifacts[_MANIFEST_PATH],
        EnterpriseAgenticGeneratedEvaluatorManifestV1,
    )
    expected_evaluator_manifest = EnterpriseAgenticGeneratedEvaluatorManifestV1(
        artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(
            evaluator_base
        ),
        public_artifact_set_sha256=public_digest,
        artifacts=_descriptors(evaluator_base),
    )
    if evaluator_manifest != expected_evaluator_manifest:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic evaluator manifest differs"
        )

    evaluator = _read_canonical_model(
        evaluator_artifacts[_EVALUATOR_TRUTH_PATH],
        EnterpriseAgenticGeneratedEvaluatorV1,
    )
    if evaluator.public_artifact_set_sha256 != public_digest:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic evaluator public binding differs"
        )
    if evaluator.identity != public.identity:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic public/evaluator identity differs"
        )
    try:
        generated = EnterpriseAgenticGeneratedBenchmarkV1(
            config=public.config,
            identity=public.identity,
            public=public.benchmark,
            evaluator=evaluator.benchmark,
            metrics=evaluator.metrics,
        )
        validated_benchmark = build_agentic_benchmark(
            generated.public.snapshot,
            generated.public.events,
            generated.public.scenario,
            generated.evaluator.bindings,
            generated.evaluator.cases,
        )
    except (AgenticReplayError, ValidationError) as error:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic public/evaluator bindings are invalid"
        ) from error
    benchmark = AgenticBenchmark(
        public=generated.public,
        evaluator=generated.evaluator,
    )
    if validated_benchmark != benchmark:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic public/evaluator bindings differ"
        )
    if derive_enterprise_agentic_integrity_metrics(benchmark) != generated.metrics:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic integrity metrics differ"
        )

    expected = generate_enterprise_agentic_world(public.config)
    if public_artifacts != generated_enterprise_agentic_public_artifacts(
        expected
    ) or evaluator_artifacts != generated_enterprise_agentic_evaluator_artifacts(
        expected
    ):
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifacts differ from declared generation"
        )
    return generated


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


def _read_canonical_model[ModelT: BaseModel](
    payload: bytes, model: type[ModelT]
) -> ModelT:
    try:
        parsed = model.model_validate_json(payload)
    except (ValueError, ValidationError) as error:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifact is invalid"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifact is not canonical JSON"
        )
    return parsed


def _read_canonical_json_value(payload: bytes) -> object:
    try:
        parsed = json.loads(payload)
        canonical = canonical_json_value_bytes(parsed)
    except (UnicodeDecodeError, ValueError) as error:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifact is invalid"
        ) from error
    if payload != canonical:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifact is not canonical JSON"
        )
    return parsed


def _read_exact_tree(directory: Path, expected_files: set[str]) -> dict[str, bytes]:
    expected_directories = {
        parent.as_posix()
        for path in expected_files
        for parent in Path(path).parents
        if parent != Path(".")
    }
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    _collect_tree(directory, directory, actual_files, actual_directories)
    if actual_files != expected_files or actual_directories != expected_directories:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifact inventory differs"
        )
    try:
        return {
            path: (directory / path).read_bytes() for path in sorted(expected_files)
        }
    except OSError as error:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifact tree is unreadable"
        ) from error


def _collect_tree(
    root: Path,
    directory: Path,
    files: set[str],
    directories: set[str],
) -> None:
    try:
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise EnterpriseAgenticArtifactError(
                "generated enterprise-agentic artifact directory is not real"
            )
        entries = tuple(directory.iterdir())
        for entry in entries:
            relative = entry.relative_to(root).as_posix()
            entry_status = entry.lstat()
            if stat.S_ISREG(entry_status.st_mode):
                files.add(relative)
            elif stat.S_ISDIR(entry_status.st_mode):
                directories.add(relative)
                _collect_tree(root, entry, files, directories)
            else:
                raise EnterpriseAgenticArtifactError(
                    "generated enterprise-agentic artifact tree contains "
                    "a non-regular entry"
                )
    except OSError as error:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifact tree is unreadable"
        ) from error


def _require_exact_entries(
    directory: Path,
    *,
    expected_files: set[str],
    expected_directories: set[str],
) -> None:
    try:
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise EnterpriseAgenticArtifactError(
                "generated enterprise-agentic artifact root is not a real directory"
            )
        files: set[str] = set()
        directories: set[str] = set()
        for entry in directory.iterdir():
            entry_status = entry.lstat()
            if stat.S_ISREG(entry_status.st_mode):
                files.add(entry.name)
            elif stat.S_ISDIR(entry_status.st_mode):
                directories.add(entry.name)
            else:
                raise EnterpriseAgenticArtifactError(
                    "generated enterprise-agentic artifact root contains "
                    "a non-regular entry"
                )
    except OSError as error:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifact root is unreadable"
        ) from error
    if files != expected_files or directories != expected_directories:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic artifact root inventory differs"
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
    "generated_enterprise_agentic_public_artifact_set_sha256",
    "generated_enterprise_agentic_public_artifacts",
    "load_generated_enterprise_agentic_benchmark",
    "load_generated_enterprise_agentic_public_tree",
    "load_generated_enterprise_agentic_trees",
    "load_public_generated_enterprise_agentic_benchmark",
]
