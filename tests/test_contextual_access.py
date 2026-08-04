"""End-to-end contextual-access smoke generation, policy, and metrics tests."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

import pytest

from synthworld.contextual_access.baselines import CONTEXTUAL_ACCESS_BASELINES
from synthworld.contextual_access.common import stable_contextual_fact_key
from synthworld.contextual_access.metrics import (
    evaluate_contextual_access_prediction,
    perfect_contextual_access_prediction,
)
from synthworld.contextual_access.models import (
    BusinessJustificationContextV1,
    BusinessJustificationKind,
    CaseAssignmentContextV1,
    CaseAssignmentState,
    ContextualAccessRequestV1,
    ContextualCaseKind,
    ContextualDecisionTruthV1,
    ContextualFactKind,
    ContextualFactV1,
    ContextualObjectCountsV1,
    ContextualObjectKind,
    ContextualPolicyV1,
    ContextualPredicateTruth,
    ContextualPredicateV1,
    ContextualRuleComposition,
    ContextualRuleEffect,
    ContextualRuleV1,
    DevicePosture,
    DevicePostureContextV1,
    DevicePostureIsV1,
    HasActiveCaseAssignmentV1,
    HasValidBusinessJustificationV1,
    IsOnCallV1,
    OnCallContextV1,
    OnCallState,
    RiskAtMostV1,
    RiskLevel,
    RiskSignalContextV1,
)
from synthworld.contextual_access.policy import evaluate_contextual_request
from synthworld.contextual_access.reference import (
    REFERENCE_CONTEXTUAL_UNIVERSE_SHA256,
    generate_contextual_access_smoke,
    reference_contextual_access,
)
from synthworld.contextual_access.shared_signals import (
    contextual_shared_signals_mapping_profile_v1,
    project_contextual_shared_signals,
)
from synthworld.enterprise.authorization.reference import (
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.rbac.common import AuthorizationDecision


def test_reference_smoke_is_deterministic_bounded_and_does_not_resize_access() -> None:
    first = reference_contextual_access()
    second = reference_contextual_access()
    authorization = reference_enterprise_authorization_inputs()
    universe = authorization.rbac.universe_result.public_universe
    assert canonical_json_bytes(first.public) == canonical_json_bytes(second.public)
    assert canonical_json_bytes(first.evaluator) == canonical_json_bytes(
        second.evaluator
    )
    assert first.public.universe == universe
    assert first.public.universe.access_atoms == universe.access_atoms
    assert (
        synthetic_digest(canonical_json_bytes(first.public.universe)).value
        == REFERENCE_CONTEXTUAL_UNIVERSE_SHA256
    )
    assert len(first.public.registry.objects) == 16
    assert len(first.public.initial_facts) == 11
    assert len(first.public.events) == 7
    assert len(first.public.delivery_attempts) == 8
    assert len(first.public.requests) == len(ContextualCaseKind) == 10
    assert len(first.evaluator.truth.checkpoints) == len(first.public.events) + 1


def test_contextual_smoke_has_every_case_and_expected_transition_outcomes() -> None:
    reference = reference_contextual_access()
    labels = {
        item.request_id: item.kind for item in reference.evaluator.truth.case_labels
    }
    cases = {labels[item.request_id]: item for item in reference.evaluator.truth.cases}
    assert set(cases) == set(ContextualCaseKind)
    assert cases[ContextualCaseKind.STATIC_ALLOW].canonical.decision is (
        AuthorizationDecision.ALLOW
    )
    assert cases[ContextualCaseKind.STATIC_DENY].canonical.deny_override_conflict
    assert cases[ContextualCaseKind.STATIC_DENY].canonical.decision is (
        AuthorizationDecision.DENY
    )
    for kind in (
        ContextualCaseKind.ASSIGNMENT_REMOVED,
        ContextualCaseKind.ON_CALL_EXPIRED,
        ContextualCaseKind.DEVICE_DEGRADED,
        ContextualCaseKind.RISK_ELEVATED,
        ContextualCaseKind.JUSTIFICATION_EXPIRED,
        ContextualCaseKind.DELAYED_DELIVERY,
        ContextualCaseKind.DUPLICATE_DELIVERY,
    ):
        assert cases[kind].canonical.decision is AuthorizationDecision.DENY
    assert cases[ContextualCaseKind.OUT_OF_ORDER_DELIVERY].canonical.decision is (
        AuthorizationDecision.ALLOW
    )
    stale = {kind for kind, case in cases.items() if case.stale_context}
    assert stale == {ContextualCaseKind.DELAYED_DELIVERY}
    assert cases[ContextualCaseKind.DELAYED_DELIVERY].presented_feed.decision is (
        AuthorizationDecision.ALLOW
    )


def test_registry_kind_growth_does_not_remap_other_kinds_or_access_atoms() -> None:
    base = reference_contextual_access()
    counts = base.config.object_counts.model_copy(
        update={"approval_evidence": base.config.object_counts.approval_evidence + 1}
    )
    expanded = generate_contextual_access_smoke(
        universe=base.public.universe,
        config=base.config.model_copy(update={"object_counts": counts}),
    )
    base_ids = {
        item.kind: tuple(
            candidate.id
            for candidate in base.public.registry.objects
            if candidate.kind is item.kind
        )
        for item in base.public.registry.objects
    }
    expanded_ids = {
        item.kind: tuple(
            candidate.id
            for candidate in expanded.public.registry.objects
            if candidate.kind is item.kind
        )
        for item in expanded.public.registry.objects
    }
    for kind in ContextualObjectKind:
        if kind is not ContextualObjectKind.APPROVAL_EVIDENCE:
            assert expanded_ids[kind] == base_ids[kind]
    assert set(base_ids[ContextualObjectKind.APPROVAL_EVIDENCE]) < set(
        expanded_ids[ContextualObjectKind.APPROVAL_EVIDENCE]
    )
    assert expanded.public.universe.access_atoms == base.public.universe.access_atoms


def test_seed_changes_overlay_identity_but_not_fixed_enterprise_breadth() -> None:
    first = reference_contextual_access(seed=1)
    second = reference_contextual_access(seed=2)
    assert first.public.registry != second.public.registry
    assert first.public.universe == second.public.universe
    assert len(first.public.requests) == len(second.public.requests) == 10
    assert first.public.universe.access_atoms == second.public.universe.access_atoms


def test_perfect_metrics_and_each_shortcut_baseline_are_discriminating() -> None:
    reference = reference_contextual_access()
    perfect = perfect_contextual_access_prediction(
        public=reference.public,
        evaluator=reference.evaluator,
    )
    metrics = evaluate_contextual_access_prediction(
        public=reference.public,
        evaluator=reference.evaluator,
        prediction=perfect,
    )
    assert metrics.metrics
    assert all(item.value == 1.0 for item in metrics.metrics)
    expected_failure = {
        "Ignore contextual predicates": "predicate_outcome_accuracy",
        "Trust presented feed": "stale_context_decision_accuracy",
        "Initial snapshot only": "transition_decision_accuracy",
        "Drop delayed events": "canonical_event_application_exact_match",
    }
    for name, baseline in CONTEXTUAL_ACCESS_BASELINES:
        report = evaluate_contextual_access_prediction(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=baseline(public=reference.public, evaluator=reference.evaluator),
        )
        values = {item.name: item.value for item in report.metrics}
        assert values[expected_failure[name]] != 1.0


def test_reference_predicate_outcomes_cover_closed_and_open_world_distinctions() -> (
    None
):
    reference = reference_contextual_access()
    predicate_types = {
        predicate.predicate_id: predicate.predicate_type
        for policy in reference.public.policies
        for rule in policy.rules
        for predicate in rule.predicates
    }
    outcomes: dict[str, set[ContextualPredicateTruth]] = defaultdict(set)
    for case in reference.evaluator.truth.cases:
        for item in case.canonical.predicate_outcomes:
            outcomes[predicate_types[item.predicate_id]].add(item.outcome)
    assert outcomes["has_active_case_assignment"] == {
        ContextualPredicateTruth.TRUE,
        ContextualPredicateTruth.FALSE,
    }
    assert outcomes["is_on_call"] == {
        ContextualPredicateTruth.TRUE,
        ContextualPredicateTruth.FALSE,
    }
    assert outcomes["risk_at_most"] == set(ContextualPredicateTruth)


def test_every_predicate_and_three_valued_composition_semantics() -> None:
    request, facts = _policy_fixture()
    predicates: dict[str, ContextualPredicateV1] = {
        "assignment": HasActiveCaseAssignmentV1(predicate_id="p-assignment"),
        "on_call": IsOnCallV1(
            predicate_id="p-on-call",
            duty_scope_id="duty-1",
        ),
        "device": DevicePostureIsV1(
            predicate_id="p-device",
            required_posture=DevicePosture.TRUSTED,
        ),
        "risk": RiskAtMostV1(
            predicate_id="p-risk",
            signal_source_id="risk-1",
            maximum_level=RiskLevel.MEDIUM,
        ),
        "justification": HasValidBusinessJustificationV1(
            predicate_id="p-justification",
            justification_kind=BusinessJustificationKind.EMERGENCY_ACCESS,
        ),
    }
    expected = {
        "assignment": ContextualPredicateTruth.TRUE,
        "on_call": ContextualPredicateTruth.TRUE,
        "device": ContextualPredicateTruth.TRUE,
        "risk": ContextualPredicateTruth.TRUE,
        "justification": ContextualPredicateTruth.TRUE,
    }
    for name, predicate in predicates.items():
        result = _single_rule(request, facts, (predicate,))
        assert result.predicate_outcomes[0].outcome is expected[name]
        assert result.decision is AuthorizationDecision.ALLOW

    unknown_device = _replace_fact(
        facts,
        DevicePostureContextV1,
        lambda item: item.model_copy(update={"posture": DevicePosture.UNKNOWN}),
    )
    high_risk = _replace_fact(
        facts,
        RiskSignalContextV1,
        lambda item: item.model_copy(update={"risk_level": RiskLevel.HIGH}),
    )
    off_call = _replace_fact(
        facts,
        OnCallContextV1,
        lambda item: item.model_copy(update={"duty_state": OnCallState.OFF_CALL}),
    )
    assert (
        _single_rule(request, unknown_device, (predicates["device"],))
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.UNKNOWN
    )
    assert (
        _single_rule(request, high_risk, (predicates["risk"],)).rule_outcomes[0].outcome
        is ContextualPredicateTruth.FALSE
    )
    assert (
        _single_rule(request, off_call, (predicates["on_call"],))
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.FALSE
    )
    absent_observation = tuple(
        item
        for item in facts
        if not isinstance(item, (DevicePostureContextV1, RiskSignalContextV1))
    )
    assert (
        _single_rule(request, absent_observation, (predicates["device"],))
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.UNKNOWN
    )
    no_device_request = request.model_copy(update={"device_id": None})
    assert (
        _single_rule(no_device_request, facts, (predicates["device"],))
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.UNKNOWN
    )

    false_assignment = HasActiveCaseAssignmentV1(predicate_id="p-false-assignment")
    false_request = request.model_copy(
        update={"subject_id": "subject-other", "asset_id": "asset-other"}
    )
    unknown = DevicePostureIsV1(
        predicate_id="p-unknown",
        required_posture=DevicePosture.TRUSTED,
    )
    assert (
        _single_rule(
            false_request,
            (),
            (false_assignment, unknown),
            composition=ContextualRuleComposition.ALL,
        )
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.FALSE
    )
    assert (
        _single_rule(
            false_request,
            (),
            (false_assignment, unknown),
            composition=ContextualRuleComposition.ANY,
        )
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.UNKNOWN
    )
    assert (
        _single_rule(
            request,
            facts,
            (predicates["assignment"], unknown),
            composition=ContextualRuleComposition.ALL,
        )
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.TRUE
    )
    facts_without_device = tuple(
        item for item in facts if not isinstance(item, DevicePostureContextV1)
    )
    assert (
        _single_rule(
            request,
            facts_without_device,
            (predicates["assignment"], unknown),
            composition=ContextualRuleComposition.ALL,
        )
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.UNKNOWN
    )
    assert (
        _single_rule(
            request,
            facts,
            (predicates["assignment"], unknown),
            composition=ContextualRuleComposition.ANY,
        )
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.TRUE
    )
    assert (
        _single_rule(
            false_request,
            (),
            (false_assignment, predicates["on_call"]),
            composition=ContextualRuleComposition.ANY,
        )
        .rule_outcomes[0]
        .outcome
        is ContextualPredicateTruth.FALSE
    )


def test_policy_scope_default_deny_and_deny_overrides_are_explicit() -> None:
    request, facts = _policy_fixture()
    allow = HasActiveCaseAssignmentV1(predicate_id="allow")
    deny = IsOnCallV1(predicate_id="deny", duty_scope_id="duty-1")
    policy = ContextualPolicyV1(
        policy_id="policy-conflict",
        policy_version_id="policy-conflict-v1",
        target_handles=(request.asset_id,),
        actions=(request.action,),
        rules=(
            ContextualRuleV1(
                rule_id="rule-allow",
                effect=ContextualRuleEffect.ALLOW,
                composition=ContextualRuleComposition.ALL,
                predicates=(allow,),
            ),
            ContextualRuleV1(
                rule_id="rule-deny",
                effect=ContextualRuleEffect.DENY,
                composition=ContextualRuleComposition.ALL,
                predicates=(deny,),
            ),
        ),
    )
    result = evaluate_contextual_request(
        active_facts=facts,
        policies=(policy,),
        request=request,
    )
    assert result.decision is AuthorizationDecision.DENY
    assert result.deny_override_conflict
    outside = request.model_copy(update={"action": "write"})
    default = evaluate_contextual_request(
        active_facts=facts,
        policies=(policy,),
        request=outside,
    )
    assert default.decision is AuthorizationDecision.DENY
    assert not default.applicable_policy_ids
    assert not default.rule_outcomes


def test_shared_signals_projection_is_custom_one_clock_and_not_caep_mislabeled() -> (
    None
):
    reference = reference_contextual_access()
    profile = contextual_shared_signals_mapping_profile_v1()
    projection = project_contextual_shared_signals(reference.public, profile=profile)
    assert len(profile.mappings) == len(ContextualFactKind)
    assert len(projection.events) == len(reference.public.events)
    assert projection.selected_temporal_base == "synthworld-temporal-1.2.0"
    assert all(item.standardized_caep_event_type is None for item in projection.events)
    assert all(
        item.custom_event_type.startswith("urn:synthworld:event:contextual-")
        for item in projection.events
    )
    assert all(
        item.projected_event_tick == item.effective_tick for item in projection.events
    )
    assert tuple(item.event_index for item in projection.events) == tuple(
        range(len(projection.events))
    )
    assert project_contextual_shared_signals(reference.public) == projection


def test_reference_config_rejects_partial_or_rescaled_case_vocabularies() -> None:
    reference = reference_contextual_access()
    invalid = (
        reference.config.model_copy(
            update={"enabled_case_kinds": (ContextualCaseKind.STATIC_ALLOW,)}
        ),
        reference.config.model_copy(update={"cases_per_kind": 2}),
        reference.config.model_copy(
            update={
                "object_counts": ContextualObjectCountsV1(
                    work_items=2,
                    duty_scopes=2,
                    devices=6,
                    signal_sources=2,
                    approval_evidence=3,
                )
            }
        ),
    )
    for config in invalid:
        with pytest.raises(ValueError, match="requires every kind once"):
            generate_contextual_access_smoke(
                universe=reference.public.universe,
                config=config,
            )


def _policy_fixture() -> tuple[
    ContextualAccessRequestV1,
    tuple[ContextualFactV1, ...],
]:
    request = ContextualAccessRequestV1(
        request_id="request",
        request_index=0,
        request_tick=1,
        subject_id="subject",
        asset_id="asset",
        action="read",
        access_atom_id="atom",
        device_id="device-1",
    )
    facts = (
        CaseAssignmentContextV1(
            fact_id="fact-assignment",
            fact_key=stable_contextual_fact_key(
                "case_assignment", "subject", "work", "asset"
            ),
            revision=0,
            subject_id="subject",
            work_item_id="work",
            asset_id="asset",
            assignment_state=CaseAssignmentState.ASSIGNED,
            valid_from_tick=0,
        ),
        OnCallContextV1(
            fact_id="fact-on-call",
            fact_key=stable_contextual_fact_key("on_call", "subject", "duty-1"),
            revision=0,
            subject_id="subject",
            duty_scope_id="duty-1",
            duty_state=OnCallState.ON_CALL,
            valid_from_tick=0,
        ),
        DevicePostureContextV1(
            fact_id="fact-device",
            fact_key=stable_contextual_fact_key(
                "device_posture", "subject", "device-1"
            ),
            revision=0,
            subject_id="subject",
            device_id="device-1",
            posture=DevicePosture.TRUSTED,
            observed_at_tick=0,
        ),
        RiskSignalContextV1(
            fact_id="fact-risk",
            fact_key=stable_contextual_fact_key("risk_signal", "subject", "risk-1"),
            revision=0,
            subject_id="subject",
            signal_source_id="risk-1",
            risk_level=RiskLevel.LOW,
            effective_from_tick=0,
        ),
        BusinessJustificationContextV1(
            fact_id="fact-justification",
            fact_key=stable_contextual_fact_key(
                "business_justification",
                "subject",
                "asset",
                "read",
                "emergency_access",
                "approval",
            ),
            revision=0,
            subject_id="subject",
            asset_id="asset",
            action="read",
            justification_kind=BusinessJustificationKind.EMERGENCY_ACCESS,
            approval_evidence_id="approval",
            valid_from_tick=0,
        ),
    )
    return request, facts


def _single_rule(
    request: ContextualAccessRequestV1,
    facts: tuple[ContextualFactV1, ...],
    predicates: tuple[ContextualPredicateV1, ...],
    *,
    composition: ContextualRuleComposition = ContextualRuleComposition.ALL,
) -> ContextualDecisionTruthV1:
    policy = ContextualPolicyV1(
        policy_id="policy",
        policy_version_id="policy-v1",
        target_handles=(request.asset_id,),
        actions=(request.action,),
        rules=(
            ContextualRuleV1(
                rule_id="rule",
                effect=ContextualRuleEffect.ALLOW,
                composition=composition,
                predicates=predicates,
            ),
        ),
    )
    return evaluate_contextual_request(
        active_facts=facts,
        policies=(policy,),
        request=request,
    )


def _replace_fact(
    facts: tuple[ContextualFactV1, ...],
    fact_type: type[ContextualFactV1],
    transform: Callable[[ContextualFactV1], ContextualFactV1],
) -> tuple[ContextualFactV1, ...]:
    return tuple(
        transform(item) if isinstance(item, fact_type) else item for item in facts
    )
