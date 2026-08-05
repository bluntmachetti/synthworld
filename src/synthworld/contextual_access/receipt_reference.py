"""Deterministic contextual receipt fixture; never evidence of a live control."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from synthworld.assurance.contextual_access import (
    ContextualAccessPreExecutionArtifactsV1,
    ContextualAccessRunMetadataV1,
    build_contextual_access_run_receipt,
)
from synthworld.assurance.models import TreeState
from synthworld.assurance.models_v2 import (
    AdapterProvenanceV2,
    BenchmarkIdentityV2,
    BuildEnvironmentV2,
    DigestV2,
    EvidenceClaimV2,
    RepositoryProvenanceV2,
    RunMetadataV2,
    RunReceiptManifestV2,
)
from synthworld.assurance.receipt import canonical_json_bytes
from synthworld.contextual_access.models import ContextualAccessPublicV1
from synthworld.contextual_access.protocol import (
    ContextualAccessObservationsV1,
    ContextualAccessRunPlanV1,
)
from synthworld.contextual_access.protocol_reference import (
    ReferenceContextualRunV1,
    reference_contextual_access_run,
)
from synthworld.enterprise.canonical import synthetic_digest


def reference_contextual_receipt_metadata(
    run: ReferenceContextualRunV1 | None = None,
) -> ContextualAccessRunMetadataV1:
    """Return fixed operator/provenance inputs for the fake receipt fixture."""

    selected = run or reference_contextual_access_run()
    plan = selected.plan
    public = selected.benchmark.public
    evaluator = selected.benchmark.evaluator
    return ContextualAccessRunMetadataV1(
        callable_identifier=(
            "synthworld.contextual_access.receipt_reference.fake_product"
        ),
        source_public_schema_version=public.schema_version,
        product_output_schema_version=selected.observations.schema_version,
        benchmark=BenchmarkIdentityV2(
            family=plan.benchmark.benchmark_family,
            version=plan.benchmark.benchmark_version,
            package_version="0.12.0",
            public_root_digest=plan.benchmark.contextual_public_root_digest,
            evaluator_root_digest=_digest_model(evaluator),
            identity_access_universe_digest=(
                plan.benchmark.identity_access_universe_digest
            ),
            policy_digest=DigestV2(value=public.benchmark.policy_digest.value),
            cell_digest=plan.benchmark.request_digest,
        ),
        build_environment=BuildEnvironmentV2(
            synthworld=RepositoryProvenanceV2(
                name="SynthWorld",
                revision="contextual-reference-revision",
                tree_state=TreeState.CLEAN,
            ),
            dependency_lock_digest=_label_digest("contextual-reference-lock"),
            runtime_identifier="cpython-3.13-reference",
            platform_identifier="platform-independent-fixture",
        ),
        run=RunMetadataV2(
            run_id=plan.run_id,
            operator_id="synthworld-contextual-reference-fixture",
            started_at=datetime(2026, 8, 4, 9, 0, tzinfo=UTC),
            completed_at=datetime(2026, 8, 4, 9, 1, tzinfo=UTC),
        ),
        adapter=AdapterProvenanceV2(
            name="synthworld-reference-contextual-adapter",
            version="1.0.0",
            source_digest=_label_digest("contextual-reference-adapter"),
            boundary="canonical contextual public identity adaptation",
        ),
        systems_under_test=selected.systems_under_test,
        evidence_claim=EvidenceClaimV2.GENERATED_TRANSFER_EVIDENCE,
    )


def build_reference_contextual_access_run_receipt(
    root: Path,
) -> RunReceiptManifestV2:
    """Exercise preflight, staging, every probe family, faults, and scoring."""

    run = reference_contextual_access_run()
    observations = run.observations

    def runner(_input_path: Path, output_path: Path) -> int:
        output_path.write_bytes(canonical_json_bytes(observations))
        return 0

    return build_contextual_access_run_receipt(
        root,
        pre_execution_artifacts=ContextualAccessPreExecutionArtifactsV1(
            run_plan=run.plan,
            public=run.benchmark.public,
        ),
        source_public=canonical_json_bytes(run.benchmark.public),
        adapter=lambda payload: payload,
        runner=runner,
        observation_normalizer=_normalize_reference_output,
        truth_loader=lambda: run.benchmark.evaluator,
        metadata=reference_contextual_receipt_metadata(run),
    )


def _normalize_reference_output(
    payload: bytes,
    _plan: ContextualAccessRunPlanV1,
    _public: ContextualAccessPublicV1,
) -> ContextualAccessObservationsV1:
    return ContextualAccessObservationsV1.model_validate_json(payload)


def _digest_model(model: BaseModel) -> DigestV2:
    return DigestV2(value=synthetic_digest(canonical_json_bytes(model)).value)


def _label_digest(value: str) -> DigestV2:
    return DigestV2(value=synthetic_digest(value.encode("utf-8")).value)


__all__ = [
    "build_reference_contextual_access_run_receipt",
    "reference_contextual_receipt_metadata",
]
