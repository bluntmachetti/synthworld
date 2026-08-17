"""Adversarial enterprise authorization contracts, baselines, and isolation."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

import synthworld.enterprise.authorization.adversarial.reference as reference_module
from synthworld.enterprise.authorization.adversarial import (
    AdversarialAuthorizationBaseline,
    AdversarialAuthorizationMechanism,
    AdversarialCohortSummaryV1,
    AdversarialCounterfactualPairTruthV1,
    AdversarialTenantRuleV1,
    EnterpriseAdversarialAuthorizationEvaluatorV1,
    EnterpriseAdversarialAuthorizationMetricsV1,
    EnterpriseAdversarialAuthorizationPolicyV1,
    EnterpriseAdversarialAuthorizationPredictionV1,
    EnterpriseAdversarialAuthorizationPublicV1,
    ReferenceEnterpriseAdversarialAuthorizationV1,
    TenantComparisonOperator,
    binding_blind_authorization_baseline,
    clearance_blind_authorization_baseline,
    evaluate_adversarial_attempt,
    evaluate_enterprise_adversarial_authorization,
    identifier_memorization_baseline,
    perfect_enterprise_adversarial_authorization_prediction,
    rbac_only_authorization_baseline,
    reference_enterprise_adversarial_authorization,
    resolve_adversarial_credential,
    scope_blind_authorization_baseline,
    tenant_blind_authorization_baseline,
    time_blind_authorization_baseline,
    validate_adversarial_authorization_artifacts,
)
from synthworld.enterprise.authorization.adversarial.metrics import (
    _attempt_accuracy,
    _pair_accuracy,
)
from synthworld.enterprise.authorization_common import RuleEffect
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    MetricEmptyBehaviour,
)
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1


def _reference() -> ReferenceEnterpriseAdversarialAuthorizationV1:
    return reference_enterprise_adversarial_authorization()


def _report(
    prediction: EnterpriseAdversarialAuthorizationPredictionV1,
) -> EnterpriseAdversarialAuthorizationMetricsV1:
    reference = _reference()
    return evaluate_enterprise_adversarial_authorization(
        public=reference.public,
        evaluator=reference.evaluator,
        prediction=prediction,
    )


def _metrics(
    report: EnterpriseAdversarialAuthorizationMetricsV1,
) -> dict[str, EnterpriseAuthorizationMetricV1]:
    return {f"{item.family}.{item.name}": item for item in report.metrics}


def _model_data(model: BaseModel) -> dict[str, Any]:
    return deepcopy(model.model_dump(mode="json"))


def _public_with_mutation(
    mutate: Callable[[dict[str, Any]], None],
) -> EnterpriseAdversarialAuthorizationPublicV1:
    data = _model_data(_reference().public)
    mutate(data)
    return EnterpriseAdversarialAuthorizationPublicV1.model_validate(data)


def test_reference_is_deterministic_opaque_and_separated() -> None:
    first = reference_enterprise_adversarial_authorization(seed=7)
    replay = reference_enterprise_adversarial_authorization(seed=7)
    changed = reference_enterprise_adversarial_authorization(seed=8)

    assert canonical_json_bytes(first.public) == canonical_json_bytes(replay.public)
    assert canonical_json_bytes(first.evaluator) == canonical_json_bytes(
        replay.evaluator
    )
    assert first.public != changed.public
    assert first.evaluator.public_digest == synthetic_digest(
        canonical_json_bytes(first.public)
    )
    assert len(first.public.attempts) == 14
    assert len(first.evaluator.pairs) == 7
    assert all(item.expected_transition for item in first.evaluator.pairs)
    assert {item.category.value for item in first.evaluator.cases} == {"single_factor"}
    assert all(UUID(item.attempt_id).version == 5 for item in first.public.attempts)
    assert not any(
        mechanism.value in item.attempt_id
        for mechanism in AdversarialAuthorizationMechanism
        for item in first.public.attempts
    )

    public_keys = _all_keys(first.public.model_dump(mode="json"))
    assert {
        "expected_decision",
        "mechanism",
        "pair_id",
        "canonical_bindings",
        "binding_status",
        "identifier_probe",
    }.isdisjoint(public_keys)
    assert first.public.grants
    assert first.public.attempts
    assert first.public.policy.tenant_rules[0].operator is (
        TenantComparisonOperator.NOT_EQUALS
    )
    assert any(
        _attempt_is_cross_tenant(first.public, item.attempt_id)
        for item in first.public.attempts
    )


def test_perfect_prediction_reports_independent_discriminating_denominators() -> None:
    reference = _reference()
    prediction = perfect_enterprise_adversarial_authorization_prediction(
        reference.evaluator
    )
    report = _report(prediction)
    metrics = _metrics(report)

    assert all(item.value == 1.0 for item in report.metrics)
    assert {
        item.mechanism.value: (
            item.total_scenarios,
            item.discriminating_denominator,
        )
        for item in report.cohorts
    } == {
        "binding": (4, 2),
        "clearance": (2, 1),
        "composition": (2, 1),
        "scope": (2, 1),
        "tenant": (2, 1),
        "time": (2, 1),
    }
    assert metrics["binding.binding_status_accuracy"].denominator == 4
    assert metrics["binding.resolved_principal_accuracy"].denominator == 4
    assert metrics["temporal.expected_transition_accuracy"].denominator == 1
    assert metrics["decision.final_decision_accuracy"].denominator == 14
    assert "aggregate" not in EnterpriseAdversarialAuthorizationMetricsV1.model_fields
    assert report.public_digest == reference.evaluator.public_digest
    assert report.evaluator_digest == synthetic_digest(
        canonical_json_bytes(reference.evaluator)
    )
    assert report.prediction_digest == synthetic_digest(
        canonical_json_bytes(prediction)
    )


@pytest.mark.parametrize(
    ("baseline", "metric_name"),
    (
        (tenant_blind_authorization_baseline, "mechanism.tenant_decision_accuracy"),
        (scope_blind_authorization_baseline, "mechanism.scope_decision_accuracy"),
        (
            binding_blind_authorization_baseline,
            "mechanism.binding_decision_accuracy",
        ),
        (time_blind_authorization_baseline, "mechanism.time_decision_accuracy"),
        (
            clearance_blind_authorization_baseline,
            "mechanism.clearance_decision_accuracy",
        ),
        (rbac_only_authorization_baseline, "mechanism.composition_decision_accuracy"),
        (
            identifier_memorization_baseline,
            "robustness.identifier_independent_decision_accuracy",
        ),
    ),
)
def test_required_weak_baselines_fail_independent_metrics(
    baseline: AdversarialAuthorizationBaseline, metric_name: str
) -> None:
    reference = _reference()
    report = evaluate_enterprise_adversarial_authorization(
        public=reference.public,
        evaluator=reference.evaluator,
        prediction=baseline(reference.public),
    )
    value = _metrics(report)[metric_name].value
    assert value is not None and value < 1.0


def test_binding_blind_baseline_cannot_claim_perfect_binding_pass() -> None:
    report = _report(binding_blind_authorization_baseline(_reference().public))
    metrics = _metrics(report)
    assert metrics["binding.binding_status_accuracy"].value == 0.5
    assert metrics["binding.resolved_principal_accuracy"].value == 0.5
    assert metrics["mechanism.binding_decision_accuracy"].value == 0.0


def test_time_blind_baseline_fails_explicit_transition_metric() -> None:
    report = _report(time_blind_authorization_baseline(_reference().public))
    assert _metrics(report)["temporal.expected_transition_accuracy"].value == 0.0


def test_public_models_reject_invalid_structure_but_allow_unauthorized_attempts() -> (
    None
):
    reference = _reference()
    cross_tenant = next(
        item
        for item in reference.public.attempts
        if _attempt_is_cross_tenant(reference.public, item.attempt_id)
    )
    assert cross_tenant in reference.public.attempts

    grant = _model_data(reference.public.grants[0])
    grant["valid_until_tick"] = grant["valid_from_tick"]
    with pytest.raises(
        ValidationError, match="adversarial_grant_interval_not_positive"
    ):
        type(reference.public.grants[0]).model_validate(grant)

    grant = _model_data(reference.public.grants[0])
    grant["allowed_scopes"] = [grant["allowed_scopes"][0]] * 2
    with pytest.raises(ValidationError, match="duplicate_adversarial_grant_scope"):
        type(reference.public.grants[0]).model_validate(grant)

    policy = _model_data(reference.public.policy)
    policy["tenant_rules"] = policy["tenant_rules"] * 2
    with pytest.raises(ValidationError, match="duplicate_adversarial_tenant_rule_id"):
        EnterpriseAdversarialAuthorizationPolicyV1.model_validate(policy)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda data: data["principals"][1].update(
                directory_alias=data["principals"][0]["directory_alias"]
            ),
            "duplicate_adversarial_principal_alias",
        ),
        (
            lambda data: data["credentials"][0].update(
                issuer_subject_alias="missing@example.invalid"
            ),
            "unknown_adversarial_credential_alias",
        ),
        (
            lambda data: data["grants"][0].update(principal_id="missing"),
            "unknown_adversarial_grant_reference",
        ),
        (
            lambda data: data["attempts"][0].update(resource_id="missing"),
            "unknown_adversarial_attempt_reference",
        ),
    ),
)
def test_public_cross_references_fail_closed(
    mutation: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _public_with_mutation(mutation)


def test_duplicate_public_and_prediction_ids_are_rejected() -> None:
    reference = _reference()
    public_data = _model_data(reference.public)
    public_data["principals"] = [public_data["principals"][0]] * 2
    with pytest.raises(ValidationError, match="duplicate_adversarial_principals_id"):
        EnterpriseAdversarialAuthorizationPublicV1.model_validate(public_data)

    prediction = perfect_enterprise_adversarial_authorization_prediction(
        reference.evaluator
    )
    with pytest.raises(
        ValidationError, match="duplicate_adversarial_prediction_attempt_id"
    ):
        EnterpriseAdversarialAuthorizationPredictionV1(
            public_digest=prediction.public_digest,
            attempts=(prediction.attempts[0], prediction.attempts[0]),
        )


def test_artifact_cross_boundary_validation_rejects_every_binding_failure() -> None:
    reference = _reference()
    public = reference.public
    evaluator = reference.evaluator

    with pytest.raises(
        ValueError, match="adversarial_evaluator_public_digest_mismatch"
    ):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(
                update={
                    "public_digest": synthetic_digest(b"different\n"),
                }
            ),
        )
    with pytest.raises(ValueError, match="adversarial_binding_inventory_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(
                update={"canonical_bindings": evaluator.canonical_bindings[:-1]}
            ),
        )
    bad_binding = evaluator.canonical_bindings[0].model_copy(
        update={"principal_id": "missing"}
    )
    with pytest.raises(ValueError, match="adversarial_binding_principal_unknown"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(
                update={
                    "canonical_bindings": (
                        bad_binding,
                        *evaluator.canonical_bindings[1:],
                    )
                }
            ),
        )
    with pytest.raises(ValueError, match="adversarial_case_inventory_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(update={"cases": evaluator.cases[:-1]}),
        )
    bad_case = evaluator.cases[0].model_copy(
        update={"resolved_principal_id": "missing"}
    )
    with pytest.raises(ValueError, match="adversarial_case_binding_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(update={"cases": (bad_case, *evaluator.cases[1:])}),
        )
    bad_case = evaluator.cases[0].model_copy(update={"pair_id": "missing"})
    with pytest.raises(ValueError, match="adversarial_case_pair_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(update={"cases": (bad_case, *evaluator.cases[1:])}),
        )
    binding_cases = tuple(
        item
        for item in evaluator.cases
        if item.mechanism is AdversarialAuthorizationMechanism.BINDING
    )
    first_binding = binding_cases[0]
    other_binding_pair = next(
        item.pair_id for item in binding_cases if item.pair_id != first_binding.pair_id
    )
    misplaced_case = first_binding.model_copy(update={"pair_id": other_binding_pair})
    cases = tuple(
        misplaced_case if item.attempt_id == misplaced_case.attempt_id else item
        for item in evaluator.cases
    )
    with pytest.raises(ValueError, match="adversarial_case_not_in_declared_pair"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(update={"cases": cases}),
        )
    bad_pair = evaluator.pairs[0].model_copy(
        update={"to_attempt_id": evaluator.pairs[1].to_attempt_id}
    )
    with pytest.raises(ValueError, match="adversarial_pair_attempt_inventory_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(update={"pairs": (bad_pair, *evaluator.pairs[1:])}),
        )
    extra_pair = evaluator.pairs[0].model_copy(update={"pair_id": "extra-pair"})
    with pytest.raises(ValueError, match="adversarial_pair_attempt_inventory_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(update={"pairs": (*evaluator.pairs, extra_pair)}),
        )


def test_artifact_validation_recomputes_every_answer_key_field() -> None:
    reference = _reference()
    public = reference.public
    evaluator = reference.evaluator

    def replace_case(
        **updates: object,
    ) -> EnterpriseAdversarialAuthorizationEvaluatorV1:
        changed = evaluator.cases[0].model_copy(update=updates)
        return evaluator.model_copy(update={"cases": (changed, *evaluator.cases[1:])})

    with pytest.raises(ValueError, match="adversarial_case_binding_status_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            replace_case(binding_status="mismatch"),
        )
    with pytest.raises(ValueError, match="adversarial_case_expected_decision_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            replace_case(
                expected_decision=_opposite(evaluator.cases[0].expected_decision)
            ),
        )
    with pytest.raises(ValueError, match="adversarial_case_ignored_decision_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            replace_case(
                mechanism_ignored_decision=_opposite(
                    evaluator.cases[0].mechanism_ignored_decision
                )
            ),
        )
    probe_index = next(
        index for index, item in enumerate(evaluator.cases) if item.identifier_probe
    )
    changed_probe = evaluator.cases[probe_index].model_copy(
        update={"identifier_probe": False}
    )
    changed_probe_cases = (
        *evaluator.cases[:probe_index],
        changed_probe,
        *evaluator.cases[probe_index + 1 :],
    )
    with pytest.raises(ValueError, match="adversarial_case_identifier_probe_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(update={"cases": changed_probe_cases}),
        )
    changed_pair = evaluator.pairs[0].model_copy(
        update={"expected_transition": not evaluator.pairs[0].expected_transition}
    )
    with pytest.raises(ValueError, match="adversarial_pair_transition_mismatch"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(
                update={"pairs": (changed_pair, *evaluator.pairs[1:])}
            ),
        )
    binding_pairs = tuple(
        item
        for item in evaluator.pairs
        if item.mechanism is AdversarialAuthorizationMechanism.BINDING
    )
    binding_cases = tuple(
        item
        for item in evaluator.cases
        if item.mechanism is AdversarialAuthorizationMechanism.BINDING
    )
    same_verdict_groups = tuple(
        tuple(item for item in binding_cases if item.expected_decision is decision)
        for decision in (AuthorizationDecision.ALLOW, AuthorizationDecision.DENY)
    )
    same_verdict_pairs = tuple(
        pair.model_copy(
            update={
                "from_attempt_id": endpoints[0].attempt_id,
                "to_attempt_id": endpoints[1].attempt_id,
                "expected_transition": False,
            }
        )
        for pair, endpoints in zip(
            binding_pairs,
            same_verdict_groups,
            strict=True,
        )
    )
    same_verdict_pair_by_attempt = {
        attempt_id: pair
        for pair in same_verdict_pairs
        for attempt_id in (pair.from_attempt_id, pair.to_attempt_id)
    }
    same_verdict_cases = tuple(
        item.model_copy(
            update={
                "pair_id": same_verdict_pair_by_attempt[item.attempt_id].pair_id,
                "identifier_probe": (
                    item.attempt_id
                    == same_verdict_pair_by_attempt[item.attempt_id].to_attempt_id
                ),
            }
        )
        if item.attempt_id in same_verdict_pair_by_attempt
        else item
        for item in evaluator.cases
    )
    changed_same_verdict_pairs = tuple(
        next(
            (
                changed
                for changed in same_verdict_pairs
                if changed.pair_id == item.pair_id
            ),
            item,
        )
        for item in evaluator.pairs
    )
    with pytest.raises(ValueError, match="adversarial_pair_transition_required"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(
                update={
                    "cases": same_verdict_cases,
                    "pairs": changed_same_verdict_pairs,
                }
            ),
        )
    nondiscriminating = tuple(
        item
        for item in binding_cases
        if item.expected_decision is item.mechanism_ignored_decision
    )
    discriminating = tuple(
        item
        for item in binding_cases
        if item.expected_decision is not item.mechanism_ignored_decision
    )
    remapped_pairs = tuple(
        pair.model_copy(
            update={
                "from_attempt_id": endpoints[0].attempt_id,
                "to_attempt_id": endpoints[1].attempt_id,
            }
        )
        for pair, endpoints in zip(
            binding_pairs,
            (nondiscriminating, discriminating),
            strict=True,
        )
    )
    remapped_pair_by_attempt = {
        attempt_id: pair
        for pair in remapped_pairs
        for attempt_id in (pair.from_attempt_id, pair.to_attempt_id)
    }
    changed_cases = tuple(
        item.model_copy(
            update={
                "pair_id": remapped_pair_by_attempt[item.attempt_id].pair_id,
                "identifier_probe": (
                    item.attempt_id
                    == remapped_pair_by_attempt[item.attempt_id].to_attempt_id
                ),
            }
        )
        if item.attempt_id in remapped_pair_by_attempt
        else item
        for item in evaluator.cases
    )
    changed_pairs = tuple(
        next(
            (changed for changed in remapped_pairs if changed.pair_id == item.pair_id),
            item,
        )
        for item in evaluator.pairs
    )
    with pytest.raises(ValueError, match="adversarial_pair_not_discriminating"):
        validate_adversarial_authorization_artifacts(
            public,
            evaluator.model_copy(
                update={"cases": changed_cases, "pairs": changed_pairs}
            ),
        )


def test_evaluator_and_metric_contract_guards_are_discriminating() -> None:
    reference = _reference()
    evaluator_data = _model_data(reference.evaluator)
    evaluator_data["cases"] = [evaluator_data["cases"][0]] * 2
    with pytest.raises(
        ValidationError, match="duplicate_adversarial_evaluator_cases_id"
    ):
        EnterpriseAdversarialAuthorizationEvaluatorV1.model_validate(evaluator_data)

    pair = _model_data(reference.evaluator.pairs[0])
    pair["to_attempt_id"] = pair["from_attempt_id"]
    with pytest.raises(ValidationError, match="adversarial_pair_attempts_must_differ"):
        AdversarialCounterfactualPairTruthV1.model_validate(pair)

    with pytest.raises(
        ValidationError, match="adversarial_denominator_exceeds_cohort_total"
    ):
        AdversarialCohortSummaryV1(
            mechanism=AdversarialAuthorizationMechanism.TENANT,
            total_scenarios=1,
            discriminating_denominator=2,
        )

    report = _report(
        perfect_enterprise_adversarial_authorization_prediction(reference.evaluator)
    )
    report_data = _model_data(report)
    report_data["cohorts"] = [report_data["cohorts"][0]] * 2
    with pytest.raises(ValidationError, match="duplicate_adversarial_metric_cohort"):
        EnterpriseAdversarialAuthorizationMetricsV1.model_validate(report_data)
    report_data = _model_data(report)
    report_data["metrics"] = [report_data["metrics"][0]] * 2
    with pytest.raises(ValidationError, match="duplicate_adversarial_metric_name"):
        EnterpriseAdversarialAuthorizationMetricsV1.model_validate(report_data)


def test_prediction_binding_and_inventory_are_exact() -> None:
    reference = _reference()
    prediction = perfect_enterprise_adversarial_authorization_prediction(
        reference.evaluator
    )
    with pytest.raises(
        ValueError, match="adversarial_prediction_public_digest_mismatch"
    ):
        evaluate_enterprise_adversarial_authorization(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=prediction.model_copy(
                update={"public_digest": synthetic_digest(b"different\n")}
            ),
        )
    with pytest.raises(
        ValueError, match="adversarial_prediction_attempt_inventory_mismatch"
    ):
        evaluate_enterprise_adversarial_authorization(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=prediction.model_copy(
                update={"attempts": prediction.attempts[:-1]}
            ),
        )


def test_public_evidence_resolution_handles_missing_and_conflicting_claims() -> None:
    reference = _reference()
    assert resolve_adversarial_credential(reference.public, "missing") is None

    def conflict(data: dict[str, Any]) -> None:
        issuer = data["credentials"][0]["issuer_subject_alias"]
        different = next(
            item["directory_alias"]
            for item in data["principals"]
            if item["directory_alias"] != issuer
        )
        data["credentials"][0]["device_owner_alias"] = different

    public = _public_with_mutation(conflict)
    credential_id = public.credentials[0].credential_id
    assert resolve_adversarial_credential(public, credential_id) is None
    prediction = tenant_blind_authorization_baseline(public)
    row = next(
        item
        for item in prediction.attempts
        if next(
            attempt
            for attempt in public.attempts
            if attempt.attempt_id == item.attempt_id
        ).credential_id
        == credential_id
    )
    assert row.resolved_principal_id is None
    assert row.binding_status.value == "missing"


def test_bounded_tenant_equality_allow_rule_and_default_deny() -> None:
    reference = _reference()
    policy = EnterpriseAdversarialAuthorizationPolicyV1(
        default_tenant_decision=AuthorizationDecision.DENY,
        tenant_rules=(
            AdversarialTenantRuleV1(
                rule_id="allow-same-tenant",
                operator=TenantComparisonOperator.EQUALS,
                effect=RuleEffect.ALLOW,
            ),
        ),
    )
    public = reference.public.model_copy(update={"policy": policy})
    same_tenant = next(
        item
        for item in public.attempts
        if not _attempt_is_cross_tenant(public, item.attempt_id)
        and item.requested_scope == "document:read"
        and item.tick == 15
    )
    different_tenant = next(
        item
        for item in public.attempts
        if _attempt_is_cross_tenant(public, item.attempt_id)
    )
    for item, expected in (
        (same_tenant, AuthorizationDecision.ALLOW),
        (different_tenant, AuthorizationDecision.DENY),
    ):
        resolved = resolve_adversarial_credential(public, item.credential_id)
        assert (
            evaluate_adversarial_attempt(public, item, resolved_principal_id=resolved)
            is expected
        )


def test_scope_and_time_must_hold_on_the_same_authority_grant() -> None:
    reference = _reference()
    public_data = _model_data(reference.public)
    original = public_data["grants"][0]
    public_data["grants"].append(
        {
            **original,
            "grant_id": "separate-admin-window",
            "allowed_scopes": ["document:admin"],
            "valid_from_tick": 20,
            "valid_until_tick": 30,
        }
    )
    public = EnterpriseAdversarialAuthorizationPublicV1.model_validate(public_data)
    scope_exceeded = next(
        item for item in public.attempts if item.requested_scope == "document:admin"
    )
    read_after_first_grant = next(
        item for item in public.attempts if item.requested_scope == "document:read"
    ).model_copy(update={"tick": 25})

    for attempt in (scope_exceeded, read_after_first_grant):
        resolved = resolve_adversarial_credential(public, attempt.credential_id)
        assert (
            evaluate_adversarial_attempt(
                public, attempt, resolved_principal_id=resolved
            )
            is AuthorizationDecision.DENY
        )


def test_empty_metric_helpers_remain_explicitly_null() -> None:
    reference = _reference()
    prediction = perfect_enterprise_adversarial_authorization_prediction(
        reference.evaluator
    )
    predicted = {item.attempt_id: item for item in prediction.attempts}
    truth = {item.attempt_id: item for item in reference.evaluator.cases}
    empty_attempt = _attempt_accuracy(
        family="empty",
        name="empty_attempt_accuracy",
        truth=(),
        predictions=predicted,
        matches=lambda _expected, _observed: True,
        denominator_meaning="no selected attempts",
    )
    empty_pair = _pair_accuracy((), truth, predicted)
    assert empty_attempt.value is None
    assert empty_pair.value is None
    assert empty_attempt.empty_behaviour is MetricEmptyBehaviour.NULL_IF_EMPTY


def test_reference_fails_if_a_declared_counterfactual_does_not_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        reference_module,
        "evaluate_adversarial_attempt",
        lambda *_args, **_kwargs: AuthorizationDecision.DENY,
    )
    with pytest.raises(
        AssertionError, match="reference adversarial pair failed to change decision"
    ):
        reference_module.reference_enterprise_adversarial_authorization()


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _all_keys(item)}
    return set()


def _attempt_is_cross_tenant(
    public: EnterpriseAdversarialAuthorizationPublicV1, attempt_id: str
) -> bool:
    attempt = next(item for item in public.attempts if item.attempt_id == attempt_id)
    principal_id = resolve_adversarial_credential(public, attempt.credential_id)
    principal = next(
        item for item in public.principals if item.principal_id == principal_id
    )
    resource = next(
        item for item in public.resources if item.resource_id == attempt.resource_id
    )
    return principal.tenant_id != resource.tenant_id


def _opposite(decision: AuthorizationDecision) -> AuthorizationDecision:
    return (
        AuthorizationDecision.DENY
        if decision is AuthorizationDecision.ALLOW
        else AuthorizationDecision.ALLOW
    )
