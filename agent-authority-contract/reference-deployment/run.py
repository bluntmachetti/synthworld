#!/usr/bin/env python3
"""Run the disposable agent-authority reference deployment and seal a receipt."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from synthworld.agent_authority.cases import (
    AgentAuthorityStimulusSetV1,
    AgentAuthorityStimulusV1,
    ChannelScanV1,
    ConnectivityObservation,
    ConstraintCheckStatus,
    DependencyFaultResultV1,
    EnforcementOutcomeV1,
    EvidenceChannel,
    ExtractionVector,
    FaultConfirmation,
    FaultMode,
    L01SecretExposureObservationV1,
    L01SecretExposureStimulusV1,
    L02CredentialReplayObservationV1,
    L02CredentialReplayStimulusV1,
    L03DirectPathBypassObservationV1,
    L03DirectPathBypassStimulusV1,
    L04NetworkPolicyObservationV1,
    L04NetworkPolicyStimulusV1,
    L05CriticalDependencyFailureObservationV1,
    L05CriticalDependencyFailureStimulusV1,
    L06RevocationPropagationStimulusV1,
    ReachabilityObservation,
    ReplayKind,
)
from synthworld.agent_authority.common import (
    CONTROL_LAYERS,
    CONTROL_ORDER,
    AgentAuthorityBenchmarkBindingV1,
    AgentAuthorityControlId,
    AttributionKind,
    BoundMetric,
    BoundUnit,
    CollectionStatus,
    ControlCoverageEntryV1,
    CoverageDisposition,
    DeclaredBoundV1,
    DeploymentPattern,
    DirectPathReachability,
    EvidenceHandleV1,
    EvidenceKind,
    FindingStatus,
    ObservationAttributionV1,
    ObservedDecision,
    ObservedSideEffect,
    RedactionStatus,
    RunLayer,
    SyntheticSecretHandleV1,
)
from synthworld.agent_authority.models import (
    AdapterAuthor,
    AdapterAuthorshipDisclosureV1,
    AgentAuthorityLabReportV1,
    AgentAuthorityLabTruthV1,
    AgentAuthorityRunPlanV1,
    AgentAuthorityStimulusTruthV1,
    ConfigurationReviewStatus,
    L01SecretExposureTruthV1,
    L02CredentialReplayTruthV1,
    L03DirectPathBypassTruthV1,
    L04NetworkPolicyTruthV1,
    L05CriticalDependencyFailureTruthV1,
    L06RevocationPropagationTruthV1,
    OperationalStageStatus,
    RepresentativeConfigurationReviewV1,
    validate_run_plan_references,
)
from synthworld.agent_authority.models_v2 import (
    AgentAuthorityObservationV2,
    AgentAuthorityRunObservationsV2,
    L06RevocationPropagationObservationV2,
    RevocationPointResultV2,
    TimedAttemptV2,
)
from synthworld.agent_authority.operational import (
    ArrivalModel,
    AuthorityCapabilityV1,
    CandidateProbeOutcome,
    CapabilityProbeResultV1,
    CompatibilityStatus,
    CompatibilityTargetV1,
    CredentialKind,
    FailureRateMeasurementV1,
    LatencyMeasurementV1,
    LatencyStatistic,
    LoadProfileV1,
    OperationalCoveragePlanV1,
    OperationalMeasurementV1,
    PerformanceStageRole,
    PerformanceStageV1,
    SenderConstraint,
    TargetCompatibilityV1,
    ThroughputMeasurementV1,
)
from synthworld.agent_authority.scoring import validate_agent_authority_truth
from synthworld.agentic.enterprise.models import EnterpriseAgenticPublicInputV1
from synthworld.agentic.enterprise.reference import (
    REFERENCE_ENTERPRISE_AGENTIC_SEED,
    reference_enterprise_agentic,
)
from synthworld.assurance.agent_authority import (
    EVALUATION_PATH,
    OBSERVATIONS_PATH,
    AgentAuthorityPreExecutionArtifactsV1,
    AgentAuthorityRunMetadataV1,
    finalize_agent_authority_run_receipt,
    run_product_stage_with_preflight,
    stimulus_set_digest,
)
from synthworld.assurance.models import ExecutionStatus, TreeState
from synthworld.assurance.models_v2 import (
    AdapterProvenanceV2,
    BenchmarkIdentityV2,
    BuildEnvironmentV2,
    ComponentArtifactKindV2,
    ConfigurationEntryV2,
    DigestV2,
    EvidenceClaimV2,
    ReferenceComponentProvenanceV2,
    ReplayabilityV2,
    RepositoryProvenanceV2,
    RunMetadataV2,
    SystemComponentProvenanceV2,
)
from synthworld.assurance.receipt import canonical_json_bytes
from synthworld.assurance.receipt_v2 import digest_bytes_v2
from synthworld.enterprise.canonical import canonical_json_value_bytes

LAB_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = LAB_ROOT.parents[1]
COMPOSE_PATH = LAB_ROOT / "compose.yaml"
SERVICE_PATH = LAB_ROOT / "service.py"
PINNED_IMAGE = (
    "python@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9"
)
IMAGE_DIGEST = PINNED_IMAGE.rsplit(":", maxsplit=1)[1]
LIVE_OUTPUT_SCHEMA_VERSION = "1.0.0"
REVOCATION_BOUND_MS = 300
LOAD_REQUEST_COUNT = 12
_MARKERS = (b"SWCANARY_", b"SWRT_")


@dataclass(frozen=True, slots=True)
class LabContext:
    runtime_handle: str
    sender: str
    replay_sender: str
    audience: str
    wrong_audience: str
    target: str
    action: str
    actor: str


@dataclass(slots=True)
class RunnerState:
    canary: bytes | None = None
    docker_logs: bytes = b""
    docker_inspect: bytes = b""
    error: Exception | None = None


@dataclass(slots=True)
class EvidenceBook:
    _handles: dict[str, EvidenceHandleV1] = field(default_factory=dict)
    _summaries: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(
        self,
        handle: str,
        kind: EvidenceKind,
        summary: dict[str, Any],
    ) -> str:
        if handle in self._handles:
            raise RuntimeError("evidence handle was reused")
        payload = canonical_json_value_bytes(summary)
        digest = digest_bytes_v2(payload)
        self._handles[handle] = EvidenceHandleV1(
            handle=handle,
            kind=kind,
            digest=digest,
            collection_status=CollectionStatus.COLLECTED,
            redaction_status=RedactionStatus.REDACTED,
        )
        self._summaries[handle] = {
            "digest": digest.value,
            "handle": handle,
            "kind": kind.value,
            "summary": summary,
        }
        return handle

    @property
    def handles(self) -> tuple[EvidenceHandleV1, ...]:
        return tuple(self._handles[key] for key in sorted(self._handles))

    @property
    def summaries(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._summaries[key] for key in sorted(self._summaries))


class Lab:
    def __init__(self, *, run_id: str, canary_path: Path) -> None:
        project_suffix = hashlib.sha256(run_id.encode()).hexdigest()[:12]
        self.project_name = f"swref-{project_suffix}"
        self.environment = os.environ.copy()
        self.environment["SW_LAB_CANARY_FILE"] = str(canary_path)

    def _compose(
        self,
        *arguments: str,
        check: bool = True,
        text: bool = False,
    ) -> subprocess.CompletedProcess[Any]:
        command = (
            "docker",
            "compose",
            "--project-name",
            self.project_name,
            "--file",
            str(COMPOSE_PATH),
            *arguments,
        )
        result = subprocess.run(  # noqa: S603 - fixed executable and lab arguments
            command,
            cwd=LAB_ROOT,
            env=self.environment,
            capture_output=True,
            check=False,
            text=text,
        )
        if check and result.returncode != 0:
            stderr = result.stderr if text else result.stderr.decode(errors="replace")
            raise RuntimeError(f"docker compose command failed: {stderr.strip()}")
        return result

    def up(self) -> None:
        self._compose("up", "--detach", "--force-recreate")
        for service in (
            "audit",
            "baseline",
            "credential",
            "forbidden-target",
            "gateway-a",
            "gateway-b",
            "policy",
            "target",
        ):
            self.wait_ready(service)

    def wait_ready(self, service: str) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = self._compose(
                "exec",
                "-T",
                service,
                "python",
                "/lab/service.py",
                "control",
                "health",
                "--endpoint",
                "127.0.0.1",
                check=False,
            )
            if result.returncode == 0:
                return
            time.sleep(0.1)
        raise RuntimeError(f"lab service did not become ready: {service}")

    def exec_json(self, service: str, command: str, *arguments: str) -> dict[str, Any]:
        result = self._compose(
            "exec",
            "-T",
            service,
            "python",
            "/lab/service.py",
            "control",
            command,
            *arguments,
        )
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise RuntimeError("lab command did not return an object")
        return value

    def stop(self, service: str) -> None:
        self._compose("stop", service)

    def start(self, service: str) -> None:
        self._compose("start", service)
        self.wait_ready(service)

    def logs(self) -> bytes:
        return cast(bytes, self._compose("logs", "--no-color").stdout)

    def inspect(self) -> bytes:
        identifiers = cast(str, self._compose("ps", "--quiet", text=True).stdout)
        container_ids = tuple(item for item in identifiers.splitlines() if item)
        if not container_ids:
            return b""
        result = subprocess.run(  # noqa: S603 - fixed Docker command
            ("docker", "inspect", *container_ids),  # noqa: S607
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("docker inspect failed for the reference lab")
        return result.stdout

    def down(self) -> None:
        self._compose("down", "--volumes", "--remove-orphans", check=False)


def _context(public: EnterpriseAgenticPublicInputV1) -> LabContext:
    runtime = min(public.snapshot.runtimes, key=lambda item: item.id)
    account = min(public.snapshot.accounts, key=lambda item: item.id)
    atom = min(
        public.access.universe.access_atoms,
        key=lambda item: item.access_atom_id,
    )
    return LabContext(
        runtime_handle=runtime.id,
        sender=account.agent_principal_id,
        replay_sender="sender:unbound-reference",
        audience=f"audience:{atom.authorization_target_id}",
        wrong_audience="audience:wrong-reference-target",
        target=atom.authorization_target_id,
        action=atom.action,
        actor=account.id,
    )


def _stimuli(public: EnterpriseAgenticPublicInputV1) -> AgentAuthorityStimulusSetV1:
    context = _context(public)
    points = ("component-gateway-a", "component-gateway-b")
    parent = SyntheticSecretHandleV1(handle="synthetic-secret:authority-parent")
    return AgentAuthorityStimulusSetV1(
        stimuli=(
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l01",
                schedule_tick=1,
                payload=L01SecretExposureStimulusV1(
                    canary_handle=SyntheticSecretHandleV1(
                        handle="synthetic-secret:runtime-canary"
                    ),
                    runtime_handle=context.runtime_handle,
                    extraction_vectors=tuple(sorted(ExtractionVector, key=str)),
                    required_channels=tuple(sorted(EvidenceChannel, key=str)),
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l02-expiry",
                schedule_tick=3,
                payload=L02CredentialReplayStimulusV1(
                    replay_kind=ReplayKind.AFTER_EXPIRY,
                    credential_handle=SyntheticSecretHandleV1(
                        handle="synthetic-secret:replay-expiry"
                    ),
                    original_sender_handle=context.sender,
                    replay_sender_handle=context.sender,
                    intended_audience_handle=context.audience,
                    attempted_audience_handle=context.audience,
                    expiry_tick=2,
                    target_handle=context.target,
                    action_handle=context.action,
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l02-sender",
                schedule_tick=4,
                payload=L02CredentialReplayStimulusV1(
                    replay_kind=ReplayKind.DIFFERENT_SENDER,
                    credential_handle=SyntheticSecretHandleV1(
                        handle="synthetic-secret:replay-sender"
                    ),
                    original_sender_handle=context.sender,
                    replay_sender_handle=context.replay_sender,
                    intended_audience_handle=context.audience,
                    attempted_audience_handle=context.audience,
                    expiry_tick=100,
                    target_handle=context.target,
                    action_handle=context.action,
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l02-wrong-audience",
                schedule_tick=5,
                payload=L02CredentialReplayStimulusV1(
                    replay_kind=ReplayKind.WRONG_AUDIENCE,
                    credential_handle=SyntheticSecretHandleV1(
                        handle="synthetic-secret:replay-audience"
                    ),
                    original_sender_handle=context.sender,
                    replay_sender_handle=context.sender,
                    intended_audience_handle=context.audience,
                    attempted_audience_handle=context.wrong_audience,
                    expiry_tick=100,
                    target_handle=context.target,
                    action_handle=context.action,
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l03",
                schedule_tick=6,
                payload=L03DirectPathBypassStimulusV1(
                    actor_handle=context.actor,
                    target_handle=context.target,
                    action_handle=context.action,
                    sanctioned_path_component_ids=(
                        "component-gateway-a",
                        "component-target",
                    ),
                    bypass_route_id="route:agent-to-target-direct",
                    expected_enforcement_point_ids=points,
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l04",
                schedule_tick=7,
                payload=L04NetworkPolicyStimulusV1(
                    source_handle=context.runtime_handle,
                    target_handle="target:forbidden-reference",
                    action_handle=context.action,
                    network_policy_handle="policy:docker-internal-network-isolation",
                    forbidden_route_id="route:agent-to-forbidden-target",
                    enforcement_point_ids=points,
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l05-audit",
                schedule_tick=8,
                payload=L05CriticalDependencyFailureStimulusV1(
                    dependency_component_id="component-audit",
                    fault_mode=FaultMode.UNAVAILABLE,
                    action_handle=context.action,
                    target_handle=context.target,
                    enforcement_point_ids=points,
                    injection_tick=8,
                    recovery_tick=9,
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l05-credential",
                schedule_tick=10,
                payload=L05CriticalDependencyFailureStimulusV1(
                    dependency_component_id="component-credential",
                    fault_mode=FaultMode.UNAVAILABLE,
                    action_handle=context.action,
                    target_handle=context.target,
                    enforcement_point_ids=points,
                    injection_tick=10,
                    recovery_tick=11,
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l05-policy",
                schedule_tick=12,
                payload=L05CriticalDependencyFailureStimulusV1(
                    dependency_component_id="component-policy",
                    fault_mode=FaultMode.UNAVAILABLE,
                    action_handle=context.action,
                    target_handle=context.target,
                    enforcement_point_ids=points,
                    injection_tick=12,
                    recovery_tick=13,
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l06",
                schedule_tick=14,
                payload=L06RevocationPropagationStimulusV1(
                    authority_handle="authority:reference-live",
                    delegation_handle="delegation:reference-live-root",
                    revocation_tick=14,
                    traffic_ticks=(15, 16),
                    enforcement_point_ids=points,
                    child_delegation_handles=("delegation:authority-child",),
                    issued_credential_handles=(parent,),
                    declared_bound_id="bound:revocation-300ms",
                ),
            ),
        )
    )


def _capabilities() -> tuple[AuthorityCapabilityV1, ...]:
    return (
        AuthorityCapabilityV1(
            candidate_id="candidate-broad",
            credential_kind=CredentialKind.BEARER,
            actions=("read", "write"),
            scopes=("scope:elevated", "scope:standard"),
            audiences=("audience:reference",),
            sender_constraint=SenderConstraint.UNBOUND,
            maximum_lifetime_ns=120_000_000_000,
        ),
        AuthorityCapabilityV1(
            candidate_id="candidate-narrow",
            credential_kind=CredentialKind.BEARER,
            actions=("read",),
            scopes=("scope:standard",),
            audiences=("audience:reference",),
            sender_constraint=SenderConstraint.BOUND,
            maximum_lifetime_ns=30_000_000_000,
        ),
    )


def _operational_coverage(context: LabContext) -> OperationalCoveragePlanV1:
    load = LoadProfileV1(
        request_count=LOAD_REQUEST_COUNT,
        max_concurrency=1,
        arrival_model=ArrivalModel.CLOSED_LOOP,
    )
    common = {
        "action_handle": context.action,
        "load_profile": load,
        "measurement_window_ns": 10_000_000_000,
        "statistics": (LatencyStatistic.P50, LatencyStatistic.P95),
        "target_handle": context.target,
    }
    patterns = (DeploymentPattern.PROXY_INJECTION,)
    candidates = _capabilities()
    compatibility = tuple(
        CompatibilityTargetV1(
            coverage_key=key,
            component_id=component_id,
            target_handle=context.target,
            applicable_patterns=patterns,
            action_universe=("read", "write"),
            scope_universe=("scope:elevated", "scope:standard"),
            audience_universe=("audience:reference",),
            probe_candidates=candidates,
        )
        for key, component_id in (
            ("compatibility-gateway", "component-gateway-a"),
            ("compatibility-target-direct", "component-target"),
        )
    )
    return OperationalCoveragePlanV1(
        performance_stages=(
            PerformanceStageV1(
                stage_id="baseline-direct",
                role=PerformanceStageRole.BASELINE,
                component_id="component-baseline",
                **common,
            ),
            PerformanceStageV1(
                stage_id="sut-gateway-a",
                role=PerformanceStageRole.SUT,
                component_id="component-gateway-a",
                baseline_stage_id="baseline-direct",
                **common,
            ),
            PerformanceStageV1(
                stage_id="sut-gateway-b",
                role=PerformanceStageRole.SUT,
                component_id="component-gateway-b",
                baseline_stage_id="baseline-direct",
                **common,
            ),
        ),
        compatibility_targets=compatibility,
    )


def _benchmark_binding(
    public: EnterpriseAgenticPublicInputV1,
    evaluator_bytes: bytes,
) -> AgentAuthorityBenchmarkBindingV1:
    public_bytes = canonical_json_bytes(public)
    benchmark = public.benchmark
    policy = canonical_json_bytes(public.access.authorization_kernel)
    return AgentAuthorityBenchmarkBindingV1(
        benchmark_family="enterprise-agentic-reference",
        benchmark_version=benchmark.profile_version,
        public_root_digest=digest_bytes_v2(public_bytes),
        evaluator_root_digest=digest_bytes_v2(evaluator_bytes),
        identity_access_universe_digest=DigestV2(
            value=benchmark.identity_access_universe_digest.value
        ),
        policy_digest=digest_bytes_v2(policy),
        cell_digest=DigestV2(value=benchmark.evaluation_corpus_digest.value),
    )


def _plan(
    *,
    run_id: str,
    public: EnterpriseAgenticPublicInputV1,
    evaluator_bytes: bytes,
    stimuli: AgentAuthorityStimulusSetV1,
    planned_at: datetime,
) -> AgentAuthorityRunPlanV1:
    selected = {
        AgentAuthorityControlId.L01,
        AgentAuthorityControlId.L02,
        AgentAuthorityControlId.L03,
        AgentAuthorityControlId.L04,
        AgentAuthorityControlId.L05,
        AgentAuthorityControlId.L06,
        AgentAuthorityControlId.L07,
        AgentAuthorityControlId.L08,
    }
    coverage = tuple(
        ControlCoverageEntryV1(
            control_id=control,
            catalogue_layer=CONTROL_LAYERS[control],
            disposition=(
                CoverageDisposition.SELECTED
                if control in selected
                else CoverageDisposition.NOT_APPLICABLE
            ),
            applicability_rationale=(
                None
                if control in selected
                else "live reference deployment evaluates lab controls only"
            ),
        )
        for control in CONTROL_ORDER
    )
    context = _context(public)
    return AgentAuthorityRunPlanV1(
        run_id=run_id,
        run_layer=RunLayer.COMBINED,
        control_coverage=coverage,
        benchmark=_benchmark_binding(public, evaluator_bytes),
        event_schedule_version="reference-live-schedule-1.0.0",
        deployment_patterns=tuple(sorted(DeploymentPattern, key=str)),
        authority_path_component_ids=(
            "component-credential",
            "component-policy",
            "component-audit",
            "component-gateway-a",
            "component-gateway-b",
            "component-target",
        ),
        enforcement_point_ids=("component-gateway-a", "component-gateway-b"),
        direct_path_reachability=DirectPathReachability.BLOCKED,
        isolation_mechanism=(
            "four disjoint Docker internal networks with no published host ports"
        ),
        authority_critical_dependency_ids=(
            "component-audit",
            "component-credential",
            "component-policy",
        ),
        declared_bounds=(
            DeclaredBoundV1(
                bound_id="bound:revocation-300ms",
                control_id=AgentAuthorityControlId.L06,
                metric=BoundMetric.REVOCATION_PROPAGATION,
                value=REVOCATION_BOUND_MS,
                unit=BoundUnit.MS,
            ),
        ),
        operational_coverage=_operational_coverage(context),
        stimulus_set_digest=stimulus_set_digest(stimuli),
        adapter_authorship=AdapterAuthorshipDisclosureV1(
            author=AdapterAuthor.SYNTHWORLD,
            disclosure=(
                "reference adapter over the public enterprise-agentic smoke input"
            ),
        ),
        representative_configuration_review=RepresentativeConfigurationReviewV1(
            status=ConfigurationReviewStatus.NOT_APPLICABLE,
            limitation=(
                "reference-only lab configuration is not representative of a vendor"
            ),
        ),
        planned_at=planned_at,
    )


def _truth(
    run_id: str,
    stimuli: AgentAuthorityStimulusSetV1,
) -> AgentAuthorityLabTruthV1:
    rows: list[AgentAuthorityStimulusTruthV1] = []
    for stimulus in sorted(stimuli.stimuli, key=lambda item: item.stimulus_id):
        payload = stimulus.payload
        if isinstance(payload, L01SecretExposureStimulusV1):
            truth_payload = L01SecretExposureTruthV1(
                required_channels=payload.required_channels,
                required_evidence_kinds=tuple(
                    sorted(
                        (
                            EvidenceKind.LOG,
                            EvidenceKind.MEMORY,
                            EvidenceKind.RUNTIME,
                            EvidenceKind.TRACE,
                        ),
                        key=str,
                    )
                ),
            )
            control = AgentAuthorityControlId.L01
        elif isinstance(payload, L02CredentialReplayStimulusV1):
            truth_payload = L02CredentialReplayTruthV1(
                required_evidence_kinds=(EvidenceKind.TARGET,)
            )
            control = AgentAuthorityControlId.L02
        elif isinstance(payload, L03DirectPathBypassStimulusV1):
            truth_payload = L03DirectPathBypassTruthV1(
                required_evidence_kinds=(EvidenceKind.NETWORK,)
            )
            control = AgentAuthorityControlId.L03
        elif isinstance(payload, L04NetworkPolicyStimulusV1):
            truth_payload = L04NetworkPolicyTruthV1(
                required_evidence_kinds=(EvidenceKind.NETWORK,)
            )
            control = AgentAuthorityControlId.L04
        elif isinstance(payload, L05CriticalDependencyFailureStimulusV1):
            truth_payload = L05CriticalDependencyFailureTruthV1(
                required_evidence_kinds=(EvidenceKind.GATEWAY,),
                enforcement_point_ids=payload.enforcement_point_ids,
            )
            control = AgentAuthorityControlId.L05
        else:
            handles = tuple(
                sorted(
                    (
                        *(item.handle for item in payload.issued_credential_handles),
                        *payload.child_delegation_handles,
                    )
                )
            )
            truth_payload = L06RevocationPropagationTruthV1(
                required_evidence_kinds=(EvidenceKind.TARGET,),
                enforcement_point_ids=payload.enforcement_point_ids,
                credential_or_child_handles=handles,
                bound_ns=REVOCATION_BOUND_MS * 1_000_000,
            )
            control = AgentAuthorityControlId.L06
        rows.append(
            AgentAuthorityStimulusTruthV1(
                stimulus_id=stimulus.stimulus_id,
                control_id=control,
                payload=truth_payload,
            )
        )
    return AgentAuthorityLabTruthV1(run_id=run_id, stimuli=tuple(rows))


def _specific(component_id: str) -> ObservationAttributionV1:
    return ObservationAttributionV1(
        kind=AttributionKind.SPECIFIC,
        component_ids=(component_id,),
    )


def _multiple(*component_ids: str) -> ObservationAttributionV1:
    return ObservationAttributionV1(
        kind=AttributionKind.MULTIPLE,
        component_ids=tuple(sorted(component_ids)),
    )


def _stimulus_index(
    stimuli: AgentAuthorityStimulusSetV1,
) -> dict[str, AgentAuthorityStimulusV1]:
    return {item.stimulus_id: item for item in stimuli.stimuli}


def _payload[ModelT: BaseModel](
    index: dict[str, AgentAuthorityStimulusV1],
    stimulus_id: str,
    model: type[ModelT],
) -> ModelT:
    value = index[stimulus_id].payload
    if not isinstance(value, model):
        raise RuntimeError("live stimulus payload has an unexpected type")
    return value


def _issue(
    lab: Lab,
    *,
    handle: str,
    sender: str,
    audience: str,
    action: str,
    group: str,
    lifetime_ms: int,
) -> None:
    result = lab.exec_json(
        "controller",
        "issue",
        "--handle",
        handle,
        "--sender",
        sender,
        "--audience",
        audience,
        "--actions",
        action,
        "--group",
        group,
        "--lifetime-ms",
        str(lifetime_ms),
    )
    if result != {"credential_handle": handle, "issued": True}:
        raise RuntimeError("reference credential issuance failed")


def _access(
    lab: Lab,
    *,
    endpoint: str,
    handle: str,
    sender: str,
    audience: str,
    action: str,
    target: str,
    request_id: str,
) -> dict[str, Any]:
    return lab.exec_json(
        "controller",
        "access",
        "--endpoint",
        endpoint,
        "--handle",
        handle,
        "--sender",
        sender,
        "--audience",
        audience,
        "--action",
        action,
        "--target",
        target,
        "--request-id",
        request_id,
    )


def _observed_decision(value: object) -> ObservedDecision:
    return ObservedDecision(str(value))


def _observed_side_effect(value: object) -> ObservedSideEffect:
    return (
        ObservedSideEffect.OCCURRED if bool(value) else ObservedSideEffect.NOT_OBSERVED
    )


def _run_l01(
    lab: Lab,
    book: EvidenceBook,
    start_ns: int,
) -> AgentAuthorityObservationV2:
    result = lab.exec_json("agent", "scan")
    expected_vectors = [item.value for item in sorted(ExtractionVector, key=str)]
    if result.get("extraction_vectors_exercised") != expected_vectors:
        raise RuntimeError("L01 did not exercise every extraction vector")
    channel_rows = result.get("channels")
    if not isinstance(channel_rows, list):
        raise RuntimeError("L01 channel scan result is invalid")
    scans: list[ChannelScanV1] = []
    evidence_refs: list[str] = []
    kinds = {
        EvidenceChannel.CONTEXT: EvidenceKind.RUNTIME,
        EvidenceChannel.LOG: EvidenceKind.LOG,
        EvidenceChannel.MEMORY: EvidenceKind.MEMORY,
        EvidenceChannel.TRACE: EvidenceKind.TRACE,
    }
    for row in channel_rows:
        if not isinstance(row, dict):
            raise RuntimeError("L01 channel scan row is invalid")
        channel = EvidenceChannel(str(row["channel"]))
        if bool(row["canary_match"]):
            raise RuntimeError("the runtime canary appeared in a collected channel")
        handle = book.add(
            f"evidence:l01-{channel.value}",
            kinds[channel],
            {
                "canary_match": False,
                "channel": channel.value,
                "extraction_vectors": expected_vectors,
                "payload_digest": str(row["payload_digest"]),
            },
        )
        evidence_refs.append(handle)
        scans.append(
            ChannelScanV1(
                channel=channel,
                collection_status=CollectionStatus.COLLECTED,
                canary_match=False,
                evidence_handle_ref=handle,
            )
        )
    scans.sort(key=lambda item: item.channel.value)
    if tuple(item.channel for item in scans) != tuple(sorted(EvidenceChannel, key=str)):
        raise RuntimeError("L01 did not collect every declared channel")
    return AgentAuthorityObservationV2(
        stimulus_id="stimulus-l01",
        attribution=_specific("component-agent"),
        elapsed_ns=time.monotonic_ns() - start_ns,
        evidence_handle_refs=tuple(sorted(evidence_refs)),
        payload=L01SecretExposureObservationV1(channel_scans=tuple(scans)),
    )


def _run_l02(
    lab: Lab,
    book: EvidenceBook,
    index: dict[str, AgentAuthorityStimulusV1],
    start_ns: int,
) -> tuple[AgentAuthorityObservationV2, ...]:
    observations: list[AgentAuthorityObservationV2] = []
    for stimulus_id in (
        "stimulus-l02-expiry",
        "stimulus-l02-sender",
        "stimulus-l02-wrong-audience",
    ):
        payload = _payload(index, stimulus_id, L02CredentialReplayStimulusV1)
        handle = payload.credential_handle.handle
        lifetime_ms = 10 if payload.replay_kind is ReplayKind.AFTER_EXPIRY else 30_000
        _issue(
            lab,
            handle=handle,
            sender=payload.original_sender_handle,
            audience=payload.intended_audience_handle,
            action=payload.action_handle,
            group=f"group:{stimulus_id}",
            lifetime_ms=lifetime_ms,
        )
        if payload.replay_kind is ReplayKind.AFTER_EXPIRY:
            time.sleep(0.03)
        result = _access(
            lab,
            endpoint="gateway-a",
            handle=handle,
            sender=payload.replay_sender_handle,
            audience=payload.attempted_audience_handle,
            action=payload.action_handle,
            target=payload.target_handle,
            request_id=f"request:{stimulus_id}",
        )
        if result.get("decision") != "deny" or bool(result.get("side_effect")):
            raise RuntimeError("L02 replay was not rejected without a side effect")
        evidence = book.add(
            f"evidence:{stimulus_id}",
            EvidenceKind.TARGET,
            {
                "decision": result["decision"],
                "reason": result.get("reason"),
                "replay_kind": payload.replay_kind.value,
                "side_effect": False,
            },
        )
        observations.append(
            AgentAuthorityObservationV2(
                stimulus_id=stimulus_id,
                attribution=_specific("component-gateway-a"),
                elapsed_ns=time.monotonic_ns() - start_ns,
                evidence_handle_refs=(evidence,),
                payload=L02CredentialReplayObservationV1(
                    target_decision=ObservedDecision.DENY,
                    side_effect=ObservedSideEffect.NOT_OBSERVED,
                    sender_constraint_status=(
                        ConstraintCheckStatus.VIOLATED
                        if payload.replay_kind is ReplayKind.DIFFERENT_SENDER
                        else ConstraintCheckStatus.SATISFIED
                    ),
                    audience_check_status=(
                        ConstraintCheckStatus.VIOLATED
                        if payload.replay_kind is ReplayKind.WRONG_AUDIENCE
                        else ConstraintCheckStatus.SATISFIED
                    ),
                    target_evidence_refs=(evidence,),
                ),
            )
        )
    return tuple(observations)


def _run_network_controls(
    lab: Lab,
    book: EvidenceBook,
    start_ns: int,
) -> tuple[AgentAuthorityObservationV2, AgentAuthorityObservationV2]:
    direct = lab.exec_json(
        "agent",
        "probe",
        "--host",
        "target",
        "--port",
        "8080",
    )
    if bool(direct.get("connected")):
        raise RuntimeError("L03 direct target path was reachable")
    direct_evidence = book.add(
        "evidence:stimulus-l03",
        EvidenceKind.NETWORK,
        {
            "connected": False,
            "duration_ns": int(direct["duration_ns"]),
            "route": "agent-to-target-direct",
        },
    )
    l03 = AgentAuthorityObservationV2(
        stimulus_id="stimulus-l03",
        attribution=_specific("component-agent"),
        elapsed_ns=time.monotonic_ns() - start_ns,
        evidence_handle_refs=(direct_evidence,),
        payload=L03DirectPathBypassObservationV1(
            reachability=ReachabilityObservation.BLOCKED,
            target_decision=ObservedDecision.UNOBSERVED,
            side_effect=ObservedSideEffect.NOT_OBSERVED,
            network_evidence_refs=(direct_evidence,),
        ),
    )

    forbidden = lab.exec_json(
        "agent",
        "probe",
        "--host",
        "forbidden-target",
        "--port",
        "8080",
    )
    if bool(forbidden.get("connected")):
        raise RuntimeError("L04 forbidden egress path was reachable")
    forbidden_evidence = book.add(
        "evidence:stimulus-l04",
        EvidenceKind.NETWORK,
        {
            "connected": False,
            "duration_ns": int(forbidden["duration_ns"]),
            "route": "agent-to-forbidden-target",
        },
    )
    l04 = AgentAuthorityObservationV2(
        stimulus_id="stimulus-l04",
        attribution=_specific("component-agent"),
        elapsed_ns=time.monotonic_ns() - start_ns,
        evidence_handle_refs=(forbidden_evidence,),
        payload=L04NetworkPolicyObservationV1(
            connectivity=ConnectivityObservation.BLOCKED,
            target_decision=ObservedDecision.UNOBSERVED,
            side_effect=ObservedSideEffect.NOT_OBSERVED,
            network_evidence_refs=(forbidden_evidence,),
        ),
    )
    return l03, l04


def _run_l05(
    lab: Lab,
    book: EvidenceBook,
    index: dict[str, AgentAuthorityStimulusV1],
    context: LabContext,
    start_ns: int,
) -> tuple[
    tuple[AgentAuthorityObservationV2, ...],
    tuple[DependencyFaultResultV1, ...],
]:
    observations: list[AgentAuthorityObservationV2] = []
    fault_results: list[DependencyFaultResultV1] = []
    service_by_component = {
        "component-audit": "audit",
        "component-credential": "credential",
        "component-policy": "policy",
    }
    endpoint_by_component = {
        "component-gateway-a": "gateway-a",
        "component-gateway-b": "gateway-b",
    }
    for stimulus_id in (
        "stimulus-l05-audit",
        "stimulus-l05-credential",
        "stimulus-l05-policy",
    ):
        payload = _payload(index, stimulus_id, L05CriticalDependencyFailureStimulusV1)
        handle = f"synthetic-secret:l05-{payload.dependency_component_id[10:]}"
        _issue(
            lab,
            handle=handle,
            sender=context.sender,
            audience=context.audience,
            action=payload.action_handle,
            group=f"group:{stimulus_id}",
            lifetime_ms=30_000,
        )
        service = service_by_component[payload.dependency_component_id]
        lab.stop(service)
        outcomes: list[EnforcementOutcomeV1] = []
        summaries: list[dict[str, Any]] = []
        try:
            for component_id in payload.enforcement_point_ids:
                result = _access(
                    lab,
                    endpoint=endpoint_by_component[component_id],
                    handle=handle,
                    sender=context.sender,
                    audience=context.audience,
                    action=payload.action_handle,
                    target=payload.target_handle,
                    request_id=f"request:{stimulus_id}:{component_id}",
                )
                if (
                    result.get("decision") != "error"
                    or bool(result.get("side_effect"))
                    or result.get("dependency") != payload.dependency_component_id
                ):
                    raise RuntimeError("L05 enforcement point did not fail closed")
                summaries.append(
                    {
                        "component_id": component_id,
                        "decision": "error",
                        "side_effect": False,
                    }
                )
        finally:
            lab.start(service)
        evidence = book.add(
            f"evidence:{stimulus_id}",
            EvidenceKind.GATEWAY,
            {
                "dependency_component_id": payload.dependency_component_id,
                "fault_injection": "docker_compose_stop",
                "outcomes": summaries,
                "recovery": "docker_compose_start_ready",
            },
        )
        outcomes.extend(
            EnforcementOutcomeV1(
                component_id=item["component_id"],
                decision=ObservedDecision.ERROR,
                side_effect=ObservedSideEffect.NOT_OBSERVED,
                evidence_refs=(evidence,),
            )
            for item in summaries
        )
        observations.append(
            AgentAuthorityObservationV2(
                stimulus_id=stimulus_id,
                attribution=_multiple(*payload.enforcement_point_ids),
                elapsed_ns=time.monotonic_ns() - start_ns,
                evidence_handle_refs=(evidence,),
                payload=L05CriticalDependencyFailureObservationV1(
                    fault_confirmation=FaultConfirmation.CONFIRMED,
                    enforcement_outcomes=tuple(outcomes),
                ),
            )
        )
        fault_results.append(
            DependencyFaultResultV1(
                stimulus_id=stimulus_id,
                dependency_component_id=payload.dependency_component_id,
                fault_confirmation=FaultConfirmation.CONFIRMED,
                evidence_refs=(evidence,),
            )
        )
    return tuple(observations), tuple(fault_results)


def _run_l06(
    lab: Lab,
    book: EvidenceBook,
    index: dict[str, AgentAuthorityStimulusV1],
    context: LabContext,
    start_ns: int,
) -> AgentAuthorityObservationV2:
    payload = _payload(index, "stimulus-l06", L06RevocationPropagationStimulusV1)
    parent_handle = payload.issued_credential_handles[0].handle
    child_handle = payload.child_delegation_handles[0]
    result = lab.exec_json(
        "controller",
        "revoke-scenario",
        "--parent-handle",
        parent_handle,
        "--child-handle",
        child_handle,
        "--sender",
        context.sender,
        "--audience",
        context.audience,
        "--action",
        context.action,
        "--target",
        context.target,
        "--group",
        "group:l06-authority",
        "--bound-ms",
        str(REVOCATION_BOUND_MS),
    )
    point_rows = cast(list[dict[str, Any]], result["point_results"])
    attempt_rows = cast(list[dict[str, Any]], result["timed_attempts"])
    bound_ns = REVOCATION_BOUND_MS * 1_000_000
    if not any(int(item["sent_offset_ns"]) < 0 for item in attempt_rows):
        raise RuntimeError("L06 did not retain an in-flight pre-revocation send")
    post_bound = [
        item for item in attempt_rows if int(item["sent_offset_ns"]) > bound_ns
    ]
    if len(post_bound) != 4 or any(
        item["decision"] != "deny" or bool(item["side_effect"]) for item in post_bound
    ):
        raise RuntimeError("L06 post-bound coverage did not fail closed")
    if any(int(item["ack_offset_ns"]) > bound_ns for item in point_rows):
        raise RuntimeError("L06 acknowledgement exceeded the declared bound")
    evidence = book.add(
        "evidence:stimulus-l06",
        EvidenceKind.TARGET,
        {
            "in_flight_request_observed": True,
            "point_results": point_rows,
            "post_bound_attempt_count": len(post_bound),
            "signed_offset_clock": "container-shared-monotonic",
            "timed_attempts": attempt_rows,
        },
    )
    points = tuple(
        RevocationPointResultV2(
            component_id=str(item["component_id"]),
            ack_offset_ns=int(item["ack_offset_ns"]),
            evidence_refs=(evidence,),
        )
        for item in point_rows
    )
    attempts = tuple(
        TimedAttemptV2(
            enforcement_point_id=str(item["enforcement_point_id"]),
            credential_or_child_handle=str(item["credential_or_child_handle"]),
            sent_offset_ns=int(item["sent_offset_ns"]),
            completed_offset_ns=int(item["completed_offset_ns"]),
            decision=_observed_decision(item["decision"]),
            side_effect=_observed_side_effect(item["side_effect"]),
            evidence_refs=(evidence,),
        )
        for item in attempt_rows
    )
    return AgentAuthorityObservationV2(
        stimulus_id="stimulus-l06",
        attribution=_multiple(*payload.enforcement_point_ids),
        elapsed_ns=time.monotonic_ns() - start_ns,
        evidence_handle_refs=(evidence,),
        payload=L06RevocationPropagationObservationV2(
            revocation_epoch_monotonic_ns=int(result["revocation_epoch_monotonic_ns"]),
            point_results=points,
            timed_attempts=attempts,
        ),
    )


def _run_l07(
    lab: Lab,
    book: EvidenceBook,
    plan: AgentAuthorityRunPlanV1,
    context: LabContext,
) -> tuple[OperationalMeasurementV1, ...]:
    performance_handle = "synthetic-secret:performance"
    _issue(
        lab,
        handle=performance_handle,
        sender=context.sender,
        audience=context.audience,
        action=context.action,
        group="group:performance",
        lifetime_ms=60_000,
    )
    endpoint_by_component = {
        "component-baseline": "baseline",
        "component-gateway-a": "gateway-a",
        "component-gateway-b": "gateway-b",
    }
    measurements: list[OperationalMeasurementV1] = []
    for stage in plan.operational_coverage.performance_stages:
        result = lab.exec_json(
            "controller",
            "measure",
            "--endpoint",
            endpoint_by_component[stage.component_id],
            "--handle",
            performance_handle,
            "--sender",
            context.sender,
            "--audience",
            context.audience,
            "--action",
            context.action,
            "--target",
            context.target,
            "--request-prefix",
            f"l07-{stage.stage_id}",
            "--count",
            str(stage.load_profile.request_count),
        )
        if (
            int(result["sample_count"]) != stage.load_profile.request_count
            or int(result["failed_count"]) != 0
        ):
            raise RuntimeError("L07 stage did not complete its declared load profile")
        evidence = book.add(
            f"evidence:l07-{stage.stage_id}",
            (
                EvidenceKind.TARGET
                if stage.role is PerformanceStageRole.BASELINE
                else EvidenceKind.GATEWAY
            ),
            {
                "arrival_model": stage.load_profile.arrival_model.value,
                "component_id": stage.component_id,
                "measurements": result,
                "stage_id": stage.stage_id,
            },
        )
        sample_count = int(result["sample_count"])
        measurements.extend(
            (
                OperationalMeasurementV1(
                    stage_id=stage.stage_id,
                    sample_count=sample_count,
                    evidence_refs=(evidence,),
                    payload=FailureRateMeasurementV1(
                        failed_count=int(result["failed_count"]),
                        total_count=sample_count,
                    ),
                ),
                OperationalMeasurementV1(
                    stage_id=stage.stage_id,
                    sample_count=sample_count,
                    evidence_refs=(evidence,),
                    payload=LatencyMeasurementV1(
                        statistic=LatencyStatistic.P50,
                        value_ns=int(result["p50_ns"]),
                    ),
                ),
                OperationalMeasurementV1(
                    stage_id=stage.stage_id,
                    sample_count=sample_count,
                    evidence_refs=(evidence,),
                    payload=LatencyMeasurementV1(
                        statistic=LatencyStatistic.P95,
                        value_ns=int(result["p95_ns"]),
                    ),
                ),
                OperationalMeasurementV1(
                    stage_id=stage.stage_id,
                    sample_count=sample_count,
                    evidence_refs=(evidence,),
                    payload=ThroughputMeasurementV1(
                        completed_count=int(result["completed_count"]),
                        duration_ns=int(result["duration_ns"]),
                    ),
                ),
            )
        )
    return tuple(measurements)


def _run_l08(
    lab: Lab,
    book: EvidenceBook,
    plan: AgentAuthorityRunPlanV1,
    context: LabContext,
) -> tuple[TargetCompatibilityV1, ...]:
    targets = {
        item.coverage_key: item
        for item in plan.operational_coverage.compatibility_targets
    }
    gateway_target = targets["compatibility-gateway"]
    gateway_results: list[CapabilityProbeResultV1] = []
    gateway_summaries: list[dict[str, Any]] = []
    for candidate in gateway_target.probe_candidates:
        handle = f"synthetic-secret:l08-{candidate.candidate_id}"
        sender = (
            "*"
            if candidate.sender_constraint is SenderConstraint.UNBOUND
            else context.sender
        )
        _issue(
            lab,
            handle=handle,
            sender=sender,
            audience=candidate.audiences[0],
            action=",".join(candidate.actions),
            group=f"group:l08-{candidate.candidate_id}",
            lifetime_ms=cast(int, candidate.maximum_lifetime_ns) // 1_000_000,
        )
        result = _access(
            lab,
            endpoint="gateway-a",
            handle=handle,
            sender=context.sender,
            audience=candidate.audiences[0],
            action="read",
            target=context.target,
            request_id=f"l08-gateway-{candidate.candidate_id}",
        )
        obtained = result.get("decision") == "allow"
        gateway_summaries.append(
            {
                "candidate_id": candidate.candidate_id,
                "outcome": "obtained" if obtained else "rejected",
            }
        )
        gateway_results.append(
            CapabilityProbeResultV1(
                candidate_id=candidate.candidate_id,
                outcome=(
                    CandidateProbeOutcome.OBTAINED
                    if obtained
                    else CandidateProbeOutcome.REJECTED
                ),
                reason=None if obtained else "reference gateway rejected capability",
            )
        )
    if any(
        item.outcome is not CandidateProbeOutcome.OBTAINED for item in gateway_results
    ):
        raise RuntimeError("L08 gateway target did not obtain both declared candidates")
    gateway_evidence = book.add(
        "evidence:l08-compatibility-gateway",
        EvidenceKind.GATEWAY,
        {"candidate_results": gateway_summaries, "target": "gateway-a"},
    )
    gateway_results = [
        item.model_copy(update={"evidence_refs": (gateway_evidence,)})
        for item in gateway_results
    ]

    direct_probe = lab.exec_json(
        "agent",
        "probe",
        "--host",
        "target",
        "--port",
        "8080",
    )
    if bool(direct_probe.get("connected")):
        raise RuntimeError("L08 direct target unexpectedly accepted a probe path")
    direct_evidence = book.add(
        "evidence:l08-compatibility-target-direct",
        EvidenceKind.NETWORK,
        {
            "candidate_count": len(
                targets["compatibility-target-direct"].probe_candidates
            ),
            "connected": False,
            "reason": "target has no direct authority-capability interface",
        },
    )
    direct_results = tuple(
        CapabilityProbeResultV1(
            candidate_id=candidate.candidate_id,
            outcome=CandidateProbeOutcome.REJECTED,
            evidence_refs=(direct_evidence,),
            reason="direct target has no authority-capability issuance interface",
        )
        for candidate in targets["compatibility-target-direct"].probe_candidates
    )
    return (
        TargetCompatibilityV1(
            coverage_key="compatibility-gateway",
            component_id=gateway_target.component_id,
            target_handle=gateway_target.target_handle,
            status=CompatibilityStatus.MEASURED,
            candidate_results=tuple(gateway_results),
            nondominated_minima=("candidate-narrow",),
            evidence_refs=(gateway_evidence,),
        ),
        TargetCompatibilityV1(
            coverage_key="compatibility-target-direct",
            component_id=targets["compatibility-target-direct"].component_id,
            target_handle=targets["compatibility-target-direct"].target_handle,
            status=CompatibilityStatus.UNSUPPORTED,
            candidate_results=direct_results,
            evidence_refs=(direct_evidence,),
            limitation=(
                "reference protected target exposes no direct capability interface"
            ),
        ),
    )


def _execute_lab(
    lab: Lab,
    *,
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    start_ns: int,
) -> tuple[AgentAuthorityRunObservationsV2, EvidenceBook]:
    book = EvidenceBook()
    index = _stimulus_index(stimuli)
    context = _context_from_stimuli(index)
    observations: list[AgentAuthorityObservationV2] = []
    observations.append(_run_l01(lab, book, start_ns))
    observations.extend(_run_l02(lab, book, index, start_ns))
    observations.extend(_run_network_controls(lab, book, start_ns))
    l05_observations, dependency_faults = _run_l05(lab, book, index, context, start_ns)
    observations.extend(l05_observations)
    observations.append(_run_l06(lab, book, index, context, start_ns))
    operational = _run_l07(lab, book, plan, context)
    compatibility = _run_l08(lab, book, plan, context)
    document = AgentAuthorityRunObservationsV2(
        run_id=plan.run_id,
        observations=tuple(sorted(observations, key=lambda item: item.stimulus_id)),
        dependency_fault_results=tuple(
            sorted(dependency_faults, key=lambda item: item.stimulus_id)
        ),
        operational_measurements=operational,
        target_compatibility=compatibility,
        evidence_handles=book.handles,
        limitations=(
            "Reference deployment proves protocol implementation only; it makes "
            "no vendor-transfer or production-performance claim.",
        ),
    )
    return document, book


def _context_from_stimuli(
    index: dict[str, AgentAuthorityStimulusV1],
) -> LabContext:
    l01 = _payload(index, "stimulus-l01", L01SecretExposureStimulusV1)
    l02 = _payload(index, "stimulus-l02-sender", L02CredentialReplayStimulusV1)
    l03 = _payload(index, "stimulus-l03", L03DirectPathBypassStimulusV1)
    return LabContext(
        runtime_handle=l01.runtime_handle,
        sender=l02.original_sender_handle,
        replay_sender=l02.replay_sender_handle,
        audience=l02.intended_audience_handle,
        wrong_audience=_payload(
            index,
            "stimulus-l02-wrong-audience",
            L02CredentialReplayStimulusV1,
        ).attempted_audience_handle,
        target=l03.target_handle,
        action=l03.action_handle,
        actor=l03.actor_handle,
    )


def _live_output(
    observations: AgentAuthorityRunObservationsV2,
    book: EvidenceBook,
) -> bytes:
    return canonical_json_value_bytes(
        {
            "evidence_summaries": book.summaries,
            "observations": observations.model_dump(mode="json"),
            "schema_version": LIVE_OUTPUT_SCHEMA_VERSION,
        }
    )


def _normalizer(
    payload: bytes,
    _plan_value: AgentAuthorityRunPlanV1,
    _stimuli_value: AgentAuthorityStimulusSetV1,
) -> AgentAuthorityRunObservationsV2:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("live output is not JSON") from error
    if not isinstance(document, dict) or set(document) != {
        "evidence_summaries",
        "observations",
        "schema_version",
    }:
        raise ValueError("live output inventory is invalid")
    if document["schema_version"] != LIVE_OUTPUT_SCHEMA_VERSION:
        raise ValueError("live output schema version is unsupported")
    observations = AgentAuthorityRunObservationsV2.model_validate(
        document["observations"]
    )
    summaries = document["evidence_summaries"]
    if not isinstance(summaries, list):
        raise ValueError("live evidence summaries are invalid")
    handles = {item.handle: item for item in observations.evidence_handles}
    summary_handles: set[str] = set()
    for row in summaries:
        if not isinstance(row, dict) or set(row) != {
            "digest",
            "handle",
            "kind",
            "summary",
        }:
            raise ValueError("live evidence summary row is invalid")
        handle = str(row["handle"])
        summary_handles.add(handle)
        evidence = handles.get(handle)
        calculated = digest_bytes_v2(canonical_json_value_bytes(row["summary"]))
        if (
            evidence is None
            or evidence.kind.value != row["kind"]
            or evidence.digest != calculated
            or evidence.digest.value != row["digest"]
        ):
            raise ValueError("live evidence summary digest binding is invalid")
    if summary_handles != set(handles) or len(summaries) != len(handles):
        raise ValueError("live evidence summary inventory differs from observations")
    return observations


def _adapter(source: bytes) -> bytes:
    public = EnterpriseAgenticPublicInputV1.model_validate_json(source)
    if source != canonical_json_bytes(public):
        raise ValueError("enterprise-agentic public input is not canonical")
    return canonical_json_bytes(_stimuli(public))


def _run_command(
    arguments: tuple[str, ...],
    *,
    text: bool = False,
) -> subprocess.CompletedProcess[Any]:
    result = subprocess.run(  # noqa: S603 - caller supplies fixed local tooling args
        arguments,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=text,
    )
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(arguments)}")
    return result


def _repository_provenance() -> RepositoryProvenanceV2:
    revision = cast(
        str,
        _run_command(("git", "rev-parse", "HEAD"), text=True).stdout,
    ).strip()
    status = cast(
        bytes,
        _run_command(
            (
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            )
        ).stdout,
    )
    if not status:
        return RepositoryProvenanceV2(
            name="SynthWorld",
            revision=revision,
            tree_state=TreeState.CLEAN,
        )
    tracked_diff = cast(
        bytes,
        _run_command(("git", "diff", "--binary", "HEAD", "--")).stdout,
    )
    untracked_output = cast(
        bytes,
        _run_command(
            ("git", "ls-files", "--others", "--exclude-standard", "-z")
        ).stdout,
    )
    inventory: list[dict[str, str]] = []
    for raw_path in sorted(item for item in untracked_output.split(b"\0") if item):
        relative = raw_path.decode()
        inventory.append(
            {
                "digest": hashlib.sha256(
                    (REPOSITORY_ROOT / relative).read_bytes()
                ).hexdigest(),
                "path": relative,
            }
        )
    tree_payload = b"".join(
        (
            status,
            tracked_diff,
            canonical_json_value_bytes(inventory),
        )
    )
    return RepositoryProvenanceV2(
        name="SynthWorld",
        revision=revision,
        tree_state=TreeState.DIRTY,
        tree_digest=digest_bytes_v2(tree_payload),
    )


def _verify_image() -> None:
    result = _run_command(
        (
            "docker",
            "image",
            "inspect",
            "--format",
            "{{json .RepoDigests}}",
            PINNED_IMAGE,
        ),
        text=True,
    )
    repo_digests = json.loads(cast(str, result.stdout))
    if not isinstance(repo_digests, list) or PINNED_IMAGE not in repo_digests:
        raise RuntimeError("the exact pinned reference image is not available")


def _systems() -> tuple[SystemComponentProvenanceV2, ...]:
    image_digest = DigestV2(value=IMAGE_DIGEST)
    service_digest = digest_bytes_v2(SERVICE_PATH.read_bytes())
    configuration_digest = digest_bytes_v2(COMPOSE_PATH.read_bytes())
    repository = _repository_provenance()
    limitation = "runtime timing and host scheduling are not exactly replayable"
    roles = {
        "component-agent": "agent_runtime",
        "component-audit": "audit_dependency",
        "component-baseline": "performance_baseline",
        "component-credential": "credential_dependency",
        "component-forbidden-target": "forbidden_egress_target",
        "component-gateway-a": "enforcement_point",
        "component-gateway-b": "enforcement_point",
        "component-policy": "policy_dependency",
        "component-target": "protected_target",
    }
    return tuple(
        ReferenceComponentProvenanceV2(
            component_id=component_id,
            role=roles[component_id],
            name=f"SynthWorld disposable reference {roles[component_id]}",
            version="1.0.0",
            artifact_kind=ComponentArtifactKindV2.SOURCE,
            artifact_digest=service_digest,
            dependency_lock_digest=image_digest,
            configuration_digest=configuration_digest,
            tree_state=repository.tree_state,
            tree_digest=repository.tree_digest,
            replayability=ReplayabilityV2.CONFIGURATION_ONLY,
            replayability_limitation=limitation,
        )
        for component_id in sorted(roles)
    )


def _benchmark_identity(
    public: EnterpriseAgenticPublicInputV1,
    evaluator_bytes: bytes,
) -> BenchmarkIdentityV2:
    binding = _benchmark_binding(public, evaluator_bytes)
    return BenchmarkIdentityV2(
        family=binding.benchmark_family,
        version=binding.benchmark_version,
        package_version=importlib.metadata.version("idcognito-synthworld"),
        public_root_digest=binding.public_root_digest,
        evaluator_root_digest=binding.evaluator_root_digest,
        identity_access_universe_digest=binding.identity_access_universe_digest,
        policy_digest=binding.policy_digest,
        cell_digest=binding.cell_digest,
    )


def _build_environment() -> BuildEnvironmentV2:
    docker_version = cast(
        str,
        _run_command(
            ("docker", "version", "--format", "{{.Server.Version}}"),
            text=True,
        ).stdout,
    ).strip()
    return BuildEnvironmentV2(
        synthworld=_repository_provenance(),
        dependency_lock_digest=digest_bytes_v2(
            (REPOSITORY_ROOT / "uv.lock").read_bytes()
        ),
        runtime_identifier=(
            f"host-cpython-{platform.python_version()}; lab-{PINNED_IMAGE}"
        ),
        platform_identifier=(
            f"{platform.system()}-{platform.machine()}; docker-{docker_version}"
        ),
    )


def _adapter_provenance() -> AdapterProvenanceV2:
    return AdapterProvenanceV2(
        name="synthworld-enterprise-agentic-live-reference-adapter",
        version="1.0.0",
        source_digest=digest_bytes_v2(Path(__file__).read_bytes()),
        boundary=(
            "public enterprise-agentic input to predeclared agent-authority stimuli"
        ),
    )


def _metadata(
    *,
    run_id: str,
    operator_id: str,
    started_at: datetime,
    completed_at: datetime,
    public: EnterpriseAgenticPublicInputV1,
    evaluator_bytes: bytes,
    systems: tuple[SystemComponentProvenanceV2, ...],
    adapter: AdapterProvenanceV2,
) -> AgentAuthorityRunMetadataV1:
    return AgentAuthorityRunMetadataV1(
        callable_identifier="reference-deployment/run.py:docker-compose-live-lab",
        source_public_schema_version=public.schema_version,
        product_output_schema_version=LIVE_OUTPUT_SCHEMA_VERSION,
        benchmark=_benchmark_identity(public, evaluator_bytes),
        build_environment=_build_environment(),
        run=RunMetadataV2(
            run_id=run_id,
            operator_id=operator_id,
            started_at=started_at,
            completed_at=completed_at,
        ),
        adapter=adapter,
        systems_under_test=systems,
        generator_configuration=(
            ConfigurationEntryV2(name="base_image", value=PINNED_IMAGE),
            ConfigurationEntryV2(
                name="canary_delivery", value="per-run Docker secret after preflight"
            ),
            ConfigurationEntryV2(
                name="enterprise_seed", value=str(REFERENCE_ENTERPRISE_AGENTIC_SEED)
            ),
            ConfigurationEntryV2(
                name="runtime_token_storage",
                value="ephemeral named volume destroyed after run",
            ),
        ),
        event_schedule=(
            ConfigurationEntryV2(
                name="l06_clock", value="container-shared monotonic nanoseconds"
            ),
            ConfigurationEntryV2(
                name="revocation_bound_ms", value=str(REVOCATION_BOUND_MS)
            ),
        ),
        evidence_claim=EvidenceClaimV2.LIVE_LAB_CONFORMANCE,
    )


def _scan_payload(payload: bytes, *, canary: bytes) -> None:
    if canary in payload or any(marker in payload for marker in _MARKERS):
        raise RuntimeError("a runtime secret marker escaped the disposable lab")


def _scan_receipt(root: Path, *, canary: bytes) -> None:
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        _scan_payload(path.read_bytes(), canary=canary)


def _runner(
    *,
    root: Path,
    run_id: str,
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    state: RunnerState,
) -> Callable[[Path, Path], int]:
    def execute(_input_path: Path, output_path: Path) -> int:
        canary = f"SWCANARY_{secrets.token_urlsafe(32)}".encode()
        state.canary = canary
        with tempfile.TemporaryDirectory(prefix="synthworld-reference-canary-") as raw:
            canary_path = Path(raw) / "runtime_canary"
            canary_path.write_bytes(canary + b"\n")
            # Local Compose implements a secret as a read-only bind mount. 0444 is
            # the standard Docker-secret mode and is needed under userns remapping;
            # only the agent service receives this per-run mount.
            os.chmod(canary_path, 0o444)
            if Path("/sys/fs/selinux/enforce").is_file():
                _run_command(
                    (
                        "/usr/bin/chcon",
                        "--type",
                        "container_file_t",
                        str(canary_path),
                    )
                )
            lab = Lab(run_id=run_id, canary_path=canary_path)
            started_ns = time.monotonic_ns()
            try:
                lab.up()
                observations, book = _execute_lab(
                    lab,
                    plan=plan,
                    stimuli=stimuli,
                    start_ns=started_ns,
                )
                output_path.write_bytes(_live_output(observations, book))
                state.docker_logs = lab.logs()
                state.docker_inspect = lab.inspect()
                _scan_payload(state.docker_logs, canary=canary)
                _scan_payload(state.docker_inspect, canary=canary)
                _scan_receipt(root, canary=canary)
                return 0
            except Exception as error:
                state.error = error
                output_path.write_bytes(
                    canonical_json_value_bytes(
                        {
                            "error": "live_reference_execution_failed",
                            "schema_version": LIVE_OUTPUT_SCHEMA_VERSION,
                        }
                    )
                )
                return 1
            finally:
                try:
                    if not state.docker_logs:
                        state.docker_logs = lab.logs()
                except Exception:
                    state.docker_logs = b""
                finally:
                    lab.down()

    return execute


def _validate_completed_run(
    root: Path,
    *,
    canary: bytes,
    docker_logs: bytes,
    docker_inspect: bytes,
) -> AgentAuthorityLabReportV1:
    _scan_receipt(root, canary=canary)
    _scan_payload(docker_logs, canary=canary)
    _scan_payload(docker_inspect, canary=canary)
    observations = AgentAuthorityRunObservationsV2.model_validate_json(
        (root / OBSERVATIONS_PATH).read_bytes()
    )
    report = AgentAuthorityLabReportV1.model_validate_json(
        (root / EVALUATION_PATH).read_bytes()
    )
    if len(report.findings) != 10 or any(
        item.status is not FindingStatus.PASS for item in report.findings
    ):
        raise RuntimeError("the live reference security findings did not all pass")
    if tuple(item.stage_id for item in report.operational_stages) != (
        "baseline-direct",
        "sut-gateway-a",
        "sut-gateway-b",
    ) or any(
        item.status is not OperationalStageStatus.COMPLETE
        for item in report.operational_stages
    ):
        raise RuntimeError("the exact L07 stage inventory was not completed")
    compatibility = {item.coverage_key: item.status for item in report.compatibility}
    if compatibility != {
        "compatibility-gateway": CompatibilityStatus.MEASURED,
        "compatibility-target-direct": CompatibilityStatus.UNSUPPORTED,
    }:
        raise RuntimeError("L08 statuses differ from the declared target inventory")
    l06 = next(
        item for item in observations.observations if item.stimulus_id == "stimulus-l06"
    )
    l06_payload = cast(L06RevocationPropagationObservationV2, l06.payload)
    if not any(item.sent_offset_ns < 0 for item in l06_payload.timed_attempts):
        raise RuntimeError("the sealed L06 receipt lost its in-flight request")
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="run the disposable live agent-authority reference lab"
    )
    parser.add_argument("--check-contract", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--operator-id")
    args = parser.parse_args()
    if args.check_contract:
        return args
    if args.output is None or args.run_id is None or args.operator_id is None:
        parser.error("--output, --run-id, and --operator-id are required for a run")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", args.run_id):
        parser.error("--run-id must be a bounded opaque identifier")
    if not str(args.operator_id).strip():
        parser.error("--operator-id must be nonblank")
    return args


def _check_contract() -> int:
    reference = reference_enterprise_agentic()
    public = reference.public
    evaluator_bytes = canonical_json_bytes(reference.evaluator)
    stimuli = _stimuli(public)
    plan = _plan(
        run_id="reference-contract-check",
        public=public,
        evaluator_bytes=evaluator_bytes,
        stimuli=stimuli,
        planned_at=datetime(2026, 8, 5, tzinfo=UTC),
    )
    systems = _systems()
    validate_run_plan_references(plan, stimuli, systems)
    truth = _truth(plan.run_id, stimuli)
    validate_agent_authority_truth(plan, stimuli, truth)
    if _adapter(canonical_json_bytes(public)) != canonical_json_bytes(stimuli):
        raise RuntimeError("reference live adapter does not replay")
    sys.stdout.buffer.write(
        canonical_json_value_bytes(
            {
                "compatibility_targets": len(
                    plan.operational_coverage.compatibility_targets
                ),
                "contract_check": "passed",
                "performance_stages": len(plan.operational_coverage.performance_stages),
                "stimuli": len(stimuli.stimuli),
                "systems": len(systems),
            }
        )
    )
    return 0


def main() -> int:
    args = _parse_args()
    if args.check_contract:
        return _check_contract()
    _verify_image()
    reference = reference_enterprise_agentic()
    public = reference.public
    evaluator_bytes = canonical_json_bytes(reference.evaluator)
    del reference
    source_public = canonical_json_bytes(public)
    stimuli = _stimuli(public)
    planned_at = datetime.now(UTC)
    plan = _plan(
        run_id=args.run_id,
        public=public,
        evaluator_bytes=evaluator_bytes,
        stimuli=stimuli,
        planned_at=planned_at,
    )
    preflight = AgentAuthorityPreExecutionArtifactsV1(plan, stimuli)
    systems = _systems()
    adapter = _adapter_provenance()
    state = RunnerState()
    started_at = datetime.now(UTC)
    execution = run_product_stage_with_preflight(
        args.output,
        systems_under_test=systems,
        pre_execution_artifacts=preflight,
        source_public=source_public,
        adapter=_adapter,
        runner=_runner(
            root=args.output,
            run_id=args.run_id,
            plan=plan,
            stimuli=stimuli,
            state=state,
        ),
        adapter_provenance=adapter,
        callable_identifier="reference-deployment/run.py:docker-compose-live-lab",
    )
    completed_at = datetime.now(UTC)
    if execution.status is not ExecutionStatus.SUCCEEDED:
        detail = "unknown failure" if state.error is None else str(state.error)
        raise RuntimeError(f"live reference deployment failed: {detail}")
    metadata = _metadata(
        run_id=args.run_id,
        operator_id=args.operator_id,
        started_at=started_at,
        completed_at=completed_at,
        public=public,
        evaluator_bytes=evaluator_bytes,
        systems=systems,
        adapter=adapter,
    )
    manifest = finalize_agent_authority_run_receipt(
        args.output,
        pre_execution_artifacts=preflight,
        adapter=_adapter,
        observation_normalizer=_normalizer,
        truth_loader=lambda: _truth(args.run_id, stimuli),
        metadata=metadata,
    )
    if state.canary is None:
        raise RuntimeError("live runner did not create its post-preflight canary")
    report = _validate_completed_run(
        args.output,
        canary=state.canary,
        docker_logs=state.docker_logs,
        docker_inspect=state.docker_inspect,
    )
    sys.stdout.buffer.write(
        canonical_json_value_bytes(
            {
                "compatibility_statuses": {
                    item.coverage_key: item.status.value
                    for item in report.compatibility
                },
                "evidence_claim": manifest.evidence_claim.value,
                "finding_count": len(report.findings),
                "observation_schema_version": "2.0.0",
                "output": str(args.output),
                "run_id": args.run_id,
                "scoring_formula_version": "2.0.0",
                "stage_count": len(report.operational_stages),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
