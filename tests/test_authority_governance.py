"""Authority-change governance conformance, separation, and replay tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from synthworld.authority_governance import (
    AUTHORITY_GOVERNANCE_BASELINES,
    AuthorityChangeType,
    AuthorityGovernanceCaseKind,
    AuthorityGovernanceEvaluationError,
    AuthorityGovernanceEvaluatorV1,
    AuthorityGovernanceEventV1,
    AuthorityGovernanceIntegrityError,
    AuthorityGovernanceMetricV1,
    AuthorityGovernancePredictionV1,
    AuthorityGovernancePublicV1,
    AuthorityGovernanceReportV1,
    GovernanceAuditEventV1,
    GovernanceDecisionEventV1,
    GovernanceEnactmentEventV1,
    GovernanceMetricFamily,
    GovernanceRequestEventV1,
    active_approver_mandates,
    active_governance_policies,
    controlling_governance_decision,
    evaluate_authority_governance_prediction,
    materialize_authority_state,
    perfect_authority_governance_prediction,
    reference_authority_governance,
    validate_authority_governance_evaluator,
    validate_authority_governance_public,
)
from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.temporal_schedule import compile_governance_temporal_schedule


def test_reference_fixture_is_deterministic_bounded_and_visibility_safe() -> None:
    first = reference_authority_governance()
    second = reference_authority_governance()
    assert first == second
    assert len(first.public.cases) == 12
    assert len(first.public.events) == len(first.public.schedule) == 49
    assert {item.case_kind for item in first.evaluator.truth} == set(
        AuthorityGovernanceCaseKind
    )
    assert any(
        not item.governance_decision_authorised for item in first.evaluator.truth
    )
    assert any(not item.enactment_consistent for item in first.evaluator.truth)
    assert any(not item.audit_reconstructable for item in first.evaluator.truth)
    public_bytes = canonical_json_bytes(first.public)
    assert b"case_kind" not in public_bytes
    assert b"failure_reasons" not in public_bytes
    assert b"governance_decision_authorised" not in public_bytes
    assert b"timestamp" not in public_bytes and b"UTC" not in public_bytes
    validate_authority_governance_public(first.public)
    validate_authority_governance_evaluator(first.public, first.evaluator)


def test_one_clock_replay_decision_precedence_policy_and_mandate_boundaries() -> None:
    reference = reference_authority_governance()
    public = reference.public
    before_first = materialize_authority_state(public, as_of_tick=2)
    after_first = materialize_authority_state(public, as_of_tick=3)
    assert {item.authority_id for item in before_first.authorities} == {
        "authority-03",
        "authority-10",
    }
    assert {item.authority_id for item in after_first.authorities} == {
        "authority-01",
        "authority-03",
        "authority-10",
    }
    after_revocation = materialize_authority_state(public, as_of_tick=108)
    assert "authority-10" not in {
        item.authority_id for item in after_revocation.authorities
    }
    conflict = controlling_governance_decision(public, authority_change_id="change-11")
    assert conflict.decision_id == "decision:change-11:b"
    assert tuple(
        item.policy_version_id
        for item in active_governance_policies(public.policies, at_tick=65)
    ) == ("policy-v1",)
    assert tuple(
        item.policy_version_id
        for item in active_governance_policies(public.policies, at_tick=70)
    ) == ("policy-v2",)
    assert tuple(
        item.mandate_id
        for item in active_approver_mandates(public.approver_mandates, at_tick=49)
    ) == ("mandate-emergency", "mandate-expired", "mandate-valid")
    assert tuple(
        item.mandate_id
        for item in active_approver_mandates(public.approver_mandates, at_tick=55)
    ) == ("mandate-valid",)
    with pytest.raises(AuthorityGovernanceIntegrityError, match="replay tick"):
        materialize_authority_state(public, as_of_tick=-1)
    with pytest.raises(AuthorityGovernanceIntegrityError, match="policy lookup"):
        active_governance_policies(public.policies, at_tick=-1)
    with pytest.raises(AuthorityGovernanceIntegrityError, match="mandate lookup"):
        active_approver_mandates(public.approver_mandates, at_tick=-1)
    with pytest.raises(AuthorityGovernanceIntegrityError, match="change is unknown"):
        controlling_governance_decision(public, authority_change_id="change-missing")


def test_perfect_prediction_and_public_only_baselines_discriminate_dimensions() -> None:
    reference = reference_authority_governance()
    perfect = perfect_authority_governance_prediction(reference.evaluator)
    report = evaluate_authority_governance_prediction(
        public=reference.public,
        evaluator=reference.evaluator,
        prediction=perfect,
    )
    assert len(report.findings) == 12
    assert all(
        (
            item.state_correct
            and item.governance_authority_correct
            and item.policy_rationale_correct
            and item.evidence_observability_correct
            and item.enactment_correct
        )
        for item in report.findings
    )
    assert {item.family for item in report.metrics} == set(GovernanceMetricFamily)
    assert all(item.value == 1.0 and item.denominator > 0 for item in report.metrics)
    assert all(item.denominator_meaning for item in report.metrics)

    reports = {
        name: evaluate_authority_governance_prediction(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=baseline(reference.public),
        )
        for name, baseline in AUTHORITY_GOVERNANCE_BASELINES
    }
    assert len(reports) == 3
    assert (
        _metric(
            reports["Final state implies valid"],
            "governance_authorisation_accuracy",
        ).value
        < 1
    )
    assert (
        _metric(
            reports["Trust recorded approval"],
            "approver_authority_at_decision_accuracy",
        ).value
        < 1
    )
    assert _metric(reports["Use latest policy"], "policy_version_accuracy").value < 1


def test_evaluation_rejects_invalid_benchmark_and_prediction_inventory() -> None:
    reference = reference_authority_governance()
    bad_evaluator = reference.evaluator.model_copy(
        update={
            "public_digest": reference.evaluator.public_digest.model_copy(
                update={"value": "0" * 64}
            )
        }
    )
    prediction = perfect_authority_governance_prediction(reference.evaluator)
    with pytest.raises(AuthorityGovernanceEvaluationError, match="benchmark"):
        evaluate_authority_governance_prediction(
            public=reference.public,
            evaluator=bad_evaluator,
            prediction=prediction,
        )
    with pytest.raises(AuthorityGovernanceEvaluationError, match="inventory"):
        evaluate_authority_governance_prediction(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=prediction.model_copy(update={"rows": prediction.rows[:-1]}),
        )


@pytest.mark.parametrize(
    ("factory", "updates", "message"),
    [
        (
            lambda: reference_authority_governance().public.initial_state.authorities[
                0
            ],
            {"actions": ("write", "read")},
            "authority actions",
        ),
        (
            lambda: reference_authority_governance().public.initial_state.authorities[
                0
            ],
            {"valid_until_tick": 0},
            "validity",
        ),
        (
            lambda: reference_authority_governance().public.initial_state,
            {
                "authorities": (
                    reference_authority_governance().public.initial_state.authorities[
                        0
                    ],
                    reference_authority_governance().public.initial_state.authorities[
                        0
                    ],
                )
            },
            "authority state",
        ),
        (
            lambda: reference_authority_governance().public.policies[0].rules[0],
            {
                "change_types": (
                    AuthorityChangeType.SUPERSEDE,
                    AuthorityChangeType.GRANT,
                )
            },
            "enum members",
        ),
        (
            lambda: reference_authority_governance().public.policies[0].rules[0],
            {"control_ids": ("z", "a")},
            "policy control_ids",
        ),
        (
            lambda: reference_authority_governance().public.policies[0],
            {
                "rules": (
                    reference_authority_governance().public.policies[0].rules[1],
                    reference_authority_governance().public.policies[0].rules[0],
                )
            },
            "policy rules",
        ),
        (
            lambda: reference_authority_governance().public.policies[0],
            {"inactive_from_tick": 0},
            "activation",
        ),
        (
            lambda: reference_authority_governance().public.approver_mandates[0],
            {"change_types": (AuthorityChangeType.REVOKE, AuthorityChangeType.GRANT)},
            "mandate change types",
        ),
        (
            lambda: reference_authority_governance().public.approver_mandates[0],
            {"affected_authority_ids": ("z", "a")},
            "affected authorities",
        ),
        (
            lambda: reference_authority_governance().public.approver_mandates[0],
            {"valid_until_tick": 40},
            "mandate validity",
        ),
        (
            lambda: reference_authority_governance().public.evidence[0],
            {"retained_until_tick": 0},
            "evidence retention",
        ),
        (
            lambda: next(
                item
                for item in reference_authority_governance().public.events
                if isinstance(item, GovernanceDecisionEventV1)
            ),
            {"evidence_refs": ("z", "a")},
            "decision evidence_refs",
        ),
        (
            lambda: next(
                item
                for item in reference_authority_governance().public.events
                if isinstance(item, GovernanceAuditEventV1)
            ),
            {"retained_evidence_refs": ("z", "a")},
            "audit retained evidence",
        ),
    ],
)
def test_component_models_reject_noncanonical_or_backward_values(
    factory: Callable[[], BaseModel], updates: dict[str, object], message: str
) -> None:
    value = factory()
    with pytest.raises(ValidationError, match=message):
        _revalidate(type(value), value, **updates)


def test_result_models_reject_bad_counts_order_and_ratios() -> None:
    reference = reference_authority_governance()
    prediction = perfect_authority_governance_prediction(reference.evaluator)
    with pytest.raises(ValidationError, match="predictions"):
        AuthorityGovernancePredictionV1(rows=tuple(reversed(prediction.rows)))
    with pytest.raises(ValidationError, match="truth"):
        AuthorityGovernanceEvaluatorV1(
            public_digest=reference.evaluator.public_digest,
            truth=tuple(reversed(reference.evaluator.truth)),
        )
    metric = AuthorityGovernanceMetricV1(
        family=GovernanceMetricFamily.STATE,
        name="example",
        value=0.5,
        numerator=1,
        denominator=2,
        support=2,
        denominator_meaning="example cases",
    )
    for updates, message in (
        ({"numerator": 3}, "counts"),
        ({"support": 3}, "counts"),
        ({"value": 0.25}, "ratio"),
    ):
        with pytest.raises(ValidationError, match=message):
            _revalidate(AuthorityGovernanceMetricV1, metric, **updates)
    report = evaluate_authority_governance_prediction(
        public=reference.public,
        evaluator=reference.evaluator,
        prediction=prediction,
    )
    with pytest.raises(ValidationError, match="findings"):
        _revalidate(
            AuthorityGovernanceReportV1,
            report,
            findings=tuple(reversed(report.findings)),
        )
    with pytest.raises(ValidationError, match="metrics"):
        _revalidate(
            AuthorityGovernanceReportV1,
            report,
            metrics=(report.metrics[0], report.metrics[0]),
        )


def test_public_model_rejects_each_noncanonical_inventory() -> None:
    public = reference_authority_governance().public
    cases = (
        ("policies", tuple(reversed(public.policies)), "policies"),
        (
            "approver_mandates",
            tuple(reversed(public.approver_mandates)),
            "mandates",
        ),
        ("evidence", tuple(reversed(public.evidence)), "evidence"),
        ("cases", tuple(reversed(public.cases)), "cases"),
        ("events", tuple(reversed(public.events)), "events"),
    )
    for field, replacement, message in cases:
        with pytest.raises(ValidationError, match=message):
            _revalidate(AuthorityGovernancePublicV1, public, **{field: replacement})


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("policy_version_id", "policy-missing", "unknown policy version"),
        ("policy_rule_ids", ("rule-missing",), "unknown policy rule"),
        ("control_ids", ("control:missing",), "unknown policy control"),
        ("mandate_ids", ("mandate-missing",), "unknown mandate"),
        ("evidence_refs", ("evidence:missing",), "unknown evidence"),
    ],
)
def test_public_integrity_rejects_invalid_decision_references(
    field: str, replacement: object, message: str
) -> None:
    public = reference_authority_governance().public
    decision = next(
        item for item in public.events if isinstance(item, GovernanceDecisionEventV1)
    )
    changed = decision.model_copy(update={field: replacement})
    with pytest.raises(AuthorityGovernanceIntegrityError, match=message):
        validate_authority_governance_public(
            _replace_event(public, decision.id, changed)
        )


def test_public_integrity_rejects_schedule_event_audit_and_decision_id_failures() -> (
    None
):
    public = reference_authority_governance().public
    with pytest.raises(AuthorityGovernanceIntegrityError, match="schedule binding"):
        validate_authority_governance_public(
            public.model_copy(update={"schedule": public.schedule[:-1]})
        )
    request = next(
        item for item in public.events if isinstance(item, GovernanceRequestEventV1)
    )
    with pytest.raises(AuthorityGovernanceIntegrityError, match="unknown change"):
        validate_authority_governance_public(
            _replace_event(
                public,
                request.id,
                request.model_copy(update={"authority_change_id": "change-missing"}),
            )
        )
    decisions = tuple(
        item for item in public.events if isinstance(item, GovernanceDecisionEventV1)
    )
    with pytest.raises(AuthorityGovernanceIntegrityError, match="must be unique"):
        validate_authority_governance_public(
            _replace_event(
                public,
                decisions[1].id,
                decisions[1].model_copy(
                    update={"decision_id": decisions[0].decision_id}
                ),
            )
        )
    audit = next(
        item for item in public.events if isinstance(item, GovernanceAuditEventV1)
    )
    with pytest.raises(AuthorityGovernanceIntegrityError, match="audit references"):
        validate_authority_governance_public(
            _replace_event(
                public,
                audit.id,
                audit.model_copy(
                    update={"retained_evidence_refs": ("evidence:missing",)}
                ),
            )
        )


def test_public_integrity_rejects_case_inventory_type_order_and_link_failures() -> None:
    public = reference_authority_governance().public
    first = public.cases[0]
    with pytest.raises(AuthorityGovernanceIntegrityError, match="unknown event"):
        validate_authority_governance_public(
            public.model_copy(
                update={
                    "cases": (
                        first.model_copy(update={"audit_event_id": "event-missing"}),
                        *public.cases[1:],
                    )
                }
            )
        )
    with pytest.raises(AuthorityGovernanceIntegrityError, match="wrong type"):
        validate_authority_governance_public(
            public.model_copy(
                update={
                    "cases": (
                        first.model_copy(
                            update={"request_event_id": first.decision_event_ids[0]}
                        ),
                        *public.cases[1:],
                    )
                }
            )
        )
    with pytest.raises(AuthorityGovernanceIntegrityError, match="more than one"):
        validate_authority_governance_public(
            public.model_copy(update={"cases": (first, first, *public.cases[1:])})
        )

    extra = next(
        item for item in public.events if isinstance(item, GovernanceAuditEventV1)
    ).model_copy(update={"id": "change-01-99-extra-audit"})
    with pytest.raises(AuthorityGovernanceIntegrityError, match="inventory differs"):
        validate_authority_governance_public(_append_event(public, extra))

    request = next(
        item
        for item in public.events
        if isinstance(item, GovernanceRequestEventV1)
        and item.authority_change_id == first.authority_change_id
    )
    with pytest.raises(AuthorityGovernanceIntegrityError, match="identifiers differ"):
        validate_authority_governance_public(
            _replace_event(
                public,
                request.id,
                request.model_copy(update={"authority_change_id": "change-02"}),
            )
        )
    decision = next(
        item
        for item in public.events
        if isinstance(item, GovernanceDecisionEventV1)
        and item.authority_change_id == first.authority_change_id
    )
    with pytest.raises(AuthorityGovernanceIntegrityError, match="order differs"):
        validate_authority_governance_public(
            _replace_event(
                public,
                decision.id,
                decision.model_copy(update={"effective_tick": 0}),
            )
        )
    enactment = next(
        item
        for item in public.events
        if isinstance(item, GovernanceEnactmentEventV1)
        and item.authority_change_id == first.authority_change_id
    )
    with pytest.raises(
        AuthorityGovernanceIntegrityError, match="unknown case decision"
    ):
        validate_authority_governance_public(
            _replace_event(
                public,
                enactment.id,
                enactment.model_copy(update={"decision_id": "decision:change-02:a"}),
            )
        )


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        (
            "controlling_decision_id",
            "decision:missing",
            "unknown controlling decision",
        ),
        ("applicable_policy_version_id", "policy-missing", "unknown policy version"),
        ("applicable_policy_rule_ids", ("rule-missing",), "unknown policy rule"),
        ("applicable_control_ids", ("control:missing",), "unknown policy control"),
        (
            "required_decision_evidence_refs",
            ("evidence:missing",),
            "unknown evidence",
        ),
        (
            "superseded_authority_change_id",
            "change-missing",
            "unknown superseded change",
        ),
    ],
)
def test_evaluator_integrity_rejects_invalid_truth_references(
    field: str, replacement: object, message: str
) -> None:
    reference = reference_authority_governance()
    truth = reference.evaluator.truth[0].model_copy(update={field: replacement})
    evaluator = reference.evaluator.model_copy(
        update={"truth": (truth, *reference.evaluator.truth[1:])}
    )
    with pytest.raises(AuthorityGovernanceIntegrityError, match=message):
        validate_authority_governance_evaluator(reference.public, evaluator)


def test_evaluator_integrity_rejects_digest_and_inventory_mismatch() -> None:
    reference = reference_authority_governance()
    with pytest.raises(AuthorityGovernanceIntegrityError, match="public digest"):
        validate_authority_governance_evaluator(
            reference.public,
            reference.evaluator.model_copy(
                update={
                    "public_digest": reference.evaluator.public_digest.model_copy(
                        update={"value": "0" * 64}
                    )
                }
            ),
        )
    with pytest.raises(AuthorityGovernanceIntegrityError, match="inventory differs"):
        validate_authority_governance_evaluator(
            reference.public,
            reference.evaluator.model_copy(
                update={"truth": reference.evaluator.truth[:-1]}
            ),
        )


def test_nonblank_tuple_and_full_replay_branches() -> None:
    reference = reference_authority_governance()
    decision = next(
        item
        for item in reference.public.events
        if isinstance(item, GovernanceDecisionEventV1)
    )
    with pytest.raises(ValidationError, match="nonblank"):
        _revalidate(
            GovernanceDecisionEventV1,
            decision,
            evidence_refs=("",),
        )
    final = materialize_authority_state(reference.public, as_of_tick=999)
    assert "authority-12" in {item.authority_id for item in final.authorities}


def test_contract_generator_is_current() -> None:
    import importlib.util

    tool = Path("authority-governance-contract/tools/generate_contract.py")
    spec = importlib.util.spec_from_file_location("governance_contract", tool)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    files = module.expected_files()
    assert len(files) == 10
    assert all(path.read_bytes() == payload for path, payload in files.items())


def _metric(
    report: AuthorityGovernanceReportV1, name: str
) -> AuthorityGovernanceMetricV1:
    return next(item for item in report.metrics if item.name == name)


def _replace_event(
    public: AuthorityGovernancePublicV1,
    event_id: str,
    replacement: AuthorityGovernanceEventV1,
) -> AuthorityGovernancePublicV1:
    events = tuple(
        sorted(
            (replacement if item.id == event_id else item for item in public.events),
            key=lambda item: (item.effective_tick, item.id),
        )
    )
    return public.model_copy(
        update={
            "events": events,
            "schedule": compile_governance_temporal_schedule(
                events=events,
                event_schedule_version=public.event_schedule_version,
            ),
        }
    )


def _append_event(
    public: AuthorityGovernancePublicV1,
    event: AuthorityGovernanceEventV1,
) -> AuthorityGovernancePublicV1:
    events = tuple(
        sorted((*public.events, event), key=lambda item: (item.effective_tick, item.id))
    )
    return public.model_copy(
        update={
            "events": events,
            "schedule": compile_governance_temporal_schedule(
                events=events,
                event_schedule_version=public.event_schedule_version,
            ),
        }
    )


def _revalidate[ModelT: BaseModel](
    model: type[ModelT], instance: BaseModel, **updates: object
) -> ModelT:
    document = instance.model_dump(mode="python")
    document.update(updates)
    return model.model_validate(document)
