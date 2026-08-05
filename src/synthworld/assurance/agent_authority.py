"""Executable receipt-v2 specialization for agent-authority lab runs."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from synthworld.agent_authority.models import (
    AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION,
    AGENT_AUTHORITY_PRODUCT_INPUT_SCHEMA_VERSION,
    AGENT_AUTHORITY_REPORT_SCHEMA_VERSION,
    AGENT_AUTHORITY_RUN_PLAN_SCHEMA_VERSION,
    AGENT_AUTHORITY_TRUTH_SCHEMA_VERSION,
    AgentAuthorityLabReportV1,
    AgentAuthorityLabTruthV1,
    AgentAuthorityOperatorModel,
    AgentAuthorityProductInputV1,
    AgentAuthorityRunObservationsV1,
    AgentAuthorityRunPlanV1,
    AgentAuthorityStimulusSetV1,
    validate_observation_references,
    validate_run_plan_references,
)
from synthworld.agent_authority.models_v2 import (
    AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION_V2,
    AgentAuthorityRunObservationsV2,
    validate_observation_references_v2,
)
from synthworld.agent_authority.scoring import (
    evaluate_agent_authority_lab,
    validate_agent_authority_truth,
)
from synthworld.agent_authority.scoring_v2 import evaluate_agent_authority_lab_v2
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

RUN_PLAN_PATH = "context/run-plan.json"
OBSERVATIONS_PATH = "observations/agent-authority.json"
TRUTH_PATH = "evaluator/agent-authority-truth.json"
EVALUATION_PATH = "evaluation/agent-authority-report.json"
AGENT_AUTHORITY_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"
AGENT_AUTHORITY_SCORING_VERSION_V2: Literal["2.0.0"] = "2.0.0"

_ROLE_PATHS = {
    "agent_authority_run_plan": RUN_PLAN_PATH,
    "source_public": SOURCE_PUBLIC_PATH,
    "product_input": PRODUCT_INPUT_PATH,
    "product_output": PRODUCT_OUTPUT_PATH,
    "execution": EXECUTION_PATH,
    "agent_authority_observations": OBSERVATIONS_PATH,
    "agent_authority_truth": TRUTH_PATH,
    "agent_authority_evaluation": EVALUATION_PATH,
}

AgentAuthorityRunObservations = (
    AgentAuthorityRunObservationsV1 | AgentAuthorityRunObservationsV2
)
ObservationNormalizer = Callable[
    [bytes, AgentAuthorityRunPlanV1, AgentAuthorityStimulusSetV1],
    AgentAuthorityRunObservations,
]
TruthLoader = Callable[[], AgentAuthorityLabTruthV1]


@dataclass(frozen=True, slots=True)
class AgentAuthorityPreExecutionArtifactsV1:
    run_plan: AgentAuthorityRunPlanV1
    stimuli: AgentAuthorityStimulusSetV1


class AgentAuthorityRunMetadataV1(AgentAuthorityOperatorModel):
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
    def validate_system_order(self) -> AgentAuthorityRunMetadataV1:
        component_ids = tuple(item.component_id for item in self.systems_under_test)
        if component_ids != tuple(sorted(set(component_ids))):
            raise ValueError("systems under test must be sorted and unique")
        return self


def stimulus_set_digest(stimuli: AgentAuthorityStimulusSetV1) -> DigestV2:
    """Digest the canonical, versioned stimulus-set artifact."""

    return digest_bytes_v2(canonical_json_bytes(stimuli))


def run_product_stage_with_preflight(
    root: Path,
    *,
    systems_under_test: tuple[SystemComponentProvenanceV2, ...],
    pre_execution_artifacts: AgentAuthorityPreExecutionArtifactsV1,
    source_public: bytes,
    adapter: PublicAdapter,
    runner: ProductRunner,
    adapter_provenance: AdapterProvenanceV2,
    callable_identifier: str,
) -> ExecutionReceiptV2:
    """Validate and persist the immutable plan before adapter/product execution."""

    if root.exists():
        raise ProductStageError("a run receipt root must not already exist")
    component_ids = tuple(item.component_id for item in systems_under_test)
    if component_ids != tuple(sorted(set(component_ids))):
        raise ProductStageError("systems under test must be sorted and unique")

    plan = pre_execution_artifacts.run_plan
    stimuli = pre_execution_artifacts.stimuli
    validate_run_plan_references(plan, stimuli, systems_under_test)
    calculated_stimulus_digest = stimulus_set_digest(stimuli)
    if plan.stimulus_set_digest != calculated_stimulus_digest:
        raise ReceiptIntegrityError("run-plan stimulus digest differs from stimuli")
    _assert_canonical_json_bytes(source_public, "source public input")

    root.mkdir(parents=True)
    write_canonical_model(root / RUN_PLAN_PATH, plan)
    _write_new(root / SOURCE_PUBLIC_PATH, source_public)

    adapted = adapter(source_public)
    adapted_stimuli = _model_from_canonical_bytes(
        adapted,
        AgentAuthorityStimulusSetV1,
        "adapter stimulus set",
    )
    if adapted_stimuli != stimuli:
        raise ReceiptIntegrityError(
            "adapter stimulus set differs from preflight-declared stimuli"
        )
    run_plan_digest = digest_bytes_v2((root / RUN_PLAN_PATH).read_bytes())
    product_input = AgentAuthorityProductInputV1(
        run_plan_digest=run_plan_digest,
        stimuli=stimuli.stimuli,
        stimulus_digest=calculated_stimulus_digest,
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
        run_plan_digest=run_plan_digest,
        stimulus_digest=calculated_stimulus_digest,
        source_public_digest=digest_bytes_v2(source_public),
        product_input_digest=digest_bytes_v2((root / PRODUCT_INPUT_PATH).read_bytes()),
        product_output_digest=digest_bytes_v2(output_path.read_bytes()),
        exit_code=exit_code,
        status=status,
    )
    write_canonical_model(root / EXECUTION_PATH, execution)
    return execution


def build_agent_authority_run_receipt(
    root: Path,
    *,
    pre_execution_artifacts: AgentAuthorityPreExecutionArtifactsV1,
    source_public: bytes,
    adapter: PublicAdapter,
    runner: ProductRunner,
    observation_normalizer: ObservationNormalizer,
    truth_loader: TruthLoader,
    metadata: AgentAuthorityRunMetadataV1,
) -> RunReceiptManifestV2:
    """Execute product first, normalize observations, then load and score truth."""

    _validate_metadata_bindings(pre_execution_artifacts.run_plan, metadata)
    run_product_stage_with_preflight(
        root,
        systems_under_test=metadata.systems_under_test,
        pre_execution_artifacts=pre_execution_artifacts,
        source_public=source_public,
        adapter=adapter,
        runner=runner,
        adapter_provenance=metadata.adapter,
        callable_identifier=metadata.callable_identifier,
    )
    return finalize_agent_authority_run_receipt(
        root,
        pre_execution_artifacts=pre_execution_artifacts,
        adapter=adapter,
        observation_normalizer=observation_normalizer,
        truth_loader=truth_loader,
        metadata=metadata,
    )


def finalize_agent_authority_run_receipt(
    root: Path,
    *,
    pre_execution_artifacts: AgentAuthorityPreExecutionArtifactsV1,
    adapter: PublicAdapter,
    observation_normalizer: ObservationNormalizer,
    truth_loader: TruthLoader,
    metadata: AgentAuthorityRunMetadataV1,
) -> RunReceiptManifestV2:
    """Evaluate a successful, fully attributed product stage and seal its receipt.

    This two-phase entry point lets a live runner construct ``metadata.run`` only
    after the external execution has completed.  It replays and validates every
    public product-stage binding before evaluator truth is loaded.
    """

    _validate_metadata_bindings(pre_execution_artifacts.run_plan, metadata)
    execution = _validate_staged_product_execution(
        root,
        pre_execution_artifacts=pre_execution_artifacts,
        adapter=adapter,
        metadata=metadata,
    )

    raw_output = (root / PRODUCT_OUTPUT_PATH).read_bytes()
    observations = observation_normalizer(
        raw_output,
        pre_execution_artifacts.run_plan,
        pre_execution_artifacts.stimuli,
    )
    _validate_observation_references_dispatched(
        pre_execution_artifacts.run_plan,
        pre_execution_artifacts.stimuli,
        observations,
        metadata.systems_under_test,
    )
    write_canonical_model(root / OBSERVATIONS_PATH, observations)

    # The evaluator-side loader is deliberately called only after product output
    # and normalized observations have both been durably staged.
    truth = truth_loader()
    validate_agent_authority_truth(
        pre_execution_artifacts.run_plan,
        pre_execution_artifacts.stimuli,
        truth,
    )
    write_canonical_model(root / TRUTH_PATH, truth)
    report = _evaluate_agent_authority_lab_dispatched(
        pre_execution_artifacts.run_plan,
        pre_execution_artifacts.stimuli,
        observations,
        truth,
        metadata.systems_under_test,
    )
    write_canonical_model(root / EVALUATION_PATH, report)

    specs = _artifact_specs(metadata, observations.schema_version)
    scoring_version = _scoring_version(observations)
    manifest = RunReceiptManifestV2(
        benchmark=metadata.benchmark,
        build_environment=metadata.build_environment,
        run=metadata.run,
        schema_versions=_schema_versions(specs),
        scoring_formula_versions=(
            VersionBindingV2(
                role="agent_authority_lab",
                version=scoring_version,
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
    return validate_agent_authority_run_receipt(
        root,
        adapter=adapter,
        observation_normalizer=observation_normalizer,
    )


def _validate_staged_product_execution(
    root: Path,
    *,
    pre_execution_artifacts: AgentAuthorityPreExecutionArtifactsV1,
    adapter: PublicAdapter,
    metadata: AgentAuthorityRunMetadataV1,
) -> ExecutionReceiptV2:
    """Validate all pre-evaluation artifacts without reading evaluator truth."""

    required_paths = (
        RUN_PLAN_PATH,
        SOURCE_PUBLIC_PATH,
        PRODUCT_INPUT_PATH,
        PRODUCT_OUTPUT_PATH,
        EXECUTION_PATH,
    )
    missing_paths = tuple(
        path for path in required_paths if not (root / path).is_file()
    )
    if missing_paths:
        raise ReceiptIntegrityError("the staged product execution is incomplete")

    plan = _read_model(root, RUN_PLAN_PATH, AgentAuthorityRunPlanV1)
    if plan != pre_execution_artifacts.run_plan:
        raise ReceiptIntegrityError("staged run plan differs from preflight")
    product_input = _read_model(root, PRODUCT_INPUT_PATH, AgentAuthorityProductInputV1)
    stimuli = AgentAuthorityStimulusSetV1(stimuli=product_input.stimuli)
    if stimuli != pre_execution_artifacts.stimuli:
        raise ReceiptIntegrityError("staged product stimuli differ from preflight")

    source_public = (root / SOURCE_PUBLIC_PATH).read_bytes()
    _assert_canonical_json_bytes(source_public, "source public input")
    adapted_stimuli = _model_from_canonical_bytes(
        adapter(source_public),
        AgentAuthorityStimulusSetV1,
        "adapter stimulus set",
    )
    if adapted_stimuli != stimuli:
        raise ReceiptIntegrityError("product stimuli differ from adapter output")

    parsed_execution = parse_execution_receipt((root / EXECUTION_PATH).read_bytes())
    if not isinstance(parsed_execution, ExecutionReceiptV2):
        raise ReceiptIntegrityError("agent-authority receipt requires execution v2")
    execution = parsed_execution
    if execution.status is not ExecutionStatus.SUCCEEDED:
        raise ReceiptIntegrityError("a failed product execution cannot be evaluated")

    run_plan_digest = digest_bytes_v2((root / RUN_PLAN_PATH).read_bytes())
    calculated_stimulus_digest = stimulus_set_digest(stimuli)
    expected_input = AgentAuthorityProductInputV1(
        run_plan_digest=run_plan_digest,
        stimuli=stimuli.stimuli,
        stimulus_digest=calculated_stimulus_digest,
    )
    if product_input != expected_input:
        raise ReceiptIntegrityError("staged product input bindings are invalid")

    component_ids = tuple(item.component_id for item in metadata.systems_under_test)
    if execution.systems_under_test != component_ids:
        raise ReceiptIntegrityError("execution systems differ from run metadata")
    execution_adapter = (
        execution.boundary,
        execution.callable_identifier,
        execution.adapter_name,
        execution.adapter_version,
        execution.adapter_source_digest,
    )
    metadata_adapter = (
        metadata.adapter.boundary,
        metadata.callable_identifier,
        metadata.adapter.name,
        metadata.adapter.version,
        metadata.adapter.source_digest,
    )
    if execution_adapter != metadata_adapter:
        raise ReceiptIntegrityError(
            "execution adapter provenance differs from metadata"
        )
    execution_digests = (
        execution.run_plan_digest,
        execution.stimulus_digest,
        execution.source_public_digest,
        execution.product_input_digest,
        execution.product_output_digest,
    )
    staged_digests = (
        run_plan_digest,
        calculated_stimulus_digest,
        digest_bytes_v2(source_public),
        digest_bytes_v2((root / PRODUCT_INPUT_PATH).read_bytes()),
        digest_bytes_v2((root / PRODUCT_OUTPUT_PATH).read_bytes()),
    )
    if execution_digests != staged_digests:
        raise ReceiptIntegrityError("execution artifact digest bindings disagree")
    return execution


def validate_agent_authority_run_receipt(
    root: Path,
    *,
    adapter: PublicAdapter | None = None,
    observation_normalizer: ObservationNormalizer | None = None,
) -> RunReceiptManifestV2:
    """Validate the complete receipt and replay supplied public transformations."""

    manifest = validate_manifest_v2(root)
    role_paths = {item.role: item.path for item in manifest.artifacts}
    if role_paths != _ROLE_PATHS:
        raise ReceiptIntegrityError(
            "agent-authority receipt roles or paths are incomplete"
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
    plan = _read_model(root, RUN_PLAN_PATH, AgentAuthorityRunPlanV1)
    product_input = _read_model(root, PRODUCT_INPUT_PATH, AgentAuthorityProductInputV1)
    parsed_execution = parse_execution_receipt((root / EXECUTION_PATH).read_bytes())
    if not isinstance(parsed_execution, ExecutionReceiptV2):
        raise ReceiptIntegrityError("agent-authority receipt requires execution v2")
    execution = parsed_execution
    stimuli = AgentAuthorityStimulusSetV1(stimuli=product_input.stimuli)
    observations = _read_observations(root)
    truth = _read_model(root, TRUTH_PATH, AgentAuthorityLabTruthV1)
    report = _read_model(root, EVALUATION_PATH, AgentAuthorityLabReportV1)
    if (
        descriptors["agent_authority_observations"].schema_version
        != observations.schema_version
    ):
        raise ReceiptIntegrityError(
            "observation artifact schema binding differs from its payload"
        )
    if {item.role: item.version for item in manifest.scoring_formula_versions} != {
        "agent_authority_lab": _scoring_version(observations)
    }:
        raise ReceiptIntegrityError("manifest scoring formula binding is incorrect")

    try:
        validate_run_plan_references(plan, stimuli, manifest.systems_under_test)
        _validate_observation_references_dispatched(
            plan, stimuli, observations, manifest.systems_under_test
        )
        validate_agent_authority_truth(plan, stimuli, truth)
    except ValueError as error:
        raise ReceiptIntegrityError(
            "agent-authority artifact relationships are invalid"
        ) from error
    plan_digest = descriptors["agent_authority_run_plan"].digest
    calculated_stimulus_digest = stimulus_set_digest(stimuli)
    if not (product_input.run_plan_digest == execution.run_plan_digest == plan_digest):
        raise ReceiptIntegrityError("run-plan digest bindings disagree")
    if not (
        plan.stimulus_set_digest
        == product_input.stimulus_digest
        == execution.stimulus_digest
        == calculated_stimulus_digest
    ):
        raise ReceiptIntegrityError("stimulus digest bindings disagree")
    if (
        execution.source_public_digest != descriptors["source_public"].digest
        or execution.product_input_digest != descriptors["product_input"].digest
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
        raise ReceiptIntegrityError("a complete agent-authority receipt is evaluated")
    _validate_manifest_benchmark(plan, manifest)

    source = (root / SOURCE_PUBLIC_PATH).read_bytes()
    if adapter is not None:
        adapted = _model_from_canonical_bytes(
            adapter(source),
            AgentAuthorityStimulusSetV1,
            "adapter stimulus set",
        )
        if adapted != stimuli:
            raise ReceiptIntegrityError("product stimuli differ from adapter output")
    if observation_normalizer is not None:
        expected_observations = observation_normalizer(
            (root / PRODUCT_OUTPUT_PATH).read_bytes(), plan, stimuli
        )
        if observations != expected_observations:
            raise ReceiptIntegrityError(
                "observations differ from normalized product output"
            )
    expected_report = _evaluate_agent_authority_lab_dispatched(
        plan, stimuli, observations, truth, manifest.systems_under_test
    )
    if report != expected_report:
        raise ReceiptIntegrityError("agent-authority evaluation does not replay")
    return manifest


def _validate_observation_references_dispatched(
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    observations: AgentAuthorityRunObservations,
    systems: tuple[SystemComponentProvenanceV2, ...],
) -> None:
    if isinstance(observations, AgentAuthorityRunObservationsV2):
        validate_observation_references_v2(plan, stimuli, observations, systems)
        return
    validate_observation_references(plan, stimuli, observations, systems)


def _evaluate_agent_authority_lab_dispatched(
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    observations: AgentAuthorityRunObservations,
    truth: AgentAuthorityLabTruthV1,
    systems: tuple[SystemComponentProvenanceV2, ...],
) -> AgentAuthorityLabReportV1:
    if isinstance(observations, AgentAuthorityRunObservationsV2):
        return evaluate_agent_authority_lab_v2(
            plan, stimuli, observations, truth, systems
        )
    return evaluate_agent_authority_lab(plan, stimuli, observations, truth, systems)


def _scoring_version(observations: AgentAuthorityRunObservations) -> str:
    if isinstance(observations, AgentAuthorityRunObservationsV2):
        return AGENT_AUTHORITY_SCORING_VERSION_V2
    return AGENT_AUTHORITY_SCORING_VERSION


def _read_observations(root: Path) -> AgentAuthorityRunObservations:
    payload = (root / OBSERVATIONS_PATH).read_bytes()
    # validate_manifest_v2 has already asserted canonical UTF-8 JSON bytes.
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ReceiptIntegrityError(
            "agent-authority observations do not match a supported schema"
        )
    version = document.get("schema_version")
    if version == AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION:
        return _model_from_canonical_bytes(
            payload,
            AgentAuthorityRunObservationsV1,
            OBSERVATIONS_PATH,
        )
    if version == AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION_V2:
        return _model_from_canonical_bytes(
            payload,
            AgentAuthorityRunObservationsV2,
            OBSERVATIONS_PATH,
        )
    raise ReceiptIntegrityError(
        "agent-authority observations use an unsupported schema version"
    )


def _artifact_specs(
    metadata: AgentAuthorityRunMetadataV1,
    observations_schema_version: str = AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION,
) -> tuple[ArtifactSpecV2, ...]:
    canonical = ArtifactSerialization.CANONICAL_JSON_V1
    return (
        ArtifactSpecV2(
            path=RUN_PLAN_PATH,
            role="agent_authority_run_plan",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=AGENT_AUTHORITY_RUN_PLAN_SCHEMA_VERSION,
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
            schema_version=AGENT_AUTHORITY_PRODUCT_INPUT_SCHEMA_VERSION,
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
            path=OBSERVATIONS_PATH,
            role="agent_authority_observations",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=observations_schema_version,
        ),
        ArtifactSpecV2(
            path=TRUTH_PATH,
            role="agent_authority_truth",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version=AGENT_AUTHORITY_TRUTH_SCHEMA_VERSION,
        ),
        ArtifactSpecV2(
            path=EVALUATION_PATH,
            role="agent_authority_evaluation",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version=AGENT_AUTHORITY_REPORT_SCHEMA_VERSION,
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
    plan: AgentAuthorityRunPlanV1, metadata: AgentAuthorityRunMetadataV1
) -> None:
    if metadata.run.run_id != plan.run_id:
        raise ReceiptIntegrityError("run metadata identifier differs from the plan")
    _validate_benchmark_identity(plan, metadata.benchmark)


def _validate_manifest_benchmark(
    plan: AgentAuthorityRunPlanV1, manifest: RunReceiptManifestV2
) -> None:
    if manifest.run.run_id != plan.run_id:
        raise ReceiptIntegrityError("manifest run identifier differs from the plan")
    _validate_benchmark_identity(plan, manifest.benchmark)


def _validate_benchmark_identity(
    plan: AgentAuthorityRunPlanV1, benchmark: BenchmarkIdentityV2
) -> None:
    binding = plan.benchmark
    compared = (
        benchmark.family,
        benchmark.version,
        benchmark.public_root_digest,
        benchmark.evaluator_root_digest,
        benchmark.identity_access_universe_digest,
        benchmark.policy_digest,
        benchmark.cell_digest,
    )
    expected = (
        binding.benchmark_family,
        binding.benchmark_version,
        binding.public_root_digest,
        binding.evaluator_root_digest,
        binding.identity_access_universe_digest,
        binding.policy_digest,
        binding.cell_digest,
    )
    if compared != expected:
        raise ReceiptIntegrityError("benchmark identity differs from the run plan")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


def _assert_canonical_json_bytes(payload: bytes, description: str) -> None:
    try:
        value = json.loads(payload.decode("utf-8"))
        canonical = (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (UnicodeDecodeError, ValueError) as error:
        raise ReceiptIntegrityError(f"{description} must use canonical JSON") from error
    if payload != canonical:
        raise ReceiptIntegrityError(f"{description} must use canonical JSON")


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
    return _model_from_canonical_bytes((root / path).read_bytes(), model, path)


__all__ = [
    "AGENT_AUTHORITY_SCORING_VERSION",
    "AGENT_AUTHORITY_SCORING_VERSION_V2",
    "EVALUATION_PATH",
    "OBSERVATIONS_PATH",
    "RUN_PLAN_PATH",
    "TRUTH_PATH",
    "AgentAuthorityPreExecutionArtifactsV1",
    "AgentAuthorityRunMetadataV1",
    "AgentAuthorityRunObservations",
    "ObservationNormalizer",
    "TruthLoader",
    "build_agent_authority_run_receipt",
    "finalize_agent_authority_run_receipt",
    "run_product_stage_with_preflight",
    "stimulus_set_digest",
    "validate_agent_authority_run_receipt",
]
