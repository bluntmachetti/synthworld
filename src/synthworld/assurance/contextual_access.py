"""Receipt-v2 staging and replay for contextual-access external runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from synthworld.assurance.models import (
    ArtifactPhase,
    ArtifactSerialization,
    EvaluationStatus,
    ExecutionStatus,
)
from synthworld.assurance.models_v2 import (
    EXECUTION_RECEIPT_SCHEMA_VERSION_V2,
    RUN_RECEIPT_SCHEMA_VERSION_V2,
    AdapterProvenanceV2,
    BenchmarkIdentityV2,
    BuildEnvironmentV2,
    ConfigurationEntryV2,
    DigestV2,
    EvidenceClaimV2,
    ExecutionReceiptV2,
    RunMetadataV2,
    RunReceiptManifestV2,
    SystemComponentProvenanceV2,
    VersionBindingV2,
)
from synthworld.assurance.receipt import (
    EXECUTION_PATH,
    PRODUCT_INPUT_PATH,
    PRODUCT_OUTPUT_PATH,
    SOURCE_PUBLIC_PATH,
    ProductRunner,
    ProductStageError,
    PublicAdapter,
    ReceiptIntegrityError,
    canonical_json_bytes,
    write_canonical_model,
)
from synthworld.assurance.receipt_v2 import (
    ArtifactSpecV2,
    describe_artifact_v2,
    digest_bytes_v2,
    parse_execution_receipt,
    validate_manifest_v2,
    write_manifest_last_v2,
)
from synthworld.contextual_access.models import (
    ContextualAccessEvaluatorV1,
    ContextualAccessPublicV1,
)
from synthworld.contextual_access.protocol import (
    CONTEXTUAL_OBSERVATIONS_PATH,
    CONTEXTUAL_OBSERVATIONS_SCHEMA_VERSION,
    CONTEXTUAL_REPORT_PATH,
    CONTEXTUAL_REPORT_SCHEMA_VERSION,
    CONTEXTUAL_RUN_PLAN_PATH,
    CONTEXTUAL_RUN_PLAN_SCHEMA_VERSION,
    CONTEXTUAL_RUN_TRUTH_PATH,
    CONTEXTUAL_RUN_TRUTH_SCHEMA_VERSION,
    ContextualAccessObservationsV1,
    ContextualAccessReportV1,
    ContextualAccessRunPlanV1,
    ContextualAccessRunTruthV1,
    ContextualProtocolError,
    compile_contextual_run_truth,
    evaluate_contextual_access_run,
    validate_contextual_observations,
    validate_contextual_run_plan,
)
from synthworld.enterprise.models import EnterpriseOperatorModel

CONTEXTUAL_PRODUCT_INPUT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
CONTEXTUAL_RUN_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"

_ROLE_PATHS = {
    "contextual_access_run_plan": CONTEXTUAL_RUN_PLAN_PATH,
    "source_public": SOURCE_PUBLIC_PATH,
    "product_input": PRODUCT_INPUT_PATH,
    "product_output": PRODUCT_OUTPUT_PATH,
    "execution": EXECUTION_PATH,
    "contextual_access_observations": CONTEXTUAL_OBSERVATIONS_PATH,
    "contextual_access_run_truth": CONTEXTUAL_RUN_TRUTH_PATH,
    "contextual_access_evaluation": CONTEXTUAL_REPORT_PATH,
}

ContextualObservationNormalizer = Callable[
    [bytes, ContextualAccessRunPlanV1, ContextualAccessPublicV1],
    ContextualAccessObservationsV1,
]
ContextualTruthLoader = Callable[[], ContextualAccessEvaluatorV1]


class ContextualAccessProductInputV1(EnterpriseOperatorModel):
    """Exact contextual adapter-facing envelope staged before execution."""

    schema_version: Literal["1.0.0"] = CONTEXTUAL_PRODUCT_INPUT_SCHEMA_VERSION
    run_plan_digest: DigestV2
    contextual_public_digest: DigestV2
    public: ContextualAccessPublicV1


@dataclass(frozen=True, slots=True)
class ContextualAccessPreExecutionArtifactsV1:
    run_plan: ContextualAccessRunPlanV1
    public: ContextualAccessPublicV1


class ContextualAccessRunMetadataV1(EnterpriseOperatorModel):
    callable_identifier: str = Field(min_length=1)
    source_public_schema_version: str = Field(min_length=1)
    product_output_schema_version: str = Field(min_length=1)
    benchmark: BenchmarkIdentityV2
    build_environment: BuildEnvironmentV2
    run: RunMetadataV2
    adapter: AdapterProvenanceV2
    systems_under_test: tuple[SystemComponentProvenanceV2, ...] = Field(min_length=1)
    generator_configuration: tuple[ConfigurationEntryV2, ...] = ()
    event_schedule: tuple[ConfigurationEntryV2, ...] = ()
    evidence_claim: EvidenceClaimV2

    @model_validator(mode="after")
    def canonical_systems(self) -> ContextualAccessRunMetadataV1:
        component_ids = tuple(item.component_id for item in self.systems_under_test)
        if component_ids != tuple(sorted(set(component_ids))):
            raise ValueError("contextual systems under test must be sorted and unique")
        return self


def run_contextual_product_stage_with_preflight(
    root: Path,
    *,
    systems_under_test: tuple[SystemComponentProvenanceV2, ...],
    pre_execution_artifacts: ContextualAccessPreExecutionArtifactsV1,
    source_public: bytes,
    adapter: PublicAdapter,
    runner: ProductRunner,
    adapter_provenance: AdapterProvenanceV2,
    callable_identifier: str,
) -> ExecutionReceiptV2:
    """Persist a validated immutable plan before adapter/product execution."""

    if root.exists():
        raise ProductStageError("a run receipt root must not already exist")
    component_ids = tuple(item.component_id for item in systems_under_test)
    if component_ids != tuple(sorted(set(component_ids))):
        raise ProductStageError("systems under test must be sorted and unique")
    plan = pre_execution_artifacts.run_plan
    public = pre_execution_artifacts.public
    try:
        validate_contextual_run_plan(
            plan,
            public=public,
            systems_under_test=systems_under_test,
        )
    except ContextualProtocolError as error:
        raise ProductStageError("contextual run-plan preflight failed") from error
    parsed_source = _model_from_canonical_bytes(
        source_public,
        ContextualAccessPublicV1,
        "contextual source public input",
    )
    if parsed_source != public:
        raise ReceiptIntegrityError(
            "contextual source public differs from preflight input"
        )

    root.mkdir(parents=True)
    write_canonical_model(root / CONTEXTUAL_RUN_PLAN_PATH, plan)
    _write_new(root / SOURCE_PUBLIC_PATH, source_public)
    adapted = adapter(source_public)
    adapted_public = _model_from_canonical_bytes(
        adapted,
        ContextualAccessPublicV1,
        "contextual adapter public input",
    )
    if adapted_public != public:
        raise ReceiptIntegrityError(
            "contextual adapter output differs from preflight public input"
        )
    plan_digest = digest_bytes_v2((root / CONTEXTUAL_RUN_PLAN_PATH).read_bytes())
    public_digest = digest_bytes_v2(source_public)
    product_input = ContextualAccessProductInputV1(
        run_plan_digest=plan_digest,
        contextual_public_digest=public_digest,
        public=public,
    )
    write_canonical_model(root / PRODUCT_INPUT_PATH, product_input)

    output_path = root / PRODUCT_OUTPUT_PATH
    exit_code = runner(root / PRODUCT_INPUT_PATH, output_path)
    if not output_path.is_file():
        raise ProductStageError("the product runner did not create its output file")
    status = ExecutionStatus.SUCCEEDED if exit_code == 0 else ExecutionStatus.FAILED
    execution = ExecutionReceiptV2(
        boundary=adapter_provenance.boundary,
        callable_identifier=callable_identifier,
        adapter_name=adapter_provenance.name,
        adapter_version=adapter_provenance.version,
        adapter_source_digest=adapter_provenance.source_digest,
        systems_under_test=component_ids,
        run_plan_digest=plan_digest,
        stimulus_digest=public_digest,
        source_public_digest=public_digest,
        product_input_digest=digest_bytes_v2((root / PRODUCT_INPUT_PATH).read_bytes()),
        product_output_digest=digest_bytes_v2(output_path.read_bytes()),
        exit_code=exit_code,
        status=status,
    )
    write_canonical_model(root / EXECUTION_PATH, execution)
    return execution


def build_contextual_access_run_receipt(
    root: Path,
    *,
    pre_execution_artifacts: ContextualAccessPreExecutionArtifactsV1,
    source_public: bytes,
    adapter: PublicAdapter,
    runner: ProductRunner,
    observation_normalizer: ContextualObservationNormalizer,
    truth_loader: ContextualTruthLoader,
    metadata: ContextualAccessRunMetadataV1,
) -> RunReceiptManifestV2:
    """Execute and stage product artifacts before loading evaluator truth."""

    _validate_metadata_bindings(
        pre_execution_artifacts.run_plan,
        pre_execution_artifacts.public,
        metadata,
    )
    execution = run_contextual_product_stage_with_preflight(
        root,
        systems_under_test=metadata.systems_under_test,
        pre_execution_artifacts=pre_execution_artifacts,
        source_public=source_public,
        adapter=adapter,
        runner=runner,
        adapter_provenance=metadata.adapter,
        callable_identifier=metadata.callable_identifier,
    )
    if execution.status is not ExecutionStatus.SUCCEEDED:
        raise ReceiptIntegrityError("a failed contextual execution cannot be evaluated")

    plan = pre_execution_artifacts.run_plan
    public = pre_execution_artifacts.public
    observations = observation_normalizer(
        (root / PRODUCT_OUTPUT_PATH).read_bytes(), plan, public
    )
    validate_contextual_observations(plan, observations)
    write_canonical_model(root / CONTEXTUAL_OBSERVATIONS_PATH, observations)

    evaluator = truth_loader()
    evaluator_digest = digest_bytes_v2(canonical_json_bytes(evaluator))
    if evaluator_digest != metadata.benchmark.evaluator_root_digest:
        raise ReceiptIntegrityError(
            "contextual evaluator digest differs from run metadata"
        )
    truth = compile_contextual_run_truth(plan, public=public, evaluator=evaluator)
    write_canonical_model(root / CONTEXTUAL_RUN_TRUTH_PATH, truth)
    report = evaluate_contextual_access_run(plan, observations, truth)
    write_canonical_model(root / CONTEXTUAL_REPORT_PATH, report)

    specs = _artifact_specs(metadata)
    manifest = RunReceiptManifestV2(
        benchmark=metadata.benchmark,
        build_environment=metadata.build_environment,
        run=metadata.run,
        schema_versions=_schema_versions(specs),
        scoring_formula_versions=(
            VersionBindingV2(
                role="contextual_access",
                version=CONTEXTUAL_RUN_SCORING_VERSION,
            ),
        ),
        generator_configuration=metadata.generator_configuration,
        event_schedule=metadata.event_schedule,
        adapter=metadata.adapter,
        systems_under_test=metadata.systems_under_test,
        artifacts=tuple(describe_artifact_v2(root, spec) for spec in specs),
        execution_status=execution.status,
        evaluation_status=EvaluationStatus.EVALUATED,
        evidence_claim=metadata.evidence_claim,
    )
    write_manifest_last_v2(root, manifest)
    return validate_contextual_access_run_receipt(
        root,
        adapter=adapter,
        observation_normalizer=observation_normalizer,
    )


def validate_contextual_access_run_receipt(
    root: Path,
    *,
    adapter: PublicAdapter | None = None,
    observation_normalizer: ContextualObservationNormalizer | None = None,
) -> RunReceiptManifestV2:
    """Validate inventory, bindings, and deterministic evaluation replay."""

    manifest = validate_manifest_v2(root)
    role_paths = {item.role: item.path for item in manifest.artifacts}
    if role_paths != _ROLE_PATHS:
        raise ReceiptIntegrityError(
            "contextual-access receipt roles or paths are incomplete"
        )
    descriptors = {item.role: item for item in manifest.artifacts}
    declared_schemas = {item.role: item.version for item in manifest.schema_versions}
    expected_schemas = {"run_receipt": manifest.schema_version} | {
        item.role: item.schema_version
        for item in manifest.artifacts
        if item.schema_version is not None
    }
    if declared_schemas != expected_schemas:
        raise ReceiptIntegrityError("manifest schema bindings differ from artifacts")
    if {item.role: item.version for item in manifest.scoring_formula_versions} != {
        "contextual_access": CONTEXTUAL_RUN_SCORING_VERSION
    }:
        raise ReceiptIntegrityError("contextual scoring formula binding is incorrect")

    plan = _read_model(root, CONTEXTUAL_RUN_PLAN_PATH, ContextualAccessRunPlanV1)
    source = (root / SOURCE_PUBLIC_PATH).read_bytes()
    public = _model_from_canonical_bytes(
        source, ContextualAccessPublicV1, "contextual source public input"
    )
    product_input = _read_model(
        root, PRODUCT_INPUT_PATH, ContextualAccessProductInputV1
    )
    parsed_execution = parse_execution_receipt((root / EXECUTION_PATH).read_bytes())
    if not isinstance(parsed_execution, ExecutionReceiptV2):
        raise ReceiptIntegrityError("contextual-access receipt requires execution v2")
    execution = parsed_execution
    observations = _read_model(
        root, CONTEXTUAL_OBSERVATIONS_PATH, ContextualAccessObservationsV1
    )
    truth = _read_model(root, CONTEXTUAL_RUN_TRUTH_PATH, ContextualAccessRunTruthV1)
    report = _read_model(root, CONTEXTUAL_REPORT_PATH, ContextualAccessReportV1)

    try:
        validate_contextual_run_plan(
            plan,
            public=public,
            systems_under_test=manifest.systems_under_test,
        )
        validate_contextual_observations(plan, observations)
    except ContextualProtocolError as error:
        raise ReceiptIntegrityError(
            "contextual-access artifact relationships are invalid"
        ) from error
    plan_digest = descriptors["contextual_access_run_plan"].digest
    public_digest = digest_bytes_v2(source)
    if not (product_input.run_plan_digest == execution.run_plan_digest == plan_digest):
        raise ReceiptIntegrityError("contextual run-plan digest bindings disagree")
    if not (
        product_input.contextual_public_digest
        == execution.stimulus_digest
        == execution.source_public_digest
        == public_digest
        == descriptors["source_public"].digest
    ):
        raise ReceiptIntegrityError("contextual public digest bindings disagree")
    if product_input.public != public:
        raise ReceiptIntegrityError("contextual product input differs from source")
    if (
        execution.product_input_digest != descriptors["product_input"].digest
        or execution.product_output_digest != descriptors["product_output"].digest
    ):
        raise ReceiptIntegrityError("execution artifact digests differ from manifest")
    expected_system_ids = tuple(
        item.component_id for item in manifest.systems_under_test
    )
    if execution.systems_under_test != expected_system_ids:
        raise ReceiptIntegrityError("execution systems differ from manifest")
    if (
        execution.boundary != manifest.adapter.boundary
        or execution.adapter_name != manifest.adapter.name
        or execution.adapter_version != manifest.adapter.version
        or execution.adapter_source_digest != manifest.adapter.source_digest
        or execution.status is not manifest.execution_status
    ):
        raise ReceiptIntegrityError("execution provenance differs from manifest")
    if manifest.evaluation_status is not EvaluationStatus.EVALUATED:
        raise ReceiptIntegrityError("a complete contextual receipt is evaluated")
    _validate_manifest_benchmark(plan, public, truth, manifest)

    if adapter is not None:
        adapted = _model_from_canonical_bytes(
            adapter(source),
            ContextualAccessPublicV1,
            "contextual adapter public input",
        )
        if adapted != public:
            raise ReceiptIntegrityError(
                "contextual product input differs from adapter output"
            )
    if observation_normalizer is not None:
        expected_observations = observation_normalizer(
            (root / PRODUCT_OUTPUT_PATH).read_bytes(), plan, public
        )
        if observations != expected_observations:
            raise ReceiptIntegrityError(
                "contextual observations differ from normalized product output"
            )
    expected_report = evaluate_contextual_access_run(plan, observations, truth)
    if report != expected_report:
        raise ReceiptIntegrityError("contextual-access evaluation does not replay")
    return manifest


def _artifact_specs(
    metadata: ContextualAccessRunMetadataV1,
) -> tuple[ArtifactSpecV2, ...]:
    canonical = ArtifactSerialization.CANONICAL_JSON_V1
    return (
        ArtifactSpecV2(
            path=CONTEXTUAL_RUN_PLAN_PATH,
            role="contextual_access_run_plan",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=CONTEXTUAL_RUN_PLAN_SCHEMA_VERSION,
        ),
        ArtifactSpecV2(
            path=SOURCE_PUBLIC_PATH,
            role="source_public",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=metadata.source_public_schema_version,
        ),
        ArtifactSpecV2(
            path=PRODUCT_INPUT_PATH,
            role="product_input",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=CONTEXTUAL_PRODUCT_INPUT_SCHEMA_VERSION,
        ),
        ArtifactSpecV2(
            path=PRODUCT_OUTPUT_PATH,
            role="product_output",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=ArtifactSerialization.RAW_BYTES,
            schema_version=metadata.product_output_schema_version,
        ),
        ArtifactSpecV2(
            path=EXECUTION_PATH,
            role="execution",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=EXECUTION_RECEIPT_SCHEMA_VERSION_V2,
        ),
        ArtifactSpecV2(
            path=CONTEXTUAL_OBSERVATIONS_PATH,
            role="contextual_access_observations",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=CONTEXTUAL_OBSERVATIONS_SCHEMA_VERSION,
        ),
        ArtifactSpecV2(
            path=CONTEXTUAL_RUN_TRUTH_PATH,
            role="contextual_access_run_truth",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version=CONTEXTUAL_RUN_TRUTH_SCHEMA_VERSION,
        ),
        ArtifactSpecV2(
            path=CONTEXTUAL_REPORT_PATH,
            role="contextual_access_evaluation",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version=CONTEXTUAL_REPORT_SCHEMA_VERSION,
        ),
    )


def _schema_versions(specs: tuple[ArtifactSpecV2, ...]) -> tuple[VersionBindingV2, ...]:
    return (
        VersionBindingV2(role="run_receipt", version=RUN_RECEIPT_SCHEMA_VERSION_V2),
        *tuple(
            VersionBindingV2(role=spec.role, version=spec.schema_version)
            for spec in specs
            if spec.schema_version is not None
        ),
    )


def _validate_metadata_bindings(
    plan: ContextualAccessRunPlanV1,
    public: ContextualAccessPublicV1,
    metadata: ContextualAccessRunMetadataV1,
) -> None:
    if metadata.run.run_id != plan.run_id:
        raise ReceiptIntegrityError("run metadata identifier differs from the plan")
    _validate_benchmark_identity(plan, public, metadata.benchmark)


def _validate_manifest_benchmark(
    plan: ContextualAccessRunPlanV1,
    public: ContextualAccessPublicV1,
    truth: ContextualAccessRunTruthV1,
    manifest: RunReceiptManifestV2,
) -> None:
    if manifest.run.run_id != plan.run_id:
        raise ReceiptIntegrityError("manifest run identifier differs from the plan")
    _validate_benchmark_identity(plan, public, manifest.benchmark)
    if (
        manifest.benchmark.evaluator_root_digest != truth.evaluator_digest
        or manifest.benchmark.public_root_digest
        != digest_bytes_v2(canonical_json_bytes(public))
    ):
        raise ReceiptIntegrityError("contextual benchmark roots differ from artifacts")


def _validate_benchmark_identity(
    plan: ContextualAccessRunPlanV1,
    public: ContextualAccessPublicV1,
    benchmark: BenchmarkIdentityV2,
) -> None:
    binding = plan.benchmark
    expected = (
        binding.benchmark_family,
        binding.benchmark_version,
        binding.contextual_public_root_digest,
        binding.identity_access_universe_digest,
        DigestV2(value=public.benchmark.policy_digest.value),
        binding.request_digest,
    )
    actual = (
        benchmark.family,
        benchmark.version,
        benchmark.public_root_digest,
        benchmark.identity_access_universe_digest,
        benchmark.policy_digest,
        benchmark.cell_digest,
    )
    if actual != expected:
        raise ReceiptIntegrityError("contextual benchmark identity differs from plan")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


def _model_from_canonical_bytes[ModelT: BaseModel](
    payload: bytes, model: type[ModelT], description: str
) -> ModelT:
    try:
        parsed = model.model_validate_json(payload)
    except ValueError as error:
        raise ReceiptIntegrityError(
            f"{description} does not match its schema"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise ReceiptIntegrityError(f"{description} is not canonical JSON")
    return parsed


def _read_model[ModelT: BaseModel](
    root: Path, path: str, model: type[ModelT]
) -> ModelT:
    try:
        payload = (root / path).read_bytes()
    except OSError as error:
        raise ReceiptIntegrityError(f"{path} cannot be read") from error
    return _model_from_canonical_bytes(payload, model, path)


__all__ = [
    "CONTEXTUAL_PRODUCT_INPUT_SCHEMA_VERSION",
    "CONTEXTUAL_RUN_SCORING_VERSION",
    "ContextualAccessPreExecutionArtifactsV1",
    "ContextualAccessProductInputV1",
    "ContextualAccessRunMetadataV1",
    "ContextualObservationNormalizer",
    "ContextualTruthLoader",
    "build_contextual_access_run_receipt",
    "run_contextual_product_stage_with_preflight",
    "validate_contextual_access_run_receipt",
]
