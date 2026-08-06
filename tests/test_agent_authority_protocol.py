"""Executable and adversarial coverage for the agent-authority run protocol."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from synthworld.agent_authority.cases import (
    AgentAuthorityStimulusSetV1,
    ChannelScanV1,
    EvidenceChannel,
)
from synthworld.agent_authority.common import (
    AgentAuthorityControlId,
    AttributionKind,
    CollectionStatus,
    EvidenceKind,
    FindingStatus,
    ObservationAttributionV1,
    RedactionStatus,
)
from synthworld.agent_authority.models import (
    AgentAuthorityLabReportV1,
    AgentAuthorityLabTruthV1,
    AgentAuthorityRunObservationsV1,
    AgentAuthorityRunPlanV1,
)
from synthworld.agent_authority.operational import (
    AddedLatencyMeasurementV1,
    CompatibilityStatus,
    LatencyStatistic,
)
from synthworld.agent_authority.reference import (
    build_reference_agent_authority_run_receipt,
    reference_metadata,
    reference_observations,
    reference_plan,
    reference_stimuli,
    reference_systems,
    reference_truth,
)
from synthworld.agent_authority.scoring import (
    evaluate_agent_authority_lab,
    validate_agent_authority_truth,
)
from synthworld.assurance.agent_authority import (
    EVALUATION_PATH,
    OBSERVATIONS_PATH,
    RUN_PLAN_PATH,
    TRUTH_PATH,
    AgentAuthorityPreExecutionArtifactsV1,
    run_product_stage_with_preflight,
    stimulus_set_digest,
    validate_agent_authority_run_receipt,
)
from synthworld.assurance.models import EvidenceClaim, RunReceiptManifest, TreeState
from synthworld.assurance.models_v2 import (
    ConfigurationObservabilityV2,
    DigestV2,
    EvidenceClaimV2,
    ManagedServiceComponentProvenanceV2,
    ReplayabilityV2,
    VersionObservabilityV2,
)
from synthworld.assurance.receipt import (
    EXECUTION_PATH,
    MANIFEST_PATH,
    PRODUCT_INPUT_PATH,
    PRODUCT_OUTPUT_PATH,
    SOURCE_PUBLIC_PATH,
    ProductStageError,
    ReceiptIntegrityError,
    canonical_json_bytes,
)
from synthworld.assurance.receipt_v2 import (
    digest_bytes_v2,
    validate_manifest_dispatched,
)


@pytest.fixture(scope="session")
def reference_receipt(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("agent-authority-receipt") / "run"
    build_reference_agent_authority_run_receipt(root)
    return root


def _copy_receipt(template: Path, tmp_path: Path) -> Path:
    root = tmp_path / "run"
    shutil.copytree(template, root)
    return root


def _replace_observation_payload(
    observations: AgentAuthorityRunObservationsV1,
    stimulus_id: str,
    **updates: object,
) -> AgentAuthorityRunObservationsV1:
    rows = []
    for row in observations.observations:
        if row.stimulus_id != stimulus_id:
            rows.append(row)
            continue
        payload = row.payload.model_dump(mode="json")
        payload.update(updates)
        row_data = row.model_dump(mode="json")
        row_data["payload"] = payload
        rows.append(type(row).model_validate(row_data))
    data = observations.model_dump(mode="json")
    data["observations"] = [item.model_dump(mode="json") for item in rows]
    return AgentAuthorityRunObservationsV1.model_validate(data)


def _evaluate(
    observations: AgentAuthorityRunObservationsV1,
) -> AgentAuthorityLabReportV1:
    return evaluate_agent_authority_lab(
        reference_plan(),
        reference_stimuli(),
        observations,
        reference_truth(),
        reference_systems(),
    )


def test_reference_receipt_is_complete_deterministic_and_marker_correct(
    reference_receipt: Path,
    tmp_path: Path,
) -> None:
    second = tmp_path / "second"
    manifest = build_reference_agent_authority_run_receipt(second)
    first_bytes = {
        item.relative_to(reference_receipt).as_posix(): item.read_bytes()
        for item in reference_receipt.rglob("*")
        if item.is_file()
    }
    second_bytes = {
        item.relative_to(second).as_posix(): item.read_bytes()
        for item in second.rglob("*")
        if item.is_file()
    }
    assert first_bytes == second_bytes
    assert set(first_bytes) == {
        RUN_PLAN_PATH,
        SOURCE_PUBLIC_PATH,
        PRODUCT_INPUT_PATH,
        PRODUCT_OUTPUT_PATH,
        EXECUTION_PATH,
        OBSERVATIONS_PATH,
        TRUTH_PATH,
        EVALUATION_PATH,
        MANIFEST_PATH,
    }
    assert manifest.schema_version == "2.0.0"
    assert manifest.evidence_claim is EvidenceClaimV2.GENERATED_TRANSFER_EVIDENCE
    assert {item.role: item.path for item in manifest.artifacts} == {
        "agent_authority_run_plan": RUN_PLAN_PATH,
        "source_public": SOURCE_PUBLIC_PATH,
        "product_input": PRODUCT_INPUT_PATH,
        "product_output": PRODUCT_OUTPUT_PATH,
        "execution": EXECUTION_PATH,
        "agent_authority_observations": OBSERVATIONS_PATH,
        "agent_authority_truth": TRUTH_PATH,
        "agent_authority_evaluation": EVALUATION_PATH,
    }
    product_output = next(
        item for item in manifest.artifacts if item.role == "product_output"
    )
    assert product_output.serialization.value == "raw_bytes"
    assert b'"synthetic"' not in first_bytes[RUN_PLAN_PATH]
    assert b'"synthetic"' not in first_bytes[OBSERVATIONS_PATH]
    assert b'"synthetic":true' in first_bytes[PRODUCT_INPUT_PATH]
    assert b'"synthetic":true' in first_bytes[TRUTH_PATH]
    product_input_document = json.loads(
        first_bytes[PRODUCT_INPUT_PATH], object_pairs_hook=dict
    )
    assert tuple(product_input_document) == (
        "run_plan_digest",
        "schema_version",
        "stimuli",
        "stimulus_digest",
    )
    report_document = json.loads(first_bytes[EVALUATION_PATH])
    assert report_document["synthetic"] is True
    assert "security_aggregate" not in report_document


def test_reference_report_keeps_security_and_operations_independent() -> None:
    report = _evaluate(reference_observations())
    assert {item.status for item in report.findings} == {FindingStatus.PASS}
    assert {item.name for item in report.security_metrics} == {
        "channel_probe_coverage",
        "canary_exposure_rate",
        "replay_rejection_rate",
        "direct_path_bypass_prevention_rate",
        "egress_policy_enforcement_rate",
        "critical_dependency_fail_closed_rate",
        "revocation_bound_compliance_rate",
        "post_bound_false_allow_rate",
    }
    assert {item.status for item in report.operational_stages} == {
        "complete",
        "gap",
    }
    assert report.added_latency == (
        AddedLatencyMeasurementV1(
            sut_stage_id="sut-a",
            baseline_stage_id="baseline-a",
            statistic=LatencyStatistic.P50,
            added_latency_ns=500,
        ),
        AddedLatencyMeasurementV1(
            sut_stage_id="sut-a",
            baseline_stage_id="baseline-a",
            statistic=LatencyStatistic.P95,
            added_latency_ns=800,
        ),
    )
    assert tuple(item.status for item in report.compatibility) == tuple(
        CompatibilityStatus
    )


def test_preflight_writes_plan_before_adapter_and_runner(tmp_path: Path) -> None:
    root = tmp_path / "run"
    events: list[str] = []
    stimuli = reference_stimuli()
    plan = reference_plan()

    def adapter(payload: bytes) -> bytes:
        events.append("adapter")
        assert (root / RUN_PLAN_PATH).read_bytes() == canonical_json_bytes(plan)
        assert (root / SOURCE_PUBLIC_PATH).read_bytes() == payload
        assert not (root / PRODUCT_INPUT_PATH).exists()
        return payload

    def runner(input_path: Path, output_path: Path) -> int:
        events.append("runner")
        assert input_path == root / PRODUCT_INPUT_PATH
        assert (root / RUN_PLAN_PATH).is_file()
        assert not (root / EXECUTION_PATH).exists()
        output_path.write_bytes(b"raw output\n")
        return 0

    execution = run_product_stage_with_preflight(
        root,
        systems_under_test=reference_systems(),
        pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(plan, stimuli),
        source_public=canonical_json_bytes(stimuli),
        adapter=adapter,
        runner=runner,
        adapter_provenance=reference_metadata().adapter,
        callable_identifier="tests.fake",
    )
    assert events == ["adapter", "runner"]
    assert execution.run_plan_digest == digest_bytes_v2(canonical_json_bytes(plan))
    assert execution.stimulus_digest == stimulus_set_digest(stimuli)


def test_preflight_rejects_unresolved_references_without_calling_adapter(
    tmp_path: Path,
) -> None:
    root = tmp_path / "run"
    called = False
    plan = reference_plan().model_copy(
        update={"authority_path_component_ids": ("component-missing",)}
    )

    def adapter(payload: bytes) -> bytes:
        nonlocal called
        called = True
        return payload

    with pytest.raises(ValueError, match="unresolved"):
        run_product_stage_with_preflight(
            root,
            systems_under_test=reference_systems(),
            pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
                plan,
                reference_stimuli(),
            ),
            source_public=canonical_json_bytes(reference_stimuli()),
            adapter=adapter,
            runner=lambda _input, _output: 0,
            adapter_provenance=reference_metadata().adapter,
            callable_identifier="tests.fake",
        )
    assert not called
    assert not root.exists()


def test_preflight_rejects_existing_root_mismatched_digest_and_adapter(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ProductStageError, match="must not already exist"):
        run_product_stage_with_preflight(
            existing,
            systems_under_test=reference_systems(),
            pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
                reference_plan(), reference_stimuli()
            ),
            source_public=canonical_json_bytes(reference_stimuli()),
            adapter=lambda payload: payload,
            runner=lambda _input, _output: 0,
            adapter_provenance=reference_metadata().adapter,
            callable_identifier="tests.fake",
        )

    bad_plan = reference_plan().model_copy(
        update={"stimulus_set_digest": DigestV2(value="f" * 64)}
    )
    with pytest.raises(ReceiptIntegrityError, match="stimulus digest"):
        run_product_stage_with_preflight(
            tmp_path / "digest",
            systems_under_test=reference_systems(),
            pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
                bad_plan, reference_stimuli()
            ),
            source_public=canonical_json_bytes(reference_stimuli()),
            adapter=lambda payload: payload,
            runner=lambda _input, _output: 0,
            adapter_provenance=reference_metadata().adapter,
            callable_identifier="tests.fake",
        )

    different = reference_stimuli().model_copy(update={"schema_version": "1.0.0"})
    different_payload = different.model_dump(mode="json")
    different_payload["stimuli"][0]["stimulus_id"] = "different"
    with pytest.raises(ReceiptIntegrityError, match="differs from preflight"):
        run_product_stage_with_preflight(
            tmp_path / "adapter",
            systems_under_test=reference_systems(),
            pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
                reference_plan(), reference_stimuli()
            ),
            source_public=canonical_json_bytes(reference_stimuli()),
            adapter=lambda _payload: canonical_json_bytes(
                AgentAuthorityStimulusSetV1.model_validate(different_payload)
            ),
            runner=lambda _input, _output: 0,
            adapter_provenance=reference_metadata().adapter,
            callable_identifier="tests.fake",
        )


def test_manifest_dispatch_and_v1_claim_separation(reference_receipt: Path) -> None:
    dispatched = validate_manifest_dispatched(reference_receipt)
    assert dispatched.schema_version == "2.0.0"
    with pytest.raises(ValueError):
        EvidenceClaim("live_lab_conformance")
    with pytest.raises(ValidationError):
        RunReceiptManifest.model_validate(
            {"schema_version": "1.0.0", "evidence_claim": "live_lab_conformance"}
        )


@pytest.mark.parametrize(
    ("stimulus_id", "updates", "status"),
    [
        (
            "stimulus-l01",
            {
                "channel_scans": [
                    {
                        "channel": "log",
                        "collection_status": "collected",
                        "canary_match": True,
                        "evidence_handle_ref": "evidence:log",
                    }
                ]
            },
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l01",
            {
                "channel_scans": [
                    {
                        "channel": "log",
                        "collection_status": "failed",
                        "canary_match": None,
                        "evidence_handle_ref": "evidence:log",
                    }
                ]
            },
            FindingStatus.INCONCLUSIVE,
        ),
        ("stimulus-l02", {"target_decision": "allow"}, FindingStatus.FAIL),
        (
            "stimulus-l02",
            {"side_effect": "occurred"},
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l02",
            {"target_decision": "unobserved", "side_effect": "unknown"},
            FindingStatus.INCONCLUSIVE,
        ),
        (
            "stimulus-l03",
            {"reachability": "reachable", "target_decision": "allow"},
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l03",
            {"side_effect": "occurred"},
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l03",
            {
                "reachability": "unknown",
                "target_decision": "unobserved",
                "side_effect": "unknown",
            },
            FindingStatus.INCONCLUSIVE,
        ),
        (
            "stimulus-l04",
            {"connectivity": "connected", "target_decision": "allow"},
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l04",
            {"side_effect": "occurred"},
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l04",
            {
                "connectivity": "unknown",
                "target_decision": "unobserved",
                "side_effect": "unknown",
            },
            FindingStatus.INCONCLUSIVE,
        ),
        (
            "stimulus-l05",
            {"fault_confirmation": "unconfirmed"},
            FindingStatus.INCONCLUSIVE,
        ),
        (
            "stimulus-l05",
            {
                "enforcement_outcomes": [
                    {
                        "component_id": "component-gateway",
                        "decision": "allow",
                        "side_effect": "occurred",
                        "evidence_refs": ["evidence:gateway"],
                    }
                ]
            },
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l05",
            {
                "enforcement_outcomes": [
                    {
                        "component_id": "component-gateway",
                        "decision": "timeout",
                        "side_effect": "occurred",
                        "evidence_refs": ["evidence:gateway"],
                    }
                ]
            },
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l06",
            {
                "point_results": [
                    {
                        "component_id": "component-gateway",
                        "ack_elapsed_ns": None,
                        "evidence_refs": ["evidence:target"],
                    }
                ]
            },
            FindingStatus.INCONCLUSIVE,
        ),
        (
            "stimulus-l06",
            {
                "point_results": [
                    {
                        "component_id": "component-gateway",
                        "ack_elapsed_ns": 11000000,
                        "evidence_refs": ["evidence:target"],
                    }
                ]
            },
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l06",
            {
                "timed_attempts": [
                    {
                        "enforcement_point_id": "component-gateway",
                        "credential_or_child_handle": "synthetic-secret:credential-1",
                        "sent_elapsed_ns": 11000000,
                        "completed_elapsed_ns": 12000000,
                        "decision": "deny",
                        "side_effect": "occurred",
                        "evidence_refs": ["evidence:target"],
                    }
                ]
            },
            FindingStatus.FAIL,
        ),
        (
            "stimulus-l05",
            {
                "enforcement_outcomes": [
                    {
                        "component_id": "component-gateway",
                        "decision": "timeout",
                        "side_effect": "unknown",
                        "evidence_refs": ["evidence:gateway"],
                    }
                ]
            },
            FindingStatus.INCONCLUSIVE,
        ),
        (
            "stimulus-l06",
            {
                "timed_attempts": [
                    {
                        "enforcement_point_id": "component-gateway",
                        "credential_or_child_handle": "synthetic-secret:credential-1",
                        "sent_elapsed_ns": 11000000,
                        "completed_elapsed_ns": 12000000,
                        "decision": "timeout",
                        "side_effect": "unknown",
                        "evidence_refs": ["evidence:target"],
                    }
                ]
            },
            FindingStatus.INCONCLUSIVE,
        ),
    ],
)
def test_security_case_outcomes_are_independent(
    stimulus_id: str,
    updates: dict[str, object],
    status: FindingStatus,
) -> None:
    observations = _replace_observation_payload(
        reference_observations(), stimulus_id, **updates
    )
    report = _evaluate(observations)
    finding = next(item for item in report.findings if item.stimulus_id == stimulus_id)
    assert finding.status is status


def test_missing_observation_is_not_executed_and_missing_evidence_is_inconclusive() -> (
    None
):
    observations = reference_observations()
    without_l02 = observations.model_copy(
        update={
            "observations": tuple(
                item
                for item in observations.observations
                if item.stimulus_id != "stimulus-l02"
            )
        }
    )
    report = _evaluate(without_l02)
    finding = next(
        item for item in report.findings if item.stimulus_id == "stimulus-l02"
    )
    assert finding.status is FindingStatus.NOT_EXECUTED
    metric = next(
        item for item in report.security_metrics if item.name == "replay_rejection_rate"
    )
    assert metric.value is None

    data = observations.model_dump(mode="json")
    for handle in data["evidence_handles"]:
        if handle["handle"] == "evidence:log":
            handle["kind"] = "trace"
    changed = AgentAuthorityRunObservationsV1.model_validate(data)
    report = _evaluate(changed)
    finding = next(
        item for item in report.findings if item.stimulus_id == "stimulus-l01"
    )
    assert finding.status is FindingStatus.INCONCLUSIVE
    assert finding.failure_code == "required_evidence_missing"


@pytest.mark.parametrize(
    "stimulus_id",
    [
        "stimulus-l01",
        "stimulus-l03",
        "stimulus-l04",
        "stimulus-l05",
        "stimulus-l06",
    ],
)
def test_every_missing_observation_has_an_explicit_metric_state(
    stimulus_id: str,
) -> None:
    observations = reference_observations()
    changed = observations.model_copy(
        update={
            "observations": tuple(
                item
                for item in observations.observations
                if item.stimulus_id != stimulus_id
            )
        }
    )
    report = _evaluate(changed)
    finding = next(item for item in report.findings if item.stimulus_id == stimulus_id)
    assert finding.status is FindingStatus.NOT_EXECUTED
    if stimulus_id == "stimulus-l06":
        false_allow = next(
            item
            for item in report.security_metrics
            if item.name == "post_bound_false_allow_rate"
        )
        assert false_allow.value is None
        assert false_allow.denominator == 0


def _replace_truth_row(index: int, **updates: object) -> AgentAuthorityLabTruthV1:
    truth = reference_truth()
    rows = list(truth.stimuli)
    rows[index] = rows[index].model_copy(update=updates)
    return truth.model_copy(update={"stimuli": tuple(rows)})


def test_truth_validation_rejects_cross_artifact_disagreement() -> None:
    plan = reference_plan()
    stimuli = reference_stimuli()
    truth = reference_truth()
    with pytest.raises(ValueError, match="truth run identifier"):
        validate_agent_authority_truth(
            plan,
            stimuli,
            truth.model_copy(update={"run_id": "different"}),
        )
    with pytest.raises(ValueError, match="truth inventory"):
        validate_agent_authority_truth(
            plan,
            stimuli,
            truth.model_copy(update={"stimuli": truth.stimuli[:-1]}),
        )
    with pytest.raises(ValueError, match="truth control"):
        validate_agent_authority_truth(
            plan,
            stimuli,
            _replace_truth_row(0, control_id=AgentAuthorityControlId.L02),
        )
    with pytest.raises(ValueError, match="truth and stimulus variants"):
        validate_agent_authority_truth(
            plan,
            stimuli,
            _replace_truth_row(0, payload=truth.stimuli[1].payload),
        )


@pytest.mark.parametrize(
    ("index", "payload", "message"),
    [
        (
            0,
            reference_truth()
            .stimuli[1]
            .payload.model_copy(update={"variant": "l01_secret_exposure"}),
            "L01 truth has the wrong typed payload",
        ),
        (
            0,
            reference_truth()
            .stimuli[0]
            .payload.model_copy(
                update={"required_channels": (EvidenceChannel.CONTEXT,)}
            ),
            "L01 truth channels",
        ),
        (
            4,
            reference_truth()
            .stimuli[1]
            .payload.model_copy(update={"variant": "l05_critical_dependency_failure"}),
            "L05 truth has the wrong typed payload",
        ),
        (
            4,
            reference_truth()
            .stimuli[4]
            .payload.model_copy(update={"enforcement_point_ids": ("different",)}),
            "L05 truth enforcement points",
        ),
        (
            5,
            reference_truth()
            .stimuli[1]
            .payload.model_copy(update={"variant": "l06_revocation_propagation"}),
            "L06 truth has the wrong typed payload",
        ),
        (
            5,
            reference_truth()
            .stimuli[5]
            .payload.model_copy(update={"enforcement_point_ids": ("different",)}),
            "L06 truth differs",
        ),
        (
            5,
            reference_truth()
            .stimuli[5]
            .payload.model_copy(update={"credential_or_child_handles": ("different",)}),
            "L06 truth differs",
        ),
        (
            5,
            reference_truth().stimuli[5].payload.model_copy(update={"bound_ns": 1}),
            "L06 truth differs",
        ),
    ],
)
def test_truth_variant_specific_contracts(
    index: int,
    payload: BaseModel,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_agent_authority_truth(
            reference_plan(),
            reference_stimuli(),
            _replace_truth_row(index, payload=payload),
        )


def test_attribution_and_channel_scan_invariants() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        ObservationAttributionV1(kind=AttributionKind.SPECIFIC)
    with pytest.raises(ValidationError, match="at least two"):
        ObservationAttributionV1(
            kind=AttributionKind.MULTIPLE,
            component_ids=("one",),
        )
    with pytest.raises(ValidationError, match="two-plus"):
        ObservationAttributionV1(
            kind=AttributionKind.AMBIGUOUS,
            component_ids=("one",),
            reason="cannot distinguish",
        )
    with pytest.raises(ValidationError, match="forbids"):
        ObservationAttributionV1(
            kind=AttributionKind.UNOBSERVED,
            reason="unexpected",
        )
    with pytest.raises(ValidationError, match="exactly when"):
        ChannelScanV1(
            channel=EvidenceChannel.LOG,
            collection_status=CollectionStatus.COLLECTED,
            canary_match=None,
            evidence_handle_ref="evidence:log",
        )


def test_managed_service_observability_branches() -> None:
    base: dict[str, object] = {
        "component_id": "managed",
        "role": "policy",
        "provider": "provider",
        "product": "product",
        "version_observability": "not_exposed",
        "replayability": "not_replayable",
        "replayability_limitation": "vendor state is unavailable",
    }

    def managed(**updates: object) -> ManagedServiceComponentProvenanceV2:
        return ManagedServiceComponentProvenanceV2.model_validate(base | updates)

    observed = managed(
        configuration_observability=ConfigurationObservabilityV2.OBSERVED,
        configuration_digest=DigestV2(value="1" * 64),
        configuration_evidence_refs=("evidence:config",),
    )
    assert observed.configuration_digest is not None
    partial = managed(
        configuration_observability=ConfigurationObservabilityV2.PARTIAL,
        configuration_digest=DigestV2(value="2" * 64),
        observed_configuration_fields=("policy",),
        configuration_evidence_refs=("evidence:config",),
        configuration_capture_limitation="only policy was visible",
    )
    assert partial.configuration_observability.value == "partial"
    hidden = managed(
        configuration_observability=ConfigurationObservabilityV2.NOT_EXPOSED,
        configuration_capture_limitation="configuration is hidden",
    )
    assert hidden.version_observability is VersionObservabilityV2.NOT_EXPOSED

    with pytest.raises(ValidationError, match="complete digest and evidence"):
        managed(
            configuration_observability="observed",
        )
    with pytest.raises(ValidationError, match="digest, fields, evidence"):
        managed(
            configuration_observability="partial",
            configuration_capture_limitation="incomplete",
        )
    with pytest.raises(ValidationError, match="forbids a digest"):
        managed(
            configuration_observability="not_exposed",
            configuration_digest=DigestV2(value="3" * 64),
            configuration_capture_limitation="hidden",
        )


def test_receipt_detects_plan_tampering(
    reference_receipt: Path, tmp_path: Path
) -> None:
    root = _copy_receipt(reference_receipt, tmp_path)
    plan = AgentAuthorityRunPlanV1.model_validate_json(
        (root / RUN_PLAN_PATH).read_bytes()
    )
    changed = plan.model_copy(update={"isolation_mechanism": "tampered"})
    payload = canonical_json_bytes(changed)
    (root / RUN_PLAN_PATH).write_bytes(payload)
    manifest = validate_manifest_dispatched(reference_receipt)
    assert manifest.schema_version == "2.0.0"
    artifacts = tuple(
        item.model_copy(
            update={"digest": digest_bytes_v2(payload), "byte_size": len(payload)}
        )
        if item.path == RUN_PLAN_PATH
        else item
        for item in manifest.artifacts
    )
    changed_manifest = manifest.model_copy(update={"artifacts": artifacts})
    (root / MANIFEST_PATH).write_bytes(canonical_json_bytes(changed_manifest))
    with pytest.raises(ReceiptIntegrityError, match="run-plan digest"):
        validate_agent_authority_run_receipt(root)


def test_real_evidence_handles_never_carry_raw_payload_fields() -> None:
    handle = reference_observations().evidence_handles[0]
    assert handle.redaction_status is RedactionStatus.NOT_REQUIRED
    with pytest.raises(ValidationError):
        type(handle).model_validate(
            handle.model_dump(mode="json") | {"raw_log_body": "secret"}
        )
    assert EvidenceKind.CREDENTIAL_STORE.value == "credential_store"
    assert ReplayabilityV2.EXACT.value == "exact"
    assert TreeState.CLEAN.value == "clean"
