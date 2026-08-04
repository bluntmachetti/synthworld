"""Deterministic fake deployment for protocol conformance tests only.

This module exercises every protocol family without making a live-control or
vendor-performance claim.  Its product output is a declared observation fixture,
not evidence that an external enforcement system ran.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from synthworld.agent_authority.cases import (
    AgentAuthorityObservationV1,
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
    L06RevocationPropagationObservationV1,
    L06RevocationPropagationStimulusV1,
    ReachabilityObservation,
    ReplayKind,
    RevocationPointResultV1,
    TimedAttemptV1,
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
    AgentAuthorityLabTruthV1,
    AgentAuthorityRunObservationsV1,
    AgentAuthorityRunPlanV1,
    AgentAuthorityStimulusTruthV1,
    ConfigurationReviewStatus,
    L01SecretExposureTruthV1,
    L02CredentialReplayTruthV1,
    L03DirectPathBypassTruthV1,
    L04NetworkPolicyTruthV1,
    L05CriticalDependencyFailureTruthV1,
    L06RevocationPropagationTruthV1,
    RepresentativeConfigurationReviewV1,
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
    OperationalCoverageGapV1,
    OperationalCoveragePlanV1,
    OperationalMeasurementV1,
    PerformanceStageRole,
    PerformanceStageV1,
    SenderConstraint,
    TargetCompatibilityV1,
    ThroughputMeasurementV1,
)
from synthworld.assurance.agent_authority import (
    AgentAuthorityPreExecutionArtifactsV1,
    AgentAuthorityRunMetadataV1,
    build_agent_authority_run_receipt,
    stimulus_set_digest,
)
from synthworld.assurance.models import TreeState
from synthworld.assurance.models_v2 import (
    AdapterProvenanceV2,
    BenchmarkIdentityV2,
    BuildEnvironmentV2,
    ComponentArtifactKindV2,
    ConfigurationObservabilityV2,
    DigestV2,
    EvidenceClaimV2,
    ManagedServiceComponentProvenanceV2,
    ReferenceComponentProvenanceV2,
    ReplayabilityV2,
    RepositoryProvenanceV2,
    RunMetadataV2,
    RunReceiptManifestV2,
    SelfHostedComponentProvenanceV2,
    SystemComponentProvenanceV2,
    VersionObservabilityV2,
)
from synthworld.assurance.receipt import canonical_json_bytes


def reference_stimuli() -> AgentAuthorityStimulusSetV1:
    credential = SyntheticSecretHandleV1(handle="synthetic-secret:credential-1")
    return AgentAuthorityStimulusSetV1(
        stimuli=(
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l01",
                schedule_tick=1,
                payload=L01SecretExposureStimulusV1(
                    canary_handle=SyntheticSecretHandleV1(
                        handle="synthetic-secret:canary-1"
                    ),
                    runtime_handle="runtime:reference",
                    extraction_vectors=(ExtractionVector.PROMPT,),
                    required_channels=(EvidenceChannel.LOG,),
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l02",
                schedule_tick=2,
                payload=L02CredentialReplayStimulusV1(
                    replay_kind=ReplayKind.DIFFERENT_SENDER,
                    credential_handle=credential,
                    original_sender_handle="sender:original",
                    replay_sender_handle="sender:replay",
                    intended_audience_handle="audience:target",
                    attempted_audience_handle="audience:target",
                    expiry_tick=10,
                    target_handle="target:reference",
                    action_handle="action:read",
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l03",
                schedule_tick=3,
                payload=L03DirectPathBypassStimulusV1(
                    actor_handle="actor:reference",
                    target_handle="target:reference",
                    action_handle="action:read",
                    sanctioned_path_component_ids=(
                        "component-gateway",
                        "component-target",
                    ),
                    bypass_route_id="route:direct",
                    expected_enforcement_point_ids=("component-gateway",),
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l04",
                schedule_tick=4,
                payload=L04NetworkPolicyStimulusV1(
                    source_handle="runtime:reference",
                    target_handle="target:reference",
                    action_handle="action:read",
                    network_policy_handle="policy:egress",
                    forbidden_route_id="route:forbidden",
                    enforcement_point_ids=("component-gateway",),
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l05",
                schedule_tick=5,
                payload=L05CriticalDependencyFailureStimulusV1(
                    dependency_component_id="component-dependency",
                    fault_mode=FaultMode.UNAVAILABLE,
                    action_handle="action:read",
                    target_handle="target:reference",
                    enforcement_point_ids=("component-gateway",),
                    injection_tick=5,
                    recovery_tick=7,
                ),
            ),
            AgentAuthorityStimulusV1(
                stimulus_id="stimulus-l06",
                schedule_tick=6,
                payload=L06RevocationPropagationStimulusV1(
                    authority_handle="authority:reference",
                    delegation_handle="delegation:reference",
                    revocation_tick=6,
                    traffic_ticks=(7, 8),
                    enforcement_point_ids=("component-gateway",),
                    issued_credential_handles=(credential,),
                    declared_bound_id="bound:revocation",
                ),
            ),
        )
    )


def reference_systems() -> tuple[SystemComponentProvenanceV2, ...]:
    clean = TreeState.CLEAN
    return (
        ReferenceComponentProvenanceV2(
            component_id="component-baseline",
            role="performance_baseline",
            name="deterministic no-enforcement baseline",
            version="1.0.0",
            artifact_kind=ComponentArtifactKindV2.SOURCE,
            artifact_digest=_digest("1"),
            dependency_lock_digest=_digest("2"),
            configuration_digest=_digest("3"),
            tree_state=clean,
            replayability=ReplayabilityV2.EXACT,
        ),
        SelfHostedComponentProvenanceV2(
            component_id="component-dependency",
            role="authority_dependency",
            name="deterministic dependency fixture",
            version="1.0.0",
            artifact_kind=ComponentArtifactKindV2.SOURCE,
            artifact_digest=_digest("4"),
            dependency_lock_digest=_digest("2"),
            configuration_digest=_digest("5"),
            tree_state=clean,
            replayability=ReplayabilityV2.EXACT,
        ),
        SelfHostedComponentProvenanceV2(
            component_id="component-gateway",
            role="enforcement_point",
            name="deterministic enforcement fixture",
            version="1.0.0",
            artifact_kind=ComponentArtifactKindV2.SOURCE,
            artifact_digest=_digest("6"),
            dependency_lock_digest=_digest("2"),
            configuration_digest=_digest("7"),
            tree_state=clean,
            replayability=ReplayabilityV2.EXACT,
        ),
        ManagedServiceComponentProvenanceV2(
            component_id="component-target",
            role="protected_target",
            provider="example.invalid",
            product="fictional managed target",
            configuration_observability=ConfigurationObservabilityV2.NOT_EXPOSED,
            configuration_capture_limitation="fixture exposes no managed configuration",
            version_observability=VersionObservabilityV2.NOT_EXPOSED,
            replayability=ReplayabilityV2.NOT_REPLAYABLE,
            replayability_limitation="managed deployment state cannot be replayed",
        ),
    )


def reference_plan() -> AgentAuthorityRunPlanV1:
    stimuli = reference_stimuli()
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
                None if control in selected else "fake lab run has no core trace input"
            ),
        )
        for control in CONTROL_ORDER
    )
    return AgentAuthorityRunPlanV1(
        run_id="reference-agent-authority-run",
        run_layer=RunLayer.COMBINED,
        control_coverage=coverage,
        benchmark=_benchmark_binding(),
        event_schedule_version="reference-schedule-1.0.0",
        deployment_patterns=(
            DeploymentPattern.PROXY_INJECTION,
            DeploymentPattern.STATIC_BEARER,
        ),
        authority_path_component_ids=("component-gateway", "component-target"),
        enforcement_point_ids=("component-gateway",),
        direct_path_reachability=DirectPathReachability.REACHABLE,
        isolation_mechanism="local deterministic process boundary",
        authority_critical_dependency_ids=("component-dependency",),
        declared_bounds=(
            DeclaredBoundV1(
                bound_id="bound:revocation",
                control_id=AgentAuthorityControlId.L06,
                metric=BoundMetric.REVOCATION_PROPAGATION,
                value=10,
                unit=BoundUnit.MS,
            ),
        ),
        operational_coverage=_operational_coverage(),
        stimulus_set_digest=stimulus_set_digest(stimuli),
        adapter_authorship=AdapterAuthorshipDisclosureV1(
            author=AdapterAuthor.SYNTHWORLD,
            disclosure="deterministic protocol fixture; not a vendor adapter",
        ),
        representative_configuration_review=RepresentativeConfigurationReviewV1(
            status=ConfigurationReviewStatus.NOT_APPLICABLE,
            limitation="fixture configuration is intentionally non-representative",
        ),
        planned_at=datetime(2026, 8, 4, 8, 0, tzinfo=UTC),
    )


def reference_observations() -> AgentAuthorityRunObservationsV1:
    evidence = _evidence_handles()
    specific_gateway = ObservationAttributionV1(
        kind=AttributionKind.SPECIFIC,
        component_ids=("component-gateway",),
    )
    observations = (
        AgentAuthorityObservationV1(
            stimulus_id="stimulus-l01",
            attribution=specific_gateway,
            elapsed_ns=1_000,
            evidence_handle_refs=("evidence:log",),
            payload=L01SecretExposureObservationV1(
                channel_scans=(
                    ChannelScanV1(
                        channel=EvidenceChannel.LOG,
                        collection_status=CollectionStatus.COLLECTED,
                        canary_match=False,
                        evidence_handle_ref="evidence:log",
                    ),
                )
            ),
        ),
        AgentAuthorityObservationV1(
            stimulus_id="stimulus-l02",
            attribution=specific_gateway,
            elapsed_ns=2_000,
            evidence_handle_refs=("evidence:target",),
            payload=L02CredentialReplayObservationV1(
                target_decision=ObservedDecision.DENY,
                side_effect=ObservedSideEffect.NOT_OBSERVED,
                sender_constraint_status=ConstraintCheckStatus.VIOLATED,
                audience_check_status=ConstraintCheckStatus.SATISFIED,
                target_evidence_refs=("evidence:target",),
            ),
        ),
        AgentAuthorityObservationV1(
            stimulus_id="stimulus-l03",
            attribution=specific_gateway,
            elapsed_ns=3_000,
            evidence_handle_refs=("evidence:network",),
            payload=L03DirectPathBypassObservationV1(
                reachability=ReachabilityObservation.BLOCKED,
                target_decision=ObservedDecision.UNOBSERVED,
                side_effect=ObservedSideEffect.NOT_OBSERVED,
                traversed_component_ids=("component-gateway",),
                network_evidence_refs=("evidence:network",),
            ),
        ),
        AgentAuthorityObservationV1(
            stimulus_id="stimulus-l04",
            attribution=specific_gateway,
            elapsed_ns=4_000,
            evidence_handle_refs=("evidence:network",),
            payload=L04NetworkPolicyObservationV1(
                connectivity=ConnectivityObservation.BLOCKED,
                target_decision=ObservedDecision.UNOBSERVED,
                side_effect=ObservedSideEffect.NOT_OBSERVED,
                network_evidence_refs=("evidence:network",),
            ),
        ),
        AgentAuthorityObservationV1(
            stimulus_id="stimulus-l05",
            attribution=specific_gateway,
            elapsed_ns=5_000,
            evidence_handle_refs=("evidence:gateway",),
            payload=L05CriticalDependencyFailureObservationV1(
                fault_confirmation=FaultConfirmation.CONFIRMED,
                enforcement_outcomes=(
                    EnforcementOutcomeV1(
                        component_id="component-gateway",
                        decision=ObservedDecision.DENY,
                        side_effect=ObservedSideEffect.NOT_OBSERVED,
                        evidence_refs=("evidence:gateway",),
                    ),
                ),
            ),
        ),
        AgentAuthorityObservationV1(
            stimulus_id="stimulus-l06",
            attribution=specific_gateway,
            elapsed_ns=12_000_000,
            evidence_handle_refs=("evidence:target",),
            payload=L06RevocationPropagationObservationV1(
                revocation_epoch_ns=100_000_000,
                point_results=(
                    RevocationPointResultV1(
                        component_id="component-gateway",
                        ack_elapsed_ns=5_000_000,
                        evidence_refs=("evidence:target",),
                    ),
                ),
                timed_attempts=(
                    TimedAttemptV1(
                        enforcement_point_id="component-gateway",
                        credential_or_child_handle="synthetic-secret:credential-1",
                        sent_elapsed_ns=11_000_000,
                        completed_elapsed_ns=12_000_000,
                        decision=ObservedDecision.DENY,
                        side_effect=ObservedSideEffect.NOT_OBSERVED,
                        evidence_refs=("evidence:target",),
                    ),
                ),
            ),
        ),
    )
    return AgentAuthorityRunObservationsV1(
        run_id="reference-agent-authority-run",
        observations=observations,
        dependency_fault_results=(
            DependencyFaultResultV1(
                stimulus_id="stimulus-l05",
                dependency_component_id="component-dependency",
                fault_confirmation=FaultConfirmation.CONFIRMED,
                evidence_refs=("evidence:gateway",),
            ),
        ),
        operational_measurements=_operational_measurements(),
        operational_coverage_gaps=(
            OperationalCoverageGapV1(
                stage_id="baseline-gap",
                reason="deliberate fake coverage gap",
                evidence_refs=("evidence:trace",),
            ),
            OperationalCoverageGapV1(
                stage_id="sut-gap",
                reason="deliberate fake coverage gap",
                evidence_refs=("evidence:trace",),
            ),
        ),
        target_compatibility=_compatibility_results(),
        evidence_handles=evidence,
        limitations=("deterministic fake deployment; no live-control claim",),
    )


def reference_truth() -> AgentAuthorityLabTruthV1:
    return AgentAuthorityLabTruthV1(
        run_id="reference-agent-authority-run",
        stimuli=(
            AgentAuthorityStimulusTruthV1(
                stimulus_id="stimulus-l01",
                control_id=AgentAuthorityControlId.L01,
                payload=L01SecretExposureTruthV1(
                    required_channels=(EvidenceChannel.LOG,),
                    required_evidence_kinds=(EvidenceKind.LOG,),
                ),
            ),
            AgentAuthorityStimulusTruthV1(
                stimulus_id="stimulus-l02",
                control_id=AgentAuthorityControlId.L02,
                payload=L02CredentialReplayTruthV1(
                    required_evidence_kinds=(EvidenceKind.TARGET,)
                ),
            ),
            AgentAuthorityStimulusTruthV1(
                stimulus_id="stimulus-l03",
                control_id=AgentAuthorityControlId.L03,
                payload=L03DirectPathBypassTruthV1(
                    required_evidence_kinds=(EvidenceKind.NETWORK,)
                ),
            ),
            AgentAuthorityStimulusTruthV1(
                stimulus_id="stimulus-l04",
                control_id=AgentAuthorityControlId.L04,
                payload=L04NetworkPolicyTruthV1(
                    required_evidence_kinds=(EvidenceKind.NETWORK,)
                ),
            ),
            AgentAuthorityStimulusTruthV1(
                stimulus_id="stimulus-l05",
                control_id=AgentAuthorityControlId.L05,
                payload=L05CriticalDependencyFailureTruthV1(
                    enforcement_point_ids=("component-gateway",),
                    required_evidence_kinds=(EvidenceKind.GATEWAY,),
                ),
            ),
            AgentAuthorityStimulusTruthV1(
                stimulus_id="stimulus-l06",
                control_id=AgentAuthorityControlId.L06,
                payload=L06RevocationPropagationTruthV1(
                    enforcement_point_ids=("component-gateway",),
                    credential_or_child_handles=("synthetic-secret:credential-1",),
                    bound_ns=10_000_000,
                    required_evidence_kinds=(EvidenceKind.TARGET,),
                ),
            ),
        ),
    )


def reference_metadata() -> AgentAuthorityRunMetadataV1:
    return AgentAuthorityRunMetadataV1(
        callable_identifier="synthworld.agent_authority.reference.fake_product",
        source_public_schema_version="1.0.0",
        product_output_schema_version="1.0.0",
        benchmark=_benchmark_identity(),
        build_environment=BuildEnvironmentV2(
            synthworld=RepositoryProvenanceV2(
                name="SynthWorld",
                revision="reference-revision",
                tree_state=TreeState.CLEAN,
            ),
            dependency_lock_digest=_digest("2"),
            runtime_identifier="cpython-3.13-reference",
            platform_identifier="platform-independent-fixture",
        ),
        run=RunMetadataV2(
            run_id="reference-agent-authority-run",
            operator_id="synthworld-reference-fixture",
            started_at=datetime(2026, 8, 4, 8, 0, tzinfo=UTC),
            completed_at=datetime(2026, 8, 4, 8, 1, tzinfo=UTC),
        ),
        adapter=AdapterProvenanceV2(
            name="synthworld-reference-agent-authority-adapter",
            version="1.0.0",
            source_digest=_digest("8"),
            boundary="canonical stimulus-set identity adaptation",
        ),
        systems_under_test=reference_systems(),
        evidence_claim=EvidenceClaimV2.GENERATED_TRANSFER_EVIDENCE,
    )


def build_reference_agent_authority_run_receipt(root: Path) -> RunReceiptManifestV2:
    stimuli = reference_stimuli()
    plan = reference_plan()
    observations = reference_observations()

    def runner(_input_path: Path, output_path: Path) -> int:
        output_path.write_bytes(canonical_json_bytes(observations))
        return 0

    return build_agent_authority_run_receipt(
        root,
        pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
            run_plan=plan,
            stimuli=stimuli,
        ),
        source_public=canonical_json_bytes(stimuli),
        adapter=lambda payload: payload,
        runner=runner,
        observation_normalizer=_normalize_reference_output,
        truth_loader=reference_truth,
        metadata=reference_metadata(),
    )


def _normalize_reference_output(
    payload: bytes,
    _plan: AgentAuthorityRunPlanV1,
    _stimuli: AgentAuthorityStimulusSetV1,
) -> AgentAuthorityRunObservationsV1:
    return AgentAuthorityRunObservationsV1.model_validate_json(payload)


def _operational_coverage() -> OperationalCoveragePlanV1:
    load = LoadProfileV1(
        request_count=100,
        max_concurrency=4,
        arrival_model=ArrivalModel.CLOSED_LOOP,
    )
    stages = (
        PerformanceStageV1(
            stage_id="baseline-a",
            role=PerformanceStageRole.BASELINE,
            component_id="component-baseline",
            target_handle="target:reference",
            action_handle="action:read",
            load_profile=load,
            measurement_window_ns=1_000_000_000,
            statistics=(LatencyStatistic.P50, LatencyStatistic.P95),
        ),
        PerformanceStageV1(
            stage_id="baseline-gap",
            role=PerformanceStageRole.BASELINE,
            component_id="component-baseline",
            target_handle="target:gap",
            action_handle="action:read",
            load_profile=load,
            measurement_window_ns=1_000_000_000,
            statistics=(LatencyStatistic.P50, LatencyStatistic.P95),
        ),
        PerformanceStageV1(
            stage_id="sut-a",
            role=PerformanceStageRole.SUT,
            component_id="component-gateway",
            target_handle="target:reference",
            action_handle="action:read",
            load_profile=load,
            measurement_window_ns=1_000_000_000,
            statistics=(LatencyStatistic.P50, LatencyStatistic.P95),
            baseline_stage_id="baseline-a",
        ),
        PerformanceStageV1(
            stage_id="sut-gap",
            role=PerformanceStageRole.SUT,
            component_id="component-gateway",
            target_handle="target:gap",
            action_handle="action:read",
            load_profile=load,
            measurement_window_ns=1_000_000_000,
            statistics=(LatencyStatistic.P50, LatencyStatistic.P95),
            baseline_stage_id="baseline-gap",
        ),
    )
    candidate_narrow = AuthorityCapabilityV1(
        candidate_id="candidate-narrow",
        credential_kind=CredentialKind.BEARER,
        actions=("action:read",),
        scopes=("scope:one",),
        audiences=("audience:target",),
        sender_constraint=SenderConstraint.BOUND,
        maximum_lifetime_ns=1_000_000_000,
    )
    candidate_wide = AuthorityCapabilityV1(
        candidate_id="candidate-wide",
        credential_kind=CredentialKind.BEARER,
        actions=("action:read", "action:write"),
        scopes=("scope:one", "scope:two"),
        audiences=("audience:target",),
        sender_constraint=SenderConstraint.UNBOUND,
    )
    targets = tuple(
        CompatibilityTargetV1(
            coverage_key=key,
            component_id="component-target",
            target_handle=f"target:{key}",
            applicable_patterns=(DeploymentPattern.PROXY_INJECTION,),
            action_universe=("action:read", "action:write"),
            scope_universe=("scope:one", "scope:two"),
            audience_universe=("audience:target",),
            probe_candidates=(candidate_narrow, candidate_wide),
        )
        for key in (
            "compat-1-measured",
            "compat-2-unsupported",
            "compat-3-incomplete",
            "compat-4-not-attempted",
        )
    )
    return OperationalCoveragePlanV1(
        performance_stages=stages,
        compatibility_targets=targets,
    )


def _operational_measurements() -> tuple[OperationalMeasurementV1, ...]:
    rows: list[OperationalMeasurementV1] = []
    for stage_id, p50, p95 in (
        ("baseline-a", 1_000, 2_000),
        ("sut-a", 1_500, 2_800),
    ):
        rows.extend(
            (
                OperationalMeasurementV1(
                    stage_id=stage_id,
                    sample_count=100,
                    evidence_refs=("evidence:trace",),
                    payload=FailureRateMeasurementV1(
                        failed_count=1,
                        total_count=100,
                    ),
                ),
                OperationalMeasurementV1(
                    stage_id=stage_id,
                    sample_count=100,
                    evidence_refs=("evidence:trace",),
                    payload=LatencyMeasurementV1(
                        statistic=LatencyStatistic.P50,
                        value_ns=p50,
                    ),
                ),
                OperationalMeasurementV1(
                    stage_id=stage_id,
                    sample_count=100,
                    evidence_refs=("evidence:trace",),
                    payload=LatencyMeasurementV1(
                        statistic=LatencyStatistic.P95,
                        value_ns=p95,
                    ),
                ),
                OperationalMeasurementV1(
                    stage_id=stage_id,
                    sample_count=100,
                    evidence_refs=("evidence:trace",),
                    payload=ThroughputMeasurementV1(
                        completed_count=99,
                        duration_ns=1_000_000_000,
                    ),
                ),
            )
        )
    return tuple(rows)


def _compatibility_results() -> tuple[TargetCompatibilityV1, ...]:
    candidate_ids = ("candidate-narrow", "candidate-wide")
    measured = tuple(
        CapabilityProbeResultV1(
            candidate_id=item,
            outcome=CandidateProbeOutcome.OBTAINED,
            evidence_refs=("evidence:target",),
        )
        for item in candidate_ids
    )
    rejected = tuple(
        CapabilityProbeResultV1(
            candidate_id=item,
            outcome=CandidateProbeOutcome.REJECTED,
            evidence_refs=("evidence:target",),
            reason="target rejects this authority form",
        )
        for item in candidate_ids
    )
    incomplete = (
        CapabilityProbeResultV1(
            candidate_id="candidate-narrow",
            outcome=CandidateProbeOutcome.FAILED,
            reason="fixture probe failed",
        ),
        CapabilityProbeResultV1(
            candidate_id="candidate-wide",
            outcome=CandidateProbeOutcome.UNOBSERVED,
            reason="fixture probe was unobserved",
        ),
    )
    return (
        TargetCompatibilityV1(
            coverage_key="compat-1-measured",
            component_id="component-target",
            target_handle="target:compat-1-measured",
            status=CompatibilityStatus.MEASURED,
            candidate_results=measured,
            nondominated_minima=("candidate-narrow",),
            evidence_refs=("evidence:target",),
        ),
        TargetCompatibilityV1(
            coverage_key="compat-2-unsupported",
            component_id="component-target",
            target_handle="target:compat-2-unsupported",
            status=CompatibilityStatus.UNSUPPORTED,
            candidate_results=rejected,
            evidence_refs=("evidence:target",),
            limitation="target cannot accept the declared authority form",
        ),
        TargetCompatibilityV1(
            coverage_key="compat-3-incomplete",
            component_id="component-target",
            target_handle="target:compat-3-incomplete",
            status=CompatibilityStatus.INCOMPLETE,
            candidate_results=incomplete,
            limitation="probe coverage is deliberately incomplete",
        ),
        TargetCompatibilityV1(
            coverage_key="compat-4-not-attempted",
            component_id="component-target",
            target_handle="target:compat-4-not-attempted",
            status=CompatibilityStatus.NOT_ATTEMPTED,
            limitation="probe deliberately not attempted",
        ),
    )


def _evidence_handles() -> tuple[EvidenceHandleV1, ...]:
    return tuple(
        EvidenceHandleV1(
            handle=handle,
            kind=kind,
            digest=_digest(character),
            collection_status=CollectionStatus.COLLECTED,
            redaction_status=RedactionStatus.NOT_REQUIRED,
        )
        for handle, kind, character in (
            ("evidence:gateway", EvidenceKind.GATEWAY, "a"),
            ("evidence:log", EvidenceKind.LOG, "b"),
            ("evidence:network", EvidenceKind.NETWORK, "c"),
            ("evidence:target", EvidenceKind.TARGET, "d"),
            ("evidence:trace", EvidenceKind.TRACE, "e"),
        )
    )


def _benchmark_binding() -> AgentAuthorityBenchmarkBindingV1:
    return AgentAuthorityBenchmarkBindingV1(
        benchmark_family="synthworld.agent_authority.reference",
        benchmark_version="1.0.0",
        public_root_digest=_digest("9"),
        evaluator_root_digest=_digest("a"),
        identity_access_universe_digest=_digest("b"),
        policy_digest=_digest("c"),
        cell_digest=_digest("d"),
    )


def _benchmark_identity() -> BenchmarkIdentityV2:
    binding = _benchmark_binding()
    return BenchmarkIdentityV2(
        family=binding.benchmark_family,
        version=binding.benchmark_version,
        package_version="0.12.0",
        public_root_digest=binding.public_root_digest,
        evaluator_root_digest=binding.evaluator_root_digest,
        identity_access_universe_digest=binding.identity_access_universe_digest,
        policy_digest=binding.policy_digest,
        cell_digest=binding.cell_digest,
    )


def _digest(character: str) -> DigestV2:
    return DigestV2(value=character * 64)


__all__ = [
    "build_reference_agent_authority_run_receipt",
    "reference_metadata",
    "reference_observations",
    "reference_plan",
    "reference_stimuli",
    "reference_systems",
    "reference_truth",
]
