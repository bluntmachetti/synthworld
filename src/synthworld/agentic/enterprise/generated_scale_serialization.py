"""Canonical V2 artifacts for enterprise-agentic scale worlds."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from synthworld.agentic.enterprise.errors import EnterpriseAgenticArtifactError
from synthworld.agentic.enterprise.generated_scale import (
    derive_enterprise_agentic_scale_integrity_metrics,
    generate_enterprise_agentic_scale_world,
)
from synthworld.agentic.enterprise.generated_scale_models import (
    EnterpriseAgenticGeneratedBenchmarkV2,
    EnterpriseAgenticGeneratedEvaluatorManifestV2,
    EnterpriseAgenticGeneratedEvaluatorV2,
    EnterpriseAgenticGeneratedPublicManifestV2,
    EnterpriseAgenticGeneratedPublicV2,
    EnterpriseAgenticLifecycleStreamV2,
    EnterpriseAgenticTopologyMetadataV2,
)
from synthworld.agentic.enterprise.generated_serialization import (
    _descriptors,
    _read_canonical_json_value,
    _read_canonical_model,
    _read_exact_tree,
    _require_exact_entries,
    _tool_schema,
    generated_enterprise_agentic_artifact_set_sha256,
)
from synthworld.agentic.errors import AgenticReplayError
from synthworld.agentic.models import AgenticBenchmark, PublicScenario
from synthworld.agentic.projection import build_agentic_benchmark
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
)

_PUBLIC_INPUT_PATH = "public-input.json"
_PUBLIC_SCENARIO_PATH = "scenarios/enterprise-agentic-scale-v2.json"
_PUBLIC_TOOL_SCHEMA_PATH = "tool_schemas/enterprise-agentic-actions-v1.json"
_PUBLIC_TOPOLOGY_PATH = "topology.json"
_PUBLIC_LIFECYCLE_PATH = "lifecycle-events.json"
_EVALUATOR_TRUTH_PATH = "truth.json"
_MANIFEST_PATH = "manifest.json"
_PUBLIC_BASE_PATHS = {
    _PUBLIC_INPUT_PATH,
    _PUBLIC_SCENARIO_PATH,
    _PUBLIC_TOOL_SCHEMA_PATH,
    _PUBLIC_TOPOLOGY_PATH,
    _PUBLIC_LIFECYCLE_PATH,
}
_PUBLIC_TREE_PATHS = {_MANIFEST_PATH, *_PUBLIC_BASE_PATHS}
_EVALUATOR_BASE_PATHS = {_EVALUATOR_TRUTH_PATH}
_EVALUATOR_TREE_PATHS = {_MANIFEST_PATH, *_EVALUATOR_BASE_PATHS}


def _public_tree_artifacts(
    public: EnterpriseAgenticGeneratedPublicV2,
) -> dict[str, bytes]:
    artifacts = {
        _PUBLIC_INPUT_PATH: canonical_json_bytes(public),
        _PUBLIC_SCENARIO_PATH: canonical_json_bytes(public.benchmark.scenario),
        _PUBLIC_TOOL_SCHEMA_PATH: canonical_json_value_bytes(_tool_schema()),
        _PUBLIC_TOPOLOGY_PATH: canonical_json_bytes(public.topology),
        _PUBLIC_LIFECYCLE_PATH: canonical_json_bytes(
            EnterpriseAgenticLifecycleStreamV2(events=public.lifecycle_events)
        ),
    }
    manifest = EnterpriseAgenticGeneratedPublicManifestV2(
        artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(artifacts),
        artifacts=_descriptors(artifacts),
    )
    return {_MANIFEST_PATH: canonical_json_bytes(manifest), **artifacts}


def generated_enterprise_agentic_scale_public_artifacts(
    generated: EnterpriseAgenticGeneratedBenchmarkV2,
) -> dict[str, bytes]:
    """Return the oracle-free V2 public artifact tree."""

    return _public_tree_artifacts(
        EnterpriseAgenticGeneratedPublicV2(
            config=generated.config,
            identity=generated.identity,
            benchmark=generated.public,
            topology=generated.topology,
            lifecycle_events=generated.lifecycle_events,
        )
    )


def generated_enterprise_agentic_scale_evaluator_artifacts(
    generated: EnterpriseAgenticGeneratedBenchmarkV2,
) -> dict[str, bytes]:
    """Return V2 evaluator truth cross-bound to the full public tree."""

    public = generated_enterprise_agentic_scale_public_artifacts(generated)
    public_digest = generated_enterprise_agentic_artifact_set_sha256(public)
    evaluator = EnterpriseAgenticGeneratedEvaluatorV2(
        identity=generated.identity,
        public_artifact_set_sha256=public_digest,
        benchmark=generated.evaluator,
        lifecycle_cases=generated.lifecycle_cases,
        metrics=generated.metrics,
    )
    artifacts = {_EVALUATOR_TRUTH_PATH: canonical_json_bytes(evaluator)}
    manifest = EnterpriseAgenticGeneratedEvaluatorManifestV2(
        artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(artifacts),
        public_artifact_set_sha256=public_digest,
        artifacts=_descriptors(artifacts),
    )
    return {**artifacts, _MANIFEST_PATH: canonical_json_bytes(manifest)}


def generated_enterprise_agentic_scale_artifact_checksums(
    generated: EnterpriseAgenticGeneratedBenchmarkV2,
) -> tuple[tuple[str, str], ...]:
    """Return exact V2 public/evaluator digests for scoring receipts."""

    public = generated_enterprise_agentic_scale_public_artifacts(generated)
    evaluator = generated_enterprise_agentic_scale_evaluator_artifacts(generated)
    return (
        ("public", generated_enterprise_agentic_artifact_set_sha256(public)),
        (
            "evaluator",
            generated_enterprise_agentic_artifact_set_sha256(
                {
                    path: payload
                    for path, payload in evaluator.items()
                    if path != _MANIFEST_PATH
                }
            ),
        ),
    )


def export_generated_enterprise_agentic_scale_benchmark(
    root: Path,
    generated: EnterpriseAgenticGeneratedBenchmarkV2,
) -> None:
    """Write new, physically separate V2 public and evaluator trees."""

    if root.exists():
        raise FileExistsError("generated enterprise-agentic output already exists")
    for visibility, artifacts in (
        ("public", generated_enterprise_agentic_scale_public_artifacts(generated)),
        (
            "evaluator",
            generated_enterprise_agentic_scale_evaluator_artifacts(generated),
        ),
    ):
        for relative_path, payload in artifacts.items():
            target = root / visibility / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)


def export_generated_enterprise_agentic_scale_public_benchmark(
    root: Path,
    generated: EnterpriseAgenticGeneratedBenchmarkV2,
) -> None:
    """Write only the V2 public tree without creating evaluator paths."""

    if root.exists():
        raise FileExistsError("generated enterprise-agentic output already exists")
    for relative_path, payload in generated_enterprise_agentic_scale_public_artifacts(
        generated
    ).items():
        target = root / "public" / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def load_public_generated_enterprise_agentic_scale_benchmark(
    root: Path,
) -> EnterpriseAgenticGeneratedPublicV2:
    """Load and verify only a V2 public tree."""

    return load_generated_enterprise_agentic_scale_public_tree(root / "public")


def load_generated_enterprise_agentic_scale_public_tree(
    public_tree: Path,
) -> EnterpriseAgenticGeneratedPublicV2:
    """Load one V2 public tree directly without touching evaluator truth."""

    return _load_public_artifacts(_read_exact_tree(public_tree, _PUBLIC_TREE_PATHS))


def _load_public_artifacts(
    public_artifacts: dict[str, bytes],
) -> EnterpriseAgenticGeneratedPublicV2:
    base = {path: public_artifacts[path] for path in sorted(_PUBLIC_BASE_PATHS)}
    manifest = _read_canonical_model(
        public_artifacts[_MANIFEST_PATH],
        EnterpriseAgenticGeneratedPublicManifestV2,
    )
    expected_manifest = EnterpriseAgenticGeneratedPublicManifestV2(
        artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(base),
        artifacts=_descriptors(base),
    )
    if manifest != expected_manifest:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 public manifest differs"
        )
    public = _read_canonical_model(
        public_artifacts[_PUBLIC_INPUT_PATH], EnterpriseAgenticGeneratedPublicV2
    )
    scenario = _read_canonical_model(
        public_artifacts[_PUBLIC_SCENARIO_PATH], PublicScenario
    )
    if scenario != public.benchmark.scenario:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 public scenario differs"
        )
    topology = _read_canonical_model(
        public_artifacts[_PUBLIC_TOPOLOGY_PATH], EnterpriseAgenticTopologyMetadataV2
    )
    if topology != public.topology:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 public topology differs"
        )
    lifecycle = _read_canonical_model(
        public_artifacts[_PUBLIC_LIFECYCLE_PATH],
        EnterpriseAgenticLifecycleStreamV2,
    )
    if lifecycle.events != public.lifecycle_events:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 lifecycle events differ"
        )
    if _read_canonical_json_value(public_artifacts[_PUBLIC_TOOL_SCHEMA_PATH]) != (
        _tool_schema()
    ):
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 tool schema differs"
        )
    return public


def load_generated_enterprise_agentic_scale_benchmark(
    root: Path,
) -> EnterpriseAgenticGeneratedBenchmarkV2:
    """Load a complete V2 tree and reproduce its declared generator output."""

    _require_exact_entries(
        root,
        expected_files=set(),
        expected_directories={"public", "evaluator"},
    )
    public_artifacts = _read_exact_tree(root / "public", _PUBLIC_TREE_PATHS)
    public = _load_public_artifacts(public_artifacts)
    evaluator_artifacts = _read_exact_tree(root / "evaluator", _EVALUATOR_TREE_PATHS)
    evaluator_base = {
        path: evaluator_artifacts[path] for path in sorted(_EVALUATOR_BASE_PATHS)
    }
    public_digest = generated_enterprise_agentic_artifact_set_sha256(public_artifacts)
    evaluator_manifest = _read_canonical_model(
        evaluator_artifacts[_MANIFEST_PATH],
        EnterpriseAgenticGeneratedEvaluatorManifestV2,
    )
    expected_manifest = EnterpriseAgenticGeneratedEvaluatorManifestV2(
        artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(
            evaluator_base
        ),
        public_artifact_set_sha256=public_digest,
        artifacts=_descriptors(evaluator_base),
    )
    if evaluator_manifest != expected_manifest:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 evaluator manifest differs"
        )
    evaluator = _read_canonical_model(
        evaluator_artifacts[_EVALUATOR_TRUTH_PATH],
        EnterpriseAgenticGeneratedEvaluatorV2,
    )
    if (
        evaluator.public_artifact_set_sha256 != public_digest
        or evaluator.identity != public.identity
    ):
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 public/evaluator binding differs"
        )
    try:
        generated = EnterpriseAgenticGeneratedBenchmarkV2(
            config=public.config,
            identity=public.identity,
            public=public.benchmark,
            topology=public.topology,
            lifecycle_events=public.lifecycle_events,
            evaluator=evaluator.benchmark,
            lifecycle_cases=evaluator.lifecycle_cases,
            metrics=evaluator.metrics,
        )
        rebuilt = build_agentic_benchmark(
            generated.public.snapshot,
            generated.public.events,
            generated.public.scenario,
            generated.evaluator.bindings,
            generated.evaluator.cases,
        )
    except (AgenticReplayError, ValidationError) as error:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 bindings are invalid"
        ) from error
    if rebuilt != AgenticBenchmark(
        public=generated.public, evaluator=generated.evaluator
    ):
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 evaluator truth differs"
        )
    if (
        derive_enterprise_agentic_scale_integrity_metrics(
            AgenticBenchmark(public=generated.public, evaluator=generated.evaluator),
            generated.topology,
            generated.lifecycle_events,
            generated.lifecycle_cases,
        )
        != generated.metrics
    ):
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 integrity metrics differ"
        )
    expected = generate_enterprise_agentic_scale_world(public.config)
    if public_artifacts != generated_enterprise_agentic_scale_public_artifacts(
        expected
    ) or evaluator_artifacts != generated_enterprise_agentic_scale_evaluator_artifacts(
        expected
    ):
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic V2 artifacts differ from declared generation"
        )
    return generated


__all__ = [
    "export_generated_enterprise_agentic_scale_benchmark",
    "export_generated_enterprise_agentic_scale_public_benchmark",
    "generated_enterprise_agentic_scale_artifact_checksums",
    "generated_enterprise_agentic_scale_evaluator_artifacts",
    "generated_enterprise_agentic_scale_public_artifacts",
    "load_generated_enterprise_agentic_scale_benchmark",
    "load_generated_enterprise_agentic_scale_public_tree",
    "load_public_generated_enterprise_agentic_scale_benchmark",
]
