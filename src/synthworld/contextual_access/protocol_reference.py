"""Deterministic reference contracts for a contextual-access external run."""

from __future__ import annotations

from dataclasses import dataclass

from synthworld.agent_authority.common import (
    CollectionStatus,
    EvidenceHandleV1,
    EvidenceKind,
    ObservedDecision,
    RedactionStatus,
)
from synthworld.assurance.models import TreeState
from synthworld.assurance.models_v2 import (
    ComponentArtifactKindV2,
    DigestV2,
    ReferenceComponentProvenanceV2,
    ReplayabilityV2,
    SystemComponentProvenanceV2,
)
from synthworld.contextual_access.models import (
    ContextualAccessPublicV1,
    ContextualCaseKind,
)
from synthworld.contextual_access.protocol import (
    AccessDecisionObservationV1,
    AccessDecisionProbeV1,
    AccessDecisionRunTruthV1,
    ContextDeliveryAcceptanceObservationV1,
    ContextualAccessObservationsV1,
    ContextualAccessReportV1,
    ContextualAccessRunPlanV1,
    ContextualAccessRunTruthV1,
    ContextualBenchmarkBindingV1,
    ContextualControlCoverageV1,
    ContextualControlId,
    ContextualCoverageDisposition,
    ContextualDecisionAttemptV1,
    ContextualFaultKind,
    ContextualFaultV1,
    ContextualRunBoundsV1,
    DeliveryAcceptanceProbeV1,
    DeliveryAcceptanceTruthV1,
    EvidenceCorrelationObservationV1,
    EvidenceCorrelationProbeV1,
    MappingIngestionObservationV1,
    MappingIngestionProbeV1,
    MappingIngestionStatus,
    MappingIngestionTruthV1,
    ProtectedEnforcementObservationV1,
    ProtectedEnforcementProbeV1,
    ProtectedEnforcementTruthV1,
    SynchronizationFaultObservationV1,
    SynchronizationFaultProbeV1,
    SynchronizationFaultStatus,
    SynchronizationFaultTruthV1,
    compile_contextual_run_truth,
    contextual_public_case_inventory_digest,
    evaluate_contextual_access_run,
    validate_contextual_observations,
    validate_contextual_run_plan,
)
from synthworld.contextual_access.reference import (
    ReferenceContextualAccessV1,
    reference_contextual_access,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.models import SyntheticModel

REFERENCE_CONTEXTUAL_RUN_ID = "contextual-reference-run-1"
REFERENCE_CONTEXT_FEED_COMPONENT_ID = "reference-context-feed"
REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID = "reference-contextual-sut"


@dataclass(frozen=True, slots=True)
class ReferenceContextualRunV1:
    benchmark: ReferenceContextualAccessV1
    systems_under_test: tuple[SystemComponentProvenanceV2, ...]
    plan: ContextualAccessRunPlanV1
    observations: ContextualAccessObservationsV1
    truth: ContextualAccessRunTruthV1
    report: ContextualAccessReportV1


def reference_contextual_access_run() -> ReferenceContextualRunV1:
    """Build perfect external-run records without executing a runtime system."""

    benchmark = reference_contextual_access()
    public = benchmark.public
    systems = _reference_components()
    labels = {item.kind: item for item in benchmark.evaluator.truth.case_labels}
    faults = tuple(
        sorted(
            (
                _fault(
                    ContextualFaultKind.DELAYED_DELIVERY,
                    labels[ContextualCaseKind.DELAYED_DELIVERY].transition_event_ids,
                    public,
                ),
                _fault(
                    ContextualFaultKind.DUPLICATE_DELIVERY,
                    labels[ContextualCaseKind.DUPLICATE_DELIVERY].transition_event_ids,
                    public,
                ),
                _fault(
                    ContextualFaultKind.OUT_OF_ORDER_DELIVERY,
                    labels[
                        ContextualCaseKind.OUT_OF_ORDER_DELIVERY
                    ].transition_event_ids,
                    public,
                ),
            ),
            key=lambda item: item.fault_id,
        )
    )
    probes = _probes(benchmark, faults)
    plan = ContextualAccessRunPlanV1(
        run_id=REFERENCE_CONTEXTUAL_RUN_ID,
        benchmark=ContextualBenchmarkBindingV1(
            enterprise_public_root_digest=_digest(public.universe),
            contextual_public_root_digest=_digest(public),
            identity_access_universe_digest=_copy_digest(
                public.benchmark.identity_access_universe_digest.value
            ),
            access_atom_digest=_copy_digest(public.benchmark.access_atom_digest.value),
            registry_digest=_copy_digest(public.benchmark.registry_digest.value),
            request_digest=_copy_digest(public.benchmark.request_digest.value),
            public_case_inventory_digest=contextual_public_case_inventory_digest(
                public
            ),
        ),
        mapping_profile_digest=_copy_digest(
            public.benchmark.mapping_profile_digest.value
        ),
        event_schedule_version=public.benchmark.event_schedule_version,
        request_ids=tuple(item.request_id for item in public.requests),
        event_ids=tuple(item.id for item in public.events),
        delivery_attempt_ids=tuple(
            item.attempt_id for item in public.delivery_attempts
        ),
        sut_component_ids=(REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID,),
        context_feed_component_ids=(REFERENCE_CONTEXT_FEED_COMPONENT_ID,),
        faults=faults,
        bounds=ContextualRunBoundsV1(
            feed_delay_bound_ticks=8,
            sut_acceptance_bound_ns=1_000_000,
            post_acceptance_decision_bound_ns=2_000_000,
        ),
        required_evidence_kinds=(EvidenceKind.TRACE,),
        control_coverage=tuple(
            ContextualControlCoverageV1(
                control_id=item,
                disposition=ContextualCoverageDisposition.SELECTED,
            )
            for item in ContextualControlId
        ),
        probes=probes,
    )
    validate_contextual_run_plan(plan, public=public, systems_under_test=systems)
    truth = compile_contextual_run_truth(
        plan,
        public=public,
        evaluator=benchmark.evaluator,
    )
    observations = _perfect_observations(plan, truth, public)
    validate_contextual_observations(plan, observations)
    report = evaluate_contextual_access_run(plan, observations, truth)
    return ReferenceContextualRunV1(
        benchmark=benchmark,
        systems_under_test=systems,
        plan=plan,
        observations=observations,
        truth=truth,
        report=report,
    )


def _reference_components() -> tuple[SystemComponentProvenanceV2, ...]:
    components = tuple(
        ReferenceComponentProvenanceV2(
            component_id=component_id,
            role=role,
            name=name,
            version="1.0.0",
            artifact_kind=ComponentArtifactKindV2.SOURCE,
            artifact_digest=_label_digest(f"{component_id}:source"),
            dependency_lock_digest=_label_digest(f"{component_id}:lock"),
            configuration_digest=_label_digest(f"{component_id}:config"),
            tree_state=TreeState.CLEAN,
            replayability=ReplayabilityV2.EXACT,
        )
        for component_id, role, name in (
            (
                REFERENCE_CONTEXT_FEED_COMPONENT_ID,
                "context_feed",
                "Fictional Context Feed",
            ),
            (
                REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID,
                "authorization_and_enforcement",
                "Fictional Authorization System",
            ),
        )
    )
    return tuple(sorted(components, key=lambda item: item.component_id))


def _fault(
    kind: ContextualFaultKind,
    event_ids: tuple[str, ...],
    public: ContextualAccessPublicV1,
) -> ContextualFaultV1:
    attempts = tuple(
        sorted(
            (item for item in public.delivery_attempts if item.event_id in event_ids),
            key=lambda item: item.attempt_id,
        )
    )
    events = {item.id: item for item in public.events}
    return ContextualFaultV1(
        fault_id=f"fault:{kind.value}",
        kind=kind,
        component_id=REFERENCE_CONTEXT_FEED_COMPONENT_ID,
        event_ids=event_ids,
        delivery_attempt_ids=tuple(item.attempt_id for item in attempts),
        injection_tick=min(events[item].effective_tick for item in event_ids),
        recovery_tick=max(item.delivery_tick for item in attempts),
    )


def _probes(
    benchmark: ReferenceContextualAccessV1,
    faults: tuple[ContextualFaultV1, ...],
) -> tuple[
    MappingIngestionProbeV1
    | AccessDecisionProbeV1
    | ProtectedEnforcementProbeV1
    | DeliveryAcceptanceProbeV1
    | SynchronizationFaultProbeV1
    | EvidenceCorrelationProbeV1,
    ...,
]:
    public = benchmark.public
    labels = {item.request_id: item for item in benchmark.evaluator.truth.case_labels}
    probes: list[
        MappingIngestionProbeV1
        | AccessDecisionProbeV1
        | ProtectedEnforcementProbeV1
        | DeliveryAcceptanceProbeV1
        | SynchronizationFaultProbeV1
        | EvidenceCorrelationProbeV1
    ] = []
    for mapping in public.mapping_profile.mappings:
        probes.append(
            MappingIngestionProbeV1(
                probe_id=f"probe:mapping:{mapping.fact_type.value}",
                component_id=REFERENCE_CONTEXT_FEED_COMPONENT_ID,
                fact_type=mapping.fact_type,
                mapping_kind=mapping.mapping_kind,
            )
        )
    for request in public.requests:
        transition_ids = labels[request.request_id].transition_event_ids
        probes.extend(
            (
                AccessDecisionProbeV1(
                    probe_id=f"probe:decision:{request.request_id}",
                    component_id=REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID,
                    request_id=request.request_id,
                    trigger_event_id=transition_ids[0] if transition_ids else None,
                ),
                ProtectedEnforcementProbeV1(
                    probe_id=f"probe:enforcement:{request.request_id}",
                    component_id=REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID,
                    request_id=request.request_id,
                ),
                EvidenceCorrelationProbeV1(
                    probe_id=f"probe:evidence:{request.request_id}",
                    component_id=REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID,
                    request_id=request.request_id,
                    required_evidence_kind=EvidenceKind.TRACE,
                ),
            )
        )
    for attempt in public.delivery_attempts:
        probes.append(
            DeliveryAcceptanceProbeV1(
                probe_id=f"probe:delivery:{attempt.attempt_id}",
                component_id=REFERENCE_CONTEXT_FEED_COMPONENT_ID,
                event_id=attempt.event_id,
                delivery_attempt_id=attempt.attempt_id,
            )
        )
    for fault in faults:
        probes.append(
            SynchronizationFaultProbeV1(
                probe_id=f"probe:sync:{fault.fault_id}",
                component_id=REFERENCE_CONTEXT_FEED_COMPONENT_ID,
                fault_id=fault.fault_id,
            )
        )
    return tuple(sorted(probes, key=lambda item: item.probe_id))


def _perfect_observations(
    plan: ContextualAccessRunPlanV1,
    truth: ContextualAccessRunTruthV1,
    public: ContextualAccessPublicV1,
) -> ContextualAccessObservationsV1:
    evidence_handle = EvidenceHandleV1(
        handle="evidence:reference-trace",
        kind=EvidenceKind.TRACE,
        digest=_label_digest("reference contextual trace"),
        collection_status=CollectionStatus.COLLECTED,
        redaction_status=RedactionStatus.NOT_REQUIRED,
    )
    evidence_refs = (evidence_handle.handle,)
    observations: list[
        MappingIngestionObservationV1
        | AccessDecisionObservationV1
        | ProtectedEnforcementObservationV1
        | ContextDeliveryAcceptanceObservationV1
        | SynchronizationFaultObservationV1
        | EvidenceCorrelationObservationV1
    ] = []
    probes = {item.probe_id: item for item in plan.probes}
    for row in truth.rows:
        probe = probes[row.probe_id]
        observation_id = f"observation:{row.probe_id}"
        if isinstance(row, MappingIngestionTruthV1):
            observations.append(
                MappingIngestionObservationV1(
                    observation_id=observation_id,
                    probe_id=row.probe_id,
                    component_id=probe.component_id,
                    evidence_refs=evidence_refs,
                    fact_type=row.fact_type,
                    mapping_kind=row.mapping_kind,
                    status=MappingIngestionStatus.INGESTED,
                )
            )
        elif isinstance(row, AccessDecisionRunTruthV1):
            request_tick = next(
                item.request_tick
                for item in public.requests
                if item.request_id == row.request_id
            )
            observations.append(
                AccessDecisionObservationV1(
                    observation_id=observation_id,
                    probe_id=row.probe_id,
                    component_id=probe.component_id,
                    evidence_refs=evidence_refs,
                    request_id=row.request_id,
                    trigger_event_id=row.trigger_event_id,
                    accepted_delivery_attempt_id=row.accepted_delivery_attempt_id,
                    policy_version_ids=row.required_policy_version_ids,
                    attempts=(
                        ContextualDecisionAttemptV1(
                            decision_tick=request_tick,
                            decision=ObservedDecision(row.expected_decision.value),
                            elapsed_ns_from_acceptance=(
                                1_000 if row.trigger_event_id is not None else None
                            ),
                        ),
                    ),
                )
            )
        elif isinstance(row, ProtectedEnforcementTruthV1):
            observations.append(
                ProtectedEnforcementObservationV1(
                    observation_id=observation_id,
                    probe_id=row.probe_id,
                    component_id=probe.component_id,
                    evidence_refs=evidence_refs,
                    request_id=row.request_id,
                    decision=ObservedDecision(row.expected_decision.value),
                    side_effect=row.expected_side_effect,
                )
            )
        elif isinstance(row, DeliveryAcceptanceTruthV1):
            observations.append(
                ContextDeliveryAcceptanceObservationV1(
                    observation_id=observation_id,
                    probe_id=row.probe_id,
                    component_id=probe.component_id,
                    evidence_refs=evidence_refs,
                    event_id=row.event_id,
                    delivery_attempt_id=row.delivery_attempt_id,
                    projected_event_tick=row.effective_tick,
                    set_issue_tick=row.effective_tick,
                    observed_delivery_tick=row.delivery_tick,
                    accepted=True,
                    acceptance_elapsed_ns=500,
                )
            )
        elif isinstance(row, SynchronizationFaultTruthV1):
            observations.append(
                SynchronizationFaultObservationV1(
                    observation_id=observation_id,
                    probe_id=row.probe_id,
                    component_id=probe.component_id,
                    evidence_refs=evidence_refs,
                    fault_id=row.fault_id,
                    status=SynchronizationFaultStatus.RECOVERED,
                    recovery_elapsed_ns=1_000,
                )
            )
        else:
            observations.append(
                EvidenceCorrelationObservationV1(
                    observation_id=observation_id,
                    probe_id=row.probe_id,
                    component_id=probe.component_id,
                    evidence_refs=evidence_refs,
                    request_id=row.request_id,
                    evidence_kind=row.required_evidence_kind,
                    correlated=True,
                )
            )
    return ContextualAccessObservationsV1(
        run_id=plan.run_id,
        observations=tuple(sorted(observations, key=lambda item: item.observation_id)),
        evidence_handles=(evidence_handle,),
    )


def _digest(value: SyntheticModel) -> DigestV2:
    return DigestV2(value=synthetic_digest(canonical_json_bytes(value)).value)


def _label_digest(value: str) -> DigestV2:
    return DigestV2(value=synthetic_digest(value.encode("utf-8")).value)


def _copy_digest(value: str) -> DigestV2:
    return DigestV2(value=value)


__all__ = [
    "REFERENCE_CONTEXTUAL_RUN_ID",
    "REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID",
    "REFERENCE_CONTEXT_FEED_COMPONENT_ID",
    "ReferenceContextualRunV1",
    "reference_contextual_access_run",
]
