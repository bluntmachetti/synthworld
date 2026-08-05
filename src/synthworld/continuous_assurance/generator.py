"""Deterministic longitudinal assurance generation over four concrete consumers."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from pydantic import BaseModel

from synthworld.agentic.enterprise.models import (
    EnterpriseAgenticEvaluatorArtifactsV1,
    EnterpriseAgenticPublicInputV1,
)
from synthworld.authority_governance.models import (
    AuthorityGovernanceEvaluatorV1,
    AuthorityGovernancePublicV1,
)
from synthworld.authority_governance.replay import (
    validate_authority_governance_evaluator,
)
from synthworld.contextual_access.models import (
    ContextualAccessEvaluatorV1,
    ContextualAccessPublicV1,
)
from synthworld.contextual_access.projection import validate_contextual_access_public
from synthworld.continuous_assurance.models import (
    CONTINUOUS_ASSURANCE_GENERATOR_VERSION,
    AssuranceDriftKind,
    AssuranceObservedState,
    ContinuousAssuranceBenchmarkBindingV1,
    ContinuousAssuranceCaseKind,
    ContinuousAssuranceCaseTruthV1,
    ContinuousAssuranceCaseV1,
    ContinuousAssuranceCheckpointV1,
    ContinuousAssuranceConfigV1,
    ContinuousAssuranceEvaluatorSourceBindingV1,
    ContinuousAssuranceEvaluatorV1,
    ContinuousAssuranceFeedWindowV1,
    ContinuousAssuranceFindingTransitionTruthV1,
    ContinuousAssurancePublicV1,
    ContinuousAssuranceRemediationV1,
    ContinuousAssuranceSignalV1,
    ContinuousAssuranceSourceBindingV1,
    ContinuousAssuranceSourceFamily,
    ContinuousAssuranceSourceReferenceV1,
    ContinuousAssuranceTier,
    FindingLifecycleState,
)
from synthworld.continuous_assurance.replay import (
    source_public_bindings_digest,
    validate_continuous_assurance_evaluator,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
    encode_parts,
    synthetic_digest,
)
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricEvaluatorArtifactsV1,
    EnterpriseIdentityFabricPublicInputV1,
)

CONTINUOUS_ASSURANCE_NAMESPACE_V1 = UUID("0b58d726-27ef-5bb8-b745-b959bad94582")


@dataclass(frozen=True, slots=True)
class ContinuousAssuranceSourceInputsV1:
    identity_fabric_public: EnterpriseIdentityFabricPublicInputV1
    identity_fabric_evaluator: EnterpriseIdentityFabricEvaluatorArtifactsV1
    enterprise_agentic_public: EnterpriseAgenticPublicInputV1
    enterprise_agentic_evaluator: EnterpriseAgenticEvaluatorArtifactsV1
    contextual_access_public: ContextualAccessPublicV1
    contextual_access_evaluator: ContextualAccessEvaluatorV1
    authority_governance_public: AuthorityGovernancePublicV1
    authority_governance_evaluator: AuthorityGovernanceEvaluatorV1


@dataclass(frozen=True, slots=True)
class ContinuousAssuranceBenchmarkV1:
    config: ContinuousAssuranceConfigV1
    public: ContinuousAssurancePublicV1
    evaluator: ContinuousAssuranceEvaluatorV1


@dataclass(frozen=True, slots=True)
class _SourceRecord:
    family: ContinuousAssuranceSourceFamily
    record_id: str
    model: BaseModel


@dataclass(frozen=True, slots=True)
class _CaseTemplate:
    name: str
    kind: ContinuousAssuranceCaseKind
    dimension: AssuranceDriftKind
    family: ContinuousAssuranceSourceFamily
    finding_required: bool
    initial_state: AssuranceObservedState
    remediation_state: AssuranceObservedState | None
    remediation_complete: bool | None
    evidence_continuous: bool | None
    recurrence: bool = False
    delayed_feed: bool = False
    later_state: AssuranceObservedState | None = None
    clear_on_later_state: bool = False
    failure_reasons: tuple[str, ...] = ()


_TEMPLATES = (
    _CaseTemplate(
        "entitlement-transient",
        ContinuousAssuranceCaseKind.ENTITLEMENT_TRANSIENT_DRIFT,
        AssuranceDriftKind.ENTITLEMENT,
        ContinuousAssuranceSourceFamily.IDENTITY_FABRIC_1_0,
        True,
        AssuranceObservedState.PRESENT,
        AssuranceObservedState.WITHDRAWN,
        True,
        True,
        failure_reasons=("entitlement_outside_intent",),
    ),
    _CaseTemplate(
        "owner-incomplete-remediation",
        ContinuousAssuranceCaseKind.OWNER_DRIFT,
        AssuranceDriftKind.OWNER,
        ContinuousAssuranceSourceFamily.IDENTITY_FABRIC_1_0,
        True,
        AssuranceObservedState.MISSING,
        AssuranceObservedState.CHANGED,
        False,
        True,
        failure_reasons=("accountable_owner_missing", "remediation_incomplete"),
    ),
    _CaseTemplate(
        "credential-revocation",
        ContinuousAssuranceCaseKind.CREDENTIAL_DRIFT,
        AssuranceDriftKind.CREDENTIAL,
        ContinuousAssuranceSourceFamily.ENTERPRISE_AGENTIC_1_0,
        True,
        AssuranceObservedState.ACTIVE,
        AssuranceObservedState.INACTIVE,
        True,
        True,
        failure_reasons=("credential_active_after_revocation",),
    ),
    _CaseTemplate(
        "delegation-recurrence",
        ContinuousAssuranceCaseKind.DELEGATION_RECURRENCE,
        AssuranceDriftKind.DELEGATION,
        ContinuousAssuranceSourceFamily.ENTERPRISE_AGENTIC_1_0,
        True,
        AssuranceObservedState.ACTIVE,
        AssuranceObservedState.INACTIVE,
        True,
        True,
        recurrence=True,
        failure_reasons=("delegation_recurred",),
    ),
    _CaseTemplate(
        "later-policy",
        ContinuousAssuranceCaseKind.POLICY_LATER_VERSION,
        AssuranceDriftKind.POLICY,
        ContinuousAssuranceSourceFamily.AUTHORITY_GOVERNANCE_1_0,
        True,
        AssuranceObservedState.CHANGED,
        None,
        None,
        True,
        later_state=AssuranceObservedState.HEALTHY,
        failure_reasons=("later_policy_does_not_authorise_prior_state",),
    ),
    _CaseTemplate(
        "late-evidence",
        ContinuousAssuranceCaseKind.EVIDENCE_LATE_ARRIVAL,
        AssuranceDriftKind.EVIDENCE,
        ContinuousAssuranceSourceFamily.AUTHORITY_GOVERNANCE_1_0,
        True,
        AssuranceObservedState.MISSING,
        None,
        None,
        False,
        later_state=AssuranceObservedState.RETAINED,
        clear_on_later_state=True,
        failure_reasons=("late_evidence_does_not_retroactively_validate",),
    ),
    _CaseTemplate(
        "feed-outage-delay",
        ContinuousAssuranceCaseKind.FEED_OUTAGE_DELAY,
        AssuranceDriftKind.ENTITLEMENT,
        ContinuousAssuranceSourceFamily.CONTEXTUAL_ACCESS_1_0,
        True,
        AssuranceObservedState.PRESENT,
        AssuranceObservedState.WITHDRAWN,
        True,
        False,
        delayed_feed=True,
        failure_reasons=("observation_delayed_by_feed_outage",),
    ),
    _CaseTemplate(
        "stable-control",
        ContinuousAssuranceCaseKind.STABLE_CONTROL,
        AssuranceDriftKind.POLICY,
        ContinuousAssuranceSourceFamily.CONTEXTUAL_ACCESS_1_0,
        False,
        AssuranceObservedState.HEALTHY,
        None,
        None,
        None,
    ),
)

_TIER_REPETITIONS = {
    ContinuousAssuranceTier.SMOKE: 1,
    ContinuousAssuranceTier.STANDARD: 3,
    ContinuousAssuranceTier.LONGITUDINAL: 6,
    ContinuousAssuranceTier.HELD_OUT: 3,
}


def generate_continuous_assurance(
    *,
    sources: ContinuousAssuranceSourceInputsV1,
    config: ContinuousAssuranceConfigV1,
) -> ContinuousAssuranceBenchmarkV1:
    """Generate a pure benchmark from explicit source artifacts and configuration."""

    _validate_source_bindings(sources)
    public_bindings, evaluator_bindings = _source_bindings(sources)
    catalog = _source_catalog(sources)
    signals: list[ContinuousAssuranceSignalV1] = []
    remediations: list[ContinuousAssuranceRemediationV1] = []
    windows: list[ContinuousAssuranceFeedWindowV1] = []
    cases: list[ContinuousAssuranceCaseV1] = []
    truth: list[ContinuousAssuranceCaseTruthV1] = []

    templates = _ordered_templates(config)
    repetitions = _TIER_REPETITIONS[config.tier]
    offset = config.seed % 7
    for cycle in range(repetitions):
        for position, template in enumerate(templates):
            base_tick = 1 + offset + cycle * 200 + position * 20
            generated = _generate_case(
                config=config,
                template=template,
                cycle=cycle,
                base_tick=base_tick,
                record=_select_source_record(
                    catalog[template.family], config, cycle, position
                ),
            )
            case, case_signals, case_remediations, window, case_truth = generated
            cases.append(case)
            signals.extend(case_signals)
            remediations.extend(case_remediations)
            if window is not None:
                windows.append(window)
            truth.append(case_truth)

    ordered_cases = tuple(sorted(cases, key=lambda item: item.case_id))
    ordered_signals = tuple(
        sorted(signals, key=lambda item: (item.effective_tick, item.signal_id))
    )
    ordered_remediations = tuple(
        sorted(
            remediations,
            key=lambda item: (item.effective_tick, item.remediation_id),
        )
    )
    ordered_windows = tuple(sorted(windows, key=lambda item: item.feed_window_id))
    horizon_tick = (
        max(
            *(item.audit_tick for item in ordered_signals),
            *(item.audit_tick for item in ordered_remediations),
            *(item.restored_at_tick for item in ordered_windows),
        )
        + 3
    )
    checkpoints = _checkpoints(
        config=config,
        signals=ordered_signals,
        remediations=ordered_remediations,
        truth=tuple(truth),
        horizon_tick=horizon_tick,
    )
    case_digest = synthetic_digest(
        canonical_json_value_bytes(
            tuple(item.model_dump(mode="json") for item in ordered_cases)
        )
    )
    benchmark_binding = ContinuousAssuranceBenchmarkBindingV1(
        tier=config.tier,
        source_public_bindings_digest=source_public_bindings_digest(public_bindings),
        case_inventory_digest=case_digest,
        policy_profile_id=_stable_id(config, "policy-profile"),
    )
    public = ContinuousAssurancePublicV1(
        benchmark=benchmark_binding,
        horizon_tick=horizon_tick,
        source_bindings=public_bindings,
        signals=ordered_signals,
        remediations=ordered_remediations,
        feed_windows=ordered_windows,
        cases=ordered_cases,
        checkpoints=checkpoints,
    )
    truth_by_id = {item.case_id: item for item in truth}
    evaluator = ContinuousAssuranceEvaluatorV1(
        public_digest=synthetic_digest(canonical_json_bytes(public)),
        private_config_digest=synthetic_digest(canonical_json_bytes(config)),
        source_bindings=evaluator_bindings,
        truth=tuple(truth_by_id[item.case_id] for item in ordered_cases),
    )
    validate_continuous_assurance_evaluator(public, evaluator)
    return ContinuousAssuranceBenchmarkV1(
        config=config,
        public=public,
        evaluator=evaluator,
    )


def _generate_case(
    *,
    config: ContinuousAssuranceConfigV1,
    template: _CaseTemplate,
    cycle: int,
    base_tick: int,
    record: _SourceRecord,
) -> tuple[
    ContinuousAssuranceCaseV1,
    tuple[ContinuousAssuranceSignalV1, ...],
    tuple[ContinuousAssuranceRemediationV1, ...],
    ContinuousAssuranceFeedWindowV1 | None,
    ContinuousAssuranceCaseTruthV1,
]:
    case_id = _stable_id(config, "case", str(cycle), template.name)
    source = ContinuousAssuranceSourceReferenceV1(
        family=record.family,
        record_id=record.record_id,
        record_digest=synthetic_digest(canonical_json_bytes(record.model)),
    )
    observation_tick = base_tick + 4
    window: ContinuousAssuranceFeedWindowV1 | None = None
    if template.delayed_feed:
        observation_tick = base_tick + 9
    first_signal = ContinuousAssuranceSignalV1(
        signal_id=_stable_id(config, "signal", str(cycle), template.name, "initial"),
        case_id=case_id,
        dimension=template.dimension,
        source=source,
        observed_state=template.initial_state,
        action_tick=base_tick + 1,
        decision_tick=base_tick + 2,
        effective_tick=base_tick + 3,
        observation_tick=observation_tick,
        audit_tick=observation_tick + 1,
        policy_version_id=_policy_version(config, cycle, "decision"),
        evidence_refs=(
            _stable_id(config, "evidence", str(cycle), template.name, "initial"),
        ),
    )
    signals = [first_signal]
    remediation_rows: list[ContinuousAssuranceRemediationV1] = []
    lifecycle: list[ContinuousAssuranceFindingTransitionTruthV1] = []
    recurrence_ticks: tuple[int, ...] = ()
    expected_clears: list[int] = []
    if template.finding_required:
        lifecycle.append(
            ContinuousAssuranceFindingTransitionTruthV1(
                tick=observation_tick,
                state=FindingLifecycleState.OPEN,
            )
        )

    if template.remediation_state is not None:
        remediation = _remediation(
            config=config,
            case_id=case_id,
            template=template,
            cycle=cycle,
            suffix="primary",
            base_tick=observation_tick + 1,
        )
        remediation_rows.append(remediation)
        if template.remediation_complete:
            expected_clears.append(remediation.observation_tick)
            lifecycle.append(
                ContinuousAssuranceFindingTransitionTruthV1(
                    tick=remediation.observation_tick,
                    state=FindingLifecycleState.CLEAR,
                )
            )

    if template.later_state is not None:
        later = ContinuousAssuranceSignalV1(
            signal_id=_stable_id(config, "signal", str(cycle), template.name, "later"),
            case_id=case_id,
            dimension=template.dimension,
            source=source,
            observed_state=template.later_state,
            action_tick=observation_tick + 2,
            decision_tick=observation_tick + 3,
            effective_tick=observation_tick + 4,
            observation_tick=observation_tick + 5,
            audit_tick=observation_tick + 6,
            policy_version_id=_policy_version(config, cycle, "later"),
            evidence_refs=(
                _stable_id(config, "evidence", str(cycle), template.name, "later"),
            ),
        )
        signals.append(later)
        if template.clear_on_later_state:
            expected_clears.append(later.observation_tick)
            lifecycle.append(
                ContinuousAssuranceFindingTransitionTruthV1(
                    tick=later.observation_tick,
                    state=FindingLifecycleState.CLEAR,
                )
            )

    if template.recurrence:
        recurrence = ContinuousAssuranceSignalV1(
            signal_id=_stable_id(
                config, "signal", str(cycle), template.name, "recurrence"
            ),
            case_id=case_id,
            dimension=template.dimension,
            source=source,
            observed_state=template.initial_state,
            action_tick=observation_tick + 10,
            decision_tick=observation_tick + 11,
            effective_tick=observation_tick + 12,
            observation_tick=observation_tick + 13,
            audit_tick=observation_tick + 14,
            policy_version_id=_policy_version(config, cycle, "decision"),
            evidence_refs=(
                _stable_id(config, "evidence", str(cycle), template.name, "recurrence"),
            ),
        )
        signals.append(recurrence)
        recurrence_ticks = (recurrence.observation_tick,)
        lifecycle.append(
            ContinuousAssuranceFindingTransitionTruthV1(
                tick=recurrence.observation_tick,
                state=FindingLifecycleState.OPEN,
            )
        )
        recurrence_remediation = _remediation(
            config=config,
            case_id=case_id,
            template=template,
            cycle=cycle,
            suffix="recurrence",
            base_tick=recurrence.observation_tick + 1,
        )
        remediation_rows.append(recurrence_remediation)
        recurrence_clear = recurrence_remediation.observation_tick
        expected_clears.append(recurrence_clear)
        lifecycle.append(
            ContinuousAssuranceFindingTransitionTruthV1(
                tick=recurrence_clear,
                state=FindingLifecycleState.CLEAR,
            )
        )

    if template.delayed_feed:
        window = ContinuousAssuranceFeedWindowV1(
            feed_window_id=_stable_id(config, "feed-window", str(cycle), template.name),
            source_family=template.family,
            unavailable_from_tick=base_tick + 2,
            restored_at_tick=base_tick + 8,
            delayed_signal_ids=(first_signal.signal_id,),
        )

    case = ContinuousAssuranceCaseV1(
        case_id=case_id,
        signal_ids=tuple(sorted(item.signal_id for item in signals)),
        remediation_ids=tuple(sorted(item.remediation_id for item in remediation_rows)),
        feed_window_id=None if window is None else window.feed_window_id,
    )
    truth = ContinuousAssuranceCaseTruthV1(
        case_id=case_id,
        case_kind=template.kind,
        drift_kind=template.dimension if template.finding_required else None,
        finding_required=template.finding_required,
        drift_effective_tick=(
            first_signal.effective_tick if template.finding_required else None
        ),
        first_observable_tick=(observation_tick if template.finding_required else None),
        expected_finding_opened_tick=(
            observation_tick if template.finding_required else None
        ),
        expected_finding_cleared_ticks=tuple(sorted(expected_clears)),
        expected_remediation_complete=template.remediation_complete,
        expected_recurrence_opened_ticks=recurrence_ticks,
        expected_evidence_continuous=template.evidence_continuous,
        canonical_policy_version_id=_policy_version(config, cycle, "decision"),
        lifecycle=tuple(
            sorted(lifecycle, key=lambda item: (item.tick, item.state.value))
        ),
        failure_reasons=tuple(sorted(template.failure_reasons)),
    )
    return (
        case,
        tuple(signals),
        tuple(remediation_rows),
        window,
        truth,
    )


def _remediation(
    *,
    config: ContinuousAssuranceConfigV1,
    case_id: str,
    template: _CaseTemplate,
    cycle: int,
    suffix: str,
    base_tick: int,
) -> ContinuousAssuranceRemediationV1:
    if template.remediation_state is None:
        raise ValueError("remediation template has no remediation state")
    return ContinuousAssuranceRemediationV1(
        remediation_id=_stable_id(
            config, "remediation", str(cycle), template.name, suffix
        ),
        case_id=case_id,
        dimension=template.dimension,
        observed_state=template.remediation_state,
        action_tick=base_tick,
        decision_tick=base_tick + 1,
        effective_tick=base_tick + 2,
        observation_tick=base_tick + 3,
        audit_tick=base_tick + 4,
        evidence_refs=(
            _stable_id(
                config, "evidence", str(cycle), template.name, f"remediation-{suffix}"
            ),
        ),
    )


def _checkpoints(
    *,
    config: ContinuousAssuranceConfigV1,
    signals: tuple[ContinuousAssuranceSignalV1, ...],
    remediations: tuple[ContinuousAssuranceRemediationV1, ...],
    truth: tuple[ContinuousAssuranceCaseTruthV1, ...],
    horizon_tick: int,
) -> tuple[ContinuousAssuranceCheckpointV1, ...]:
    ticks = {
        0,
        horizon_tick,
        *(item.effective_tick for item in signals),
        *(item.observation_tick for item in signals),
        *(item.audit_tick for item in signals),
        *(item.effective_tick for item in remediations),
        *(item.observation_tick for item in remediations),
        *(item.audit_tick for item in remediations),
        *(transition.tick for row in truth for transition in row.lifecycle),
    }
    return tuple(
        ContinuousAssuranceCheckpointV1(
            checkpoint_id=_stable_id(config, "checkpoint", str(tick)),
            tick=tick,
            observed_signal_ids=tuple(
                sorted(
                    item.signal_id for item in signals if item.observation_tick <= tick
                )
            ),
            observed_remediation_ids=tuple(
                sorted(
                    item.remediation_id
                    for item in remediations
                    if item.observation_tick <= tick
                )
            ),
            available_evidence_refs=tuple(
                sorted(
                    {
                        evidence
                        for item in signals
                        if item.audit_tick <= tick
                        for evidence in item.evidence_refs
                    }
                    | {
                        evidence
                        for item in remediations
                        if item.audit_tick <= tick
                        for evidence in item.evidence_refs
                    }
                )
            ),
        )
        for tick in sorted(ticks)
    )


def _source_bindings(
    sources: ContinuousAssuranceSourceInputsV1,
) -> tuple[
    tuple[ContinuousAssuranceSourceBindingV1, ...],
    tuple[ContinuousAssuranceEvaluatorSourceBindingV1, ...],
]:
    rows = (
        (
            ContinuousAssuranceSourceFamily.IDENTITY_FABRIC_1_0,
            sources.identity_fabric_public,
            sources.identity_fabric_evaluator,
        ),
        (
            ContinuousAssuranceSourceFamily.ENTERPRISE_AGENTIC_1_0,
            sources.enterprise_agentic_public,
            sources.enterprise_agentic_evaluator,
        ),
        (
            ContinuousAssuranceSourceFamily.CONTEXTUAL_ACCESS_1_0,
            sources.contextual_access_public,
            sources.contextual_access_evaluator,
        ),
        (
            ContinuousAssuranceSourceFamily.AUTHORITY_GOVERNANCE_1_0,
            sources.authority_governance_public,
            sources.authority_governance_evaluator,
        ),
    )
    evaluator = tuple(
        sorted(
            (
                ContinuousAssuranceEvaluatorSourceBindingV1(
                    family=family,
                    public_schema_version=public.schema_version,
                    public_digest=synthetic_digest(canonical_json_bytes(public)),
                    evaluator_schema_version=evaluator.schema_version,
                    evaluator_digest=synthetic_digest(canonical_json_bytes(evaluator)),
                )
                for family, public, evaluator in rows
            ),
            key=lambda item: item.family.value,
        )
    )
    public = tuple(
        ContinuousAssuranceSourceBindingV1(
            family=item.family,
            public_schema_version=item.public_schema_version,
            public_digest=item.public_digest,
        )
        for item in evaluator
    )
    return public, evaluator


def _source_catalog(
    sources: ContinuousAssuranceSourceInputsV1,
) -> dict[ContinuousAssuranceSourceFamily, tuple[_SourceRecord, ...]]:
    return {
        ContinuousAssuranceSourceFamily.IDENTITY_FABRIC_1_0: tuple(
            _SourceRecord(
                family=ContinuousAssuranceSourceFamily.IDENTITY_FABRIC_1_0,
                record_id=item.checkpoint_id,
                model=item,
            )
            for item in sources.identity_fabric_public.checkpoints
        ),
        ContinuousAssuranceSourceFamily.ENTERPRISE_AGENTIC_1_0: tuple(
            _SourceRecord(
                family=ContinuousAssuranceSourceFamily.ENTERPRISE_AGENTIC_1_0,
                record_id=item.id,
                model=item,
            )
            for item in sources.enterprise_agentic_public.events
        ),
        ContinuousAssuranceSourceFamily.CONTEXTUAL_ACCESS_1_0: tuple(
            _SourceRecord(
                family=ContinuousAssuranceSourceFamily.CONTEXTUAL_ACCESS_1_0,
                record_id=item.id,
                model=item,
            )
            for item in sources.contextual_access_public.events
        ),
        ContinuousAssuranceSourceFamily.AUTHORITY_GOVERNANCE_1_0: tuple(
            _SourceRecord(
                family=ContinuousAssuranceSourceFamily.AUTHORITY_GOVERNANCE_1_0,
                record_id=item.id,
                model=item,
            )
            for item in sources.authority_governance_public.events
        ),
    }


def _validate_source_bindings(sources: ContinuousAssuranceSourceInputsV1) -> None:
    pairs = (
        (
            sources.identity_fabric_public,
            sources.identity_fabric_evaluator.public_input_digest,
        ),
        (
            sources.enterprise_agentic_public,
            sources.enterprise_agentic_evaluator.public_input_digest,
        ),
        (
            sources.contextual_access_public,
            sources.contextual_access_evaluator.public_digest,
        ),
    )
    for public, bound_digest in pairs:
        if synthetic_digest(canonical_json_bytes(public)) != bound_digest:
            raise ValueError("continuous-assurance source evaluator binding differs")
    validate_contextual_access_public(sources.contextual_access_public)
    validate_authority_governance_evaluator(
        sources.authority_governance_public,
        sources.authority_governance_evaluator,
    )


def _ordered_templates(
    config: ContinuousAssuranceConfigV1,
) -> tuple[_CaseTemplate, ...]:
    if config.tier is not ContinuousAssuranceTier.HELD_OUT:
        return _TEMPLATES
    return tuple(
        sorted(
            _TEMPLATES,
            key=lambda item: _stable_id(config, "template-order", item.name),
        )
    )


def _select_source_record(
    records: tuple[_SourceRecord, ...],
    config: ContinuousAssuranceConfigV1,
    cycle: int,
    position: int,
) -> _SourceRecord:
    if not records:
        raise ValueError("continuous-assurance source family has no records")
    index = (config.seed + config.risk_threshold + cycle + position) % len(records)
    return records[index]


def _policy_version(config: ContinuousAssuranceConfigV1, cycle: int, phase: str) -> str:
    return (
        f"policy:{phase}:risk-{config.risk_threshold}:"
        f"{config.justification_kind}:cycle-{cycle}"
    )


def _stable_id(config: ContinuousAssuranceConfigV1, *parts: str) -> str:
    return str(
        uuid5(
            CONTINUOUS_ASSURANCE_NAMESPACE_V1,
            encode_parts(
                (
                    CONTINUOUS_ASSURANCE_GENERATOR_VERSION,
                    config.tier.value,
                    str(config.seed),
                    str(config.risk_threshold),
                    config.justification_kind,
                    *parts,
                )
            ),
        )
    )


__all__ = [
    "CONTINUOUS_ASSURANCE_NAMESPACE_V1",
    "ContinuousAssuranceBenchmarkV1",
    "ContinuousAssuranceSourceInputsV1",
    "generate_continuous_assurance",
]
