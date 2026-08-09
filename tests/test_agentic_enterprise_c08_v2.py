"""Focused branch coverage for the isolated enterprise C08 v2 surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.agentic.enterprise.c08_v2 import (
    DEFAULT_C08_REFERENCE_SEED,
    C08CaseOutcomeV2,
    C08EvaluationError,
    C08EvaluationMetricV2,
    C08EvaluatorTruthV2,
    C08EvidenceBindingV2,
    C08EvidenceEventV2,
    C08EvidenceKindV2,
    C08EvidenceObservationV2,
    C08EvidenceRequirementV2,
    C08ProjectionError,
    C08SerializationError,
    C08SourceActionV2,
    C08SourceWorldV2,
    C08SubmissionV2,
    compile_c08_truth,
    c08_public_observation_id,
    evaluate_c08,
    export_c08_artifacts,
    generate_c08_reference,
    load_c08_evaluator,
    load_c08_public,
    load_c08_submission,
    project_c08_public,
    reference_submission_from_public,
    serialize_c08_public,
)
from synthworld.agentic.enterprise.c08_v2.models import (
    C08EvaluationReportV2,
    C08PublicInputV2,
)
from synthworld.agentic.enterprise.c08_v2.projection import c08_public_input_digest


_SOURCE_EVIDENCE_IDS = {
    "evidence-a-1",
    "evidence-a-2",
    "evidence-a-extra",
    "evidence-a-identity-extra",
    "evidence-b-1",
    "evidence-b-extra",
}


def _requirement(kind: C08EvidenceKindV2, handle: str) -> C08EvidenceRequirementV2:
    return C08EvidenceRequirementV2(kind=kind, binding_handle=handle)


def _public_evidence_id(evidence_id: str) -> str:
    if evidence_id in _SOURCE_EVIDENCE_IDS:
        return c08_public_observation_id(evidence_id)
    return evidence_id


def _source() -> C08SourceWorldV2:
    return C08SourceWorldV2(
        actions=(
            C08SourceActionV2(
                action_id="action-a",
                tenant_id="tenant-a",
                resource_id="resource-a",
                action="read",
                tick=1,
                required_evidence=(
                    _requirement(
                        C08EvidenceKindV2.AUTHORITY,
                        "binding-a-authority",
                    ),
                    _requirement(
                        C08EvidenceKindV2.IDENTITY,
                        "binding-a-identity",
                    ),
                ),
                required_evidence_ids=("evidence-a-1", "evidence-a-2"),
            ),
            C08SourceActionV2(
                action_id="action-b",
                tenant_id="tenant-b",
                resource_id="resource-b",
                action="write",
                tick=2,
                required_evidence=(
                    _requirement(C08EvidenceKindV2.POLICY, "binding-b-policy"),
                ),
                required_evidence_ids=("evidence-b-1",),
            ),
        ),
        evidence_events=(
            C08EvidenceEventV2(
                sequence=0,
                evidence_id="evidence-a-1",
                action_id="action-a",
                tenant_id="tenant-a",
                resource_id="resource-a",
                action="read",
                tick=1,
                kind=C08EvidenceKindV2.AUTHORITY,
                binding_handle="binding-a-authority",
                payload_digest="a" * 64,
            ),
            C08EvidenceEventV2(
                sequence=1,
                evidence_id="evidence-a-2",
                action_id="action-a",
                tenant_id="tenant-a",
                resource_id="resource-a",
                action="read",
                tick=1,
                kind=C08EvidenceKindV2.IDENTITY,
                binding_handle="binding-a-identity",
                payload_digest="b" * 64,
            ),
            C08EvidenceEventV2(
                sequence=2,
                evidence_id="evidence-a-extra",
                action_id="action-a",
                tenant_id="tenant-a",
                resource_id="resource-a",
                action="read",
                tick=1,
                kind=C08EvidenceKindV2.AUTHORITY,
                binding_handle="binding-a-distractor",
                payload_digest="c" * 64,
            ),
            C08EvidenceEventV2(
                sequence=3,
                evidence_id="evidence-a-identity-extra",
                action_id="action-a",
                tenant_id="tenant-a",
                resource_id="resource-a",
                action="read",
                tick=1,
                kind=C08EvidenceKindV2.IDENTITY,
                binding_handle="binding-a-identity-distractor",
                payload_digest="d" * 64,
            ),
            C08EvidenceEventV2(
                sequence=4,
                evidence_id="evidence-b-1",
                action_id="action-b",
                tenant_id="tenant-b",
                resource_id="resource-b",
                action="write",
                tick=2,
                kind=C08EvidenceKindV2.POLICY,
                binding_handle="binding-b-policy",
                payload_digest="e" * 64,
            ),
            C08EvidenceEventV2(
                sequence=5,
                evidence_id="evidence-b-extra",
                action_id="action-b",
                tenant_id="tenant-b",
                resource_id="resource-b",
                action="write",
                tick=2,
                kind=C08EvidenceKindV2.POLICY,
                binding_handle="binding-b-policy-distractor",
                payload_digest="f" * 64,
            ),
        ),
    )


def _bundle() -> tuple[C08PublicInputV2, C08EvaluatorTruthV2]:
    source = _source()
    public = project_c08_public(source)
    return public, compile_c08_truth(source, public)


def _submission(
    digest: str, rows: tuple[tuple[str, str, str], ...]
) -> C08SubmissionV2:
    return C08SubmissionV2(
        public_input_digest=digest,
        observations=tuple(
            C08EvidenceObservationV2(
                observation_id=f"observation-{index}",
                sequence=index,
                action_id=action_id,
                tenant_id=tenant_id,
                evidence_id=_public_evidence_id(evidence_id),
            )
            for index, (action_id, tenant_id, evidence_id) in enumerate(rows)
        ),
    )


def _outcome(report: C08EvaluationReportV2, action_id: str) -> C08CaseOutcomeV2:
    return next(item.outcome for item in report.outcomes if item.action_id == action_id)


def _reference_submission(public: C08PublicInputV2) -> C08SubmissionV2:
    events_by_semantics = {
        (event.action_id, event.kind, event.binding_handle): event
        for event in public.evidence_events
    }
    rows = tuple(
        (
            action.action_id,
            action.tenant_id,
            events_by_semantics[
                (
                    action.action_id,
                    requirement.kind,
                    requirement.binding_handle,
                )
            ].evidence_id,
        )
        for action in public.actions
        for requirement in action.required_evidence
    )
    return _submission(c08_public_input_digest(public), rows)


def test_projection_hides_bindings_and_exact_case_scores() -> None:
    public, evaluator = _bundle()
    public_payload = json.dumps(public.model_dump(mode="json"))
    assert "required_observation_ids" not in public_payload
    assert not any(item in public_payload for item in _SOURCE_EVIDENCE_IDS)
    assert {event.evidence_id for event in public.evidence_events} == {
        _public_evidence_id("evidence-a-1"),
        _public_evidence_id("evidence-a-2"),
        _public_evidence_id("evidence-a-extra"),
        _public_evidence_id("evidence-a-identity-extra"),
        _public_evidence_id("evidence-b-1"),
        _public_evidence_id("evidence-b-extra"),
    }
    assert evaluator.bindings[0].required_observation_ids == tuple(
        sorted(
            (
                _public_evidence_id("evidence-a-1"),
                _public_evidence_id("evidence-a-2"),
            )
        )
    )
    submission = _reference_submission(public)
    report = evaluate_c08(public=public, evaluator=evaluator, submission=submission)
    assert all(item.outcome is C08CaseOutcomeV2.EXACT for item in report.outcomes)
    assert {item.name for item in report.metrics} == {
        "evidence_action_binding_accuracy",
        "evidence_completeness_recall",
        "evidence_exact_match_accuracy",
        "evidence_extra_rate",
        "evidence_fabrication_rate",
        "evidence_wrong_action_rate",
    }
    assert next(
        item.value
        for item in report.metrics
        if item.name == "evidence_exact_match_accuracy"
    ) == 1.0


@pytest.mark.parametrize(
    ("name", "rows", "action_id", "expected"),
    [
        (
            "missing",
            (
                ("action-a", "tenant-a", "evidence-a-1"),
                ("action-b", "tenant-b", "evidence-b-1"),
            ),
            "action-a",
            C08CaseOutcomeV2.MISSING,
        ),
        (
            "fabricated",
            (
                ("action-a", "tenant-a", "evidence-a-1"),
                ("action-a", "tenant-a", "evidence-fake"),
                ("action-b", "tenant-b", "evidence-b-1"),
            ),
            "action-a",
            C08CaseOutcomeV2.FABRICATED,
        ),
        (
            "wrong-action",
            (
                ("action-a", "tenant-a", "evidence-a-1"),
                ("action-b", "tenant-b", "evidence-a-2"),
                ("action-b", "tenant-b", "evidence-b-1"),
            ),
            "action-b",
            C08CaseOutcomeV2.WRONG_ACTION,
        ),
        (
            "extra",
            (
                ("action-a", "tenant-a", "evidence-a-1"),
                ("action-a", "tenant-a", "evidence-a-2"),
                ("action-a", "tenant-a", "evidence-a-extra"),
                ("action-b", "tenant-b", "evidence-b-1"),
            ),
            "action-a",
            C08CaseOutcomeV2.EXTRA,
        ),
    ],
)
def test_discriminating_c08_outcomes(
    name: str,
    rows: tuple[tuple[str, str, str], ...],
    action_id: str,
    expected: C08CaseOutcomeV2,
) -> None:
    del name
    public, evaluator = _bundle()
    report = evaluate_c08(
        public=public,
        evaluator=evaluator,
        submission=_submission(c08_public_input_digest(public), rows),
    )
    assert _outcome(report, action_id) is expected


def test_metrics_have_independent_denominators_and_zero_submission_is_undefined(
) -> None:
    public, evaluator = _bundle()
    report = evaluate_c08(
        public=public,
        evaluator=evaluator,
        submission=_submission(c08_public_input_digest(public), ()),
    )
    values = {item.name: item for item in report.metrics}
    assert values["evidence_exact_match_accuracy"].denominator == 2
    assert values["evidence_completeness_recall"].denominator == 3
    assert values["evidence_action_binding_accuracy"].value is None
    assert values["evidence_action_binding_accuracy"].undefined_reason


def test_tenant_mismatch_is_not_an_allow() -> None:
    public, evaluator = _bundle()
    report = evaluate_c08(
        public=public,
        evaluator=evaluator,
        submission=_submission(
            c08_public_input_digest(public),
            (
                ("action-a", "tenant-a", "evidence-a-1"),
                ("action-a", "tenant-b", "evidence-a-2"),
                ("action-b", "tenant-b", "evidence-b-1"),
            ),
        ),
    )
    assert _outcome(report, "action-a") is C08CaseOutcomeV2.WRONG_ACTION


def test_projection_rejects_changed_public_action() -> None:
    source = _source()
    public = project_c08_public(source)
    changed = public.model_copy(
        update={
            "actions": (
                public.actions[0].model_copy(update={"tenant_id": "tenant-x"}),
                public.actions[1],
            )
        }
    )
    with pytest.raises(C08ProjectionError, match="differs from source"):
        compile_c08_truth(source, changed)


def test_compile_orders_evaluator_bindings_by_action_id() -> None:
    source = _source()
    renamed_actions = (
        source.actions[0].model_copy(update={"action_id": "z-action"}),
        source.actions[1].model_copy(update={"action_id": "a-action"}),
    )
    renamed_events = tuple(
        event.model_copy(
            update={
                "action_id": (
                    "z-action" if event.action_id == "action-a" else "a-action"
                )
            }
        )
        for event in source.evidence_events
    )
    renamed_source = C08SourceWorldV2(
        actions=renamed_actions,
        evidence_events=renamed_events,
    )
    public = project_c08_public(renamed_source)
    evaluator = compile_c08_truth(renamed_source, public)
    assert tuple(item.action_id for item in public.actions) == (
        "z-action",
        "a-action",
    )
    assert tuple(item.action_id for item in evaluator.bindings) == (
        "a-action",
        "z-action",
    )


def test_same_kind_distractors_are_allowed_but_duplicate_handles_are_rejected() -> None:
    public, _ = _bundle()
    authority_candidates = tuple(
        event
        for event in public.evidence_events
        if event.action_id == "action-a"
        and event.kind is C08EvidenceKindV2.AUTHORITY
    )
    assert len(authority_candidates) == 2
    assert len({event.binding_handle for event in authority_candidates}) == 2
    duplicate = authority_candidates[0].model_copy(
        update={
            "evidence_id": "observation-duplicate-handle",
            "sequence": len(public.evidence_events),
        }
    )
    invalid_public = public.model_copy(
        update={"evidence_events": (*public.evidence_events, duplicate)}
    )
    with pytest.raises(
        ValidationError,
        match="action/kind/handle bindings must be unique",
    ):
        C08PublicInputV2.model_validate(invalid_public.model_dump())
    with pytest.raises(ValueError, match="ambiguous"):
        reference_submission_from_public(invalid_public)


def test_public_requirement_without_nonrequired_same_kind_distractor_is_rejected(
) -> None:
    public, _ = _bundle()
    evidence_events = tuple(
        event
        for event in public.evidence_events
        if not (
            event.action_id == "action-a"
            and event.kind is C08EvidenceKindV2.IDENTITY
            and event.binding_handle == "binding-a-identity-distractor"
        )
    )
    payload = public.model_dump(mode="json")
    payload["evidence_events"] = [
        event.model_copy(update={"sequence": sequence}).model_dump(mode="json")
        for sequence, event in enumerate(evidence_events)
    ]
    with pytest.raises(
        ValidationError,
        match="same-action/same-kind distractor with a different binding handle",
    ):
        C08PublicInputV2.model_validate(payload)


def test_evaluation_rejects_digest_and_reference_mismatches() -> None:
    public, evaluator = _bundle()
    submission = _submission("0" * 64, ())
    with pytest.raises(C08EvaluationError, match="submission binds"):
        evaluate_c08(public=public, evaluator=evaluator, submission=submission)
    bad_evaluator = evaluator.model_copy(update={"public_input_digest": "1" * 64})
    with pytest.raises(C08EvaluationError, match="evaluator truth binds"):
        evaluate_c08(
            public=public,
            evaluator=bad_evaluator,
            submission=_submission(c08_public_input_digest(public), ()),
        )
    unknown_action = _submission(
        c08_public_input_digest(public), (("unknown", "tenant-a", "evidence-a-1"),)
    )
    with pytest.raises(C08EvaluationError, match="unknown action"):
        evaluate_c08(public=public, evaluator=evaluator, submission=unknown_action)
    incomplete = evaluator.model_copy(update={"bindings": evaluator.bindings[:1]})
    with pytest.raises(C08EvaluationError, match="actions and evaluator"):
        evaluate_c08(
            public=public,
            evaluator=incomplete,
            submission=_submission(c08_public_input_digest(public), ()),
        )


def test_evaluator_ids_must_match_public_event_semantics() -> None:
    public, evaluator = _bundle()
    missing = evaluator.bindings[0].model_copy(
        update={
            "required_observation_ids": (
                _public_evidence_id("evidence-a-2"),
                "observation-missing",
            )
        }
    )
    with pytest.raises(C08EvaluationError, match="missing public evidence"):
        evaluate_c08(
            public=public,
            evaluator=evaluator.model_copy(
                update={"bindings": (missing, evaluator.bindings[1])}
            ),
            submission=_reference_submission(public),
        )
    wrong_action = evaluator.bindings[0].model_copy(
        update={
            "required_observation_ids": (
                _public_evidence_id("evidence-a-2"),
                _public_evidence_id("evidence-b-1"),
            )
        }
    )
    with pytest.raises(C08EvaluationError, match="does not match its public action"):
        evaluate_c08(
            public=public,
            evaluator=evaluator.model_copy(
                update={"bindings": (wrong_action, evaluator.bindings[1])}
            ),
            submission=_reference_submission(public),
        )


def test_model_boundaries_reject_unordered_duplicate_and_unknown_records() -> None:
    source = _source()
    with pytest.raises(ValidationError, match="evidence identifiers must be sorted"):
        C08SourceActionV2(
            action_id="action-z",
            tenant_id="tenant-z",
            resource_id="resource-z",
            action="read",
            tick=0,
            required_evidence=(
                _requirement(C08EvidenceKindV2.AUTHORITY, "binding-z-authority"),
            ),
            required_evidence_ids=("z-2", "z-1"),
        )
    with pytest.raises(
        ValidationError, match="IDs and requirements must have equal length"
    ):
        C08SourceActionV2(
            action_id="action-z",
            tenant_id="tenant-z",
            resource_id="resource-z",
            action="read",
            tick=0,
            required_evidence=(
                _requirement(C08EvidenceKindV2.AUTHORITY, "binding-z-authority"),
            ),
            required_evidence_ids=("z-1", "z-2"),
        )
    unknown_required = source.actions[0].model_copy(
        update={"required_evidence_ids": ("evidence-a-missing", "evidence-a-2")}
    )
    with pytest.raises(ValidationError, match="not in the evidence stream"):
        C08SourceWorldV2(
            actions=(unknown_required, source.actions[1]),
            evidence_events=source.evidence_events,
        )
    with pytest.raises(ValidationError, match="ordered by tick"):
        C08SourceWorldV2(
            actions=tuple(reversed(source.actions)),
            evidence_events=source.evidence_events,
        )
    duplicate = source.actions[1].model_copy(update={"action_id": "action-a"})
    with pytest.raises(ValidationError, match="action identifiers must be unique"):
        C08SourceWorldV2(
            actions=(source.actions[0], duplicate),
            evidence_events=source.evidence_events,
        )
    duplicate_evidence = source.evidence_events[1].model_copy(
        update={"evidence_id": "evidence-a-1"}
    )
    with pytest.raises(ValidationError, match="globally unique"):
        C08SourceWorldV2(
            actions=source.actions,
            evidence_events=(
                source.evidence_events[0],
                duplicate_evidence,
                *source.evidence_events[2:],
            ),
        )
    public, evaluator = _bundle()
    with pytest.raises(ValidationError, match="contiguous sequence order"):
        C08PublicInputV2(
            actions=public.actions,
            evidence_events=tuple(reversed(public.evidence_events)),
        )
    tenant_tampered = public.evidence_events[0].model_copy(
        update={"tenant_id": "tenant-b"}
    )
    with pytest.raises(ValidationError, match="semantics differ"):
        C08PublicInputV2(
            actions=public.actions,
            evidence_events=(tenant_tampered, *public.evidence_events[1:]),
        )
    missing_kind = public.actions[0].model_copy(
        update={
            "required_evidence": (
                _requirement(C08EvidenceKindV2.POLICY, "binding-missing-policy"),
            )
        }
    )
    with pytest.raises(ValidationError, match="resolve exactly one observation"):
        C08PublicInputV2(
            actions=(missing_kind, public.actions[1]),
            evidence_events=public.evidence_events,
        )
    with pytest.raises(ValidationError, match="observation identifiers"):
        C08SubmissionV2(
            public_input_digest=c08_public_input_digest(public),
            observations=(
                C08EvidenceObservationV2(
                    observation_id="same",
                    sequence=0,
                    action_id="action-a",
                    tenant_id="tenant-a",
                    evidence_id="evidence-a-1",
                ),
                C08EvidenceObservationV2(
                    observation_id="same",
                    sequence=1,
                    action_id="action-a",
                    tenant_id="tenant-a",
                    evidence_id="evidence-a-2",
                ),
            ),
        )
    with pytest.raises(ValidationError, match="contiguous sequence"):
        C08SubmissionV2(
            public_input_digest=c08_public_input_digest(public),
            observations=(
                C08EvidenceObservationV2(
                    observation_id="observation-0",
                    sequence=1,
                    action_id="action-a",
                    tenant_id="tenant-a",
                    evidence_id=_public_evidence_id("evidence-a-1"),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="binding action identifiers"):
        C08EvaluatorTruthV2(
            public_input_digest=evaluator.public_input_digest,
            bindings=(evaluator.bindings[0], evaluator.bindings[0]),
        )
    with pytest.raises(ValidationError, match="globally unique"):
        C08EvaluatorTruthV2(
            public_input_digest=evaluator.public_input_digest,
            bindings=(
                evaluator.bindings[0],
                evaluator.bindings[1].model_copy(
                    update={
                        "required_evidence": (
                            _requirement(
                                C08EvidenceKindV2.AUTHORITY,
                                "binding-a-authority",
                            ),
                        ),
                        "required_observation_ids": (
                            _public_evidence_id("evidence-a-1"),
                        ),
                    }
                ),
            ),
        )


def test_metric_model_rejects_inconsistent_values() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        C08EvaluationMetricV2(
            name="bad",
            value=1.0,
            numerator=2,
            denominator=1,
            denominator_meaning="items",
        )
    with pytest.raises(ValidationError, match=r"undefined.*value"):
        C08EvaluationMetricV2(
            name="bad",
            value=0.0,
            numerator=0,
            denominator=0,
            denominator_meaning="items",
        )
    with pytest.raises(ValidationError, match="requires a reason"):
        C08EvaluationMetricV2(
            name="bad",
            numerator=0,
            denominator=0,
            denominator_meaning="items",
        )
    with pytest.raises(ValidationError, match="requires a value"):
        C08EvaluationMetricV2(
            name="bad",
            numerator=0,
            denominator=1,
            denominator_meaning="items",
        )
    with pytest.raises(ValidationError, match="undefined reason"):
        C08EvaluationMetricV2(
            name="bad",
            value=0.0,
            numerator=0,
            denominator=1,
            denominator_meaning="items",
            undefined_reason="wrong",
        )
    with pytest.raises(ValidationError, match="equal numerator"):
        C08EvaluationMetricV2(
            name="bad",
            value=0.5,
            numerator=0,
            denominator=1,
            denominator_meaning="items",
        )


def test_report_order_and_serialization_are_canonical_and_separate(
    tmp_path: Path,
) -> None:
    public, evaluator = _bundle()
    submission = _reference_submission(public)
    report = evaluate_c08(public=public, evaluator=evaluator, submission=submission)
    root = tmp_path / "c08"
    export_c08_artifacts(
        root, public=public, evaluator=evaluator, submission=submission, report=report
    )
    assert load_c08_public(root / "public" / "public-input.json") == public
    assert load_c08_evaluator(root / "evaluator" / "truth.json") == evaluator
    assert load_c08_submission(root / "submission" / "submission.json") == submission
    assert "required_observation_ids" not in (
        root / "public" / "public-input.json"
    ).read_text()
    with pytest.raises(C08SerializationError, match="already exists"):
        export_c08_artifacts(
            root, public=public, evaluator=evaluator, submission=submission
        )
    with pytest.raises(C08SerializationError, match="unreadable"):
        load_c08_public(root / "missing.json")
    noncanonical = json.dumps(public.model_dump(mode="json"), indent=2).encode()
    path = tmp_path / "noncanonical.json"
    path.write_bytes(noncanonical)
    with pytest.raises(C08SerializationError, match=r"not canonical"):
        load_c08_public(path)
    assert serialize_c08_public(public).endswith(b"\n")


def test_report_models_require_canonical_order() -> None:
    public, evaluator = _bundle()
    submission = _submission(
        c08_public_input_digest(public),
        (("action-a", "tenant-a", "evidence-a-1"),),
    )
    report = evaluate_c08(public=public, evaluator=evaluator, submission=submission)
    report_without_scope = report.model_dump(mode="json")
    del report_without_scope["measurement_scope"]
    with pytest.raises(ValidationError, match="measurement_scope"):
        C08EvaluationReportV2.model_validate(report_without_scope)
    with pytest.raises(ValidationError, match="outcomes must be sorted"):
        C08EvaluationReportV2(
            public_input_digest=report.public_input_digest,
            measurement_scope=report.measurement_scope,
            outcomes=tuple(reversed(report.outcomes)),
            metrics=report.metrics,
        )
    with pytest.raises(ValidationError, match="metrics must be sorted"):
        C08EvaluationReportV2(
            public_input_digest=report.public_input_digest,
            measurement_scope=report.measurement_scope,
            outcomes=report.outcomes,
            metrics=tuple(reversed(report.metrics)),
        )
    with pytest.raises(ValidationError, match="public action identifiers"):
        C08PublicInputV2(
            actions=(
                public.actions[0],
                public.actions[0],
            ),
            evidence_events=public.evidence_events,
        )
    with pytest.raises(ValidationError, match="public actions must be ordered"):
        C08PublicInputV2(
            actions=tuple(reversed(public.actions)),
            evidence_events=public.evidence_events,
        )
    with pytest.raises(
        ValidationError, match="IDs and requirements must have equal length"
    ):
        C08EvidenceBindingV2(
            action_id="action-x",
            tenant_id="tenant-x",
            required_evidence=(
                _requirement(C08EvidenceKindV2.AUTHORITY, "binding-x-authority"),
            ),
            required_observation_ids=("x-required", "x-extra"),
        )
    with pytest.raises(ValidationError, match="binding observation identifiers"):
        C08EvidenceBindingV2(
            action_id="action-x",
            tenant_id="tenant-x",
            required_evidence=(
                _requirement(C08EvidenceKindV2.AUTHORITY, "binding-x-authority"),
                _requirement(C08EvidenceKindV2.IDENTITY, "binding-x-identity"),
            ),
            required_observation_ids=("x-1", "x-1"),
        )


def test_reference_generator_is_deterministic_and_publicly_constructible() -> None:
    first = generate_c08_reference()
    second = generate_c08_reference(DEFAULT_C08_REFERENCE_SEED)
    different = generate_c08_reference(DEFAULT_C08_REFERENCE_SEED + 1)
    assert first == second
    assert first != different
    assert reference_submission_from_public(first.public) == first.reference_submission
    report = evaluate_c08(
        public=first.public,
        evaluator=first.evaluator,
        submission=first.reference_submission,
    )
    assert all(item.outcome is C08CaseOutcomeV2.EXACT for item in report.outcomes)
    assert tuple(item.action_id for item in first.evaluator.bindings) == tuple(
        item.action_id for item in first.public.actions
    )
    public_by_id = {item.action_id: item for item in first.public.actions}
    event_by_id = {item.evidence_id: item for item in first.public.evidence_events}
    assert tuple(event_by_id) == tuple(sorted(event_by_id))
    for binding in first.evaluator.bindings:
        action = public_by_id[binding.action_id]
        assert binding.tenant_id == action.tenant_id
        assert binding.required_evidence == action.required_evidence
        bound_events = tuple(
            event_by_id[item] for item in binding.required_observation_ids
        )
        assert {
            (item.kind, item.binding_handle) for item in bound_events
        } == {
            (item.kind, item.binding_handle) for item in binding.required_evidence
        }
        assert all(
            (item.action_id, item.tenant_id) == (action.action_id, action.tenant_id)
            for item in bound_events
        )
        for requirement in action.required_evidence:
            same_kind = tuple(
                event
                for event in first.public.evidence_events
                if event.action_id == action.action_id
                and event.kind is requirement.kind
            )
            assert len(same_kind) == 2
            assert sum(
                event.binding_handle == requirement.binding_handle
                for event in same_kind
            ) == 1
    assert len(first.public.actions) == 3
    assert all(
        sum(
            event.action_id == action.action_id
            for event in first.public.evidence_events
        )
        == 4
        for action in first.public.actions
    )
    report_payload = json.dumps(report.model_dump(mode="json"))
    assert "offline scoring does not prove live evidence retention" in report_payload
    assert "offline scoring does not prove durable logging" in report_payload
    assert "offline scoring does not prove enforcement behavior" in report_payload


@pytest.mark.parametrize("seed", [-1, True, False, 1.5, "20260809"])
def test_reference_generator_rejects_invalid_seeds(seed: object) -> None:
    with pytest.raises(ValueError, match="nonnegative integer"):
        generate_c08_reference(seed)  # type: ignore[arg-type]


def test_generated_c08_schemas_are_model_authoritative_and_checkable(
    tmp_path: Path,
) -> None:
    import importlib.util

    tool_path = Path(
        "enterprise-identity-access-contract/tools/generate_c08_v2_schemas.py"
    )
    spec = importlib.util.spec_from_file_location("c08_schema_generator", tool_path)
    assert spec is not None and spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    expected = tool.expected_schema_files(tmp_path)
    assert {path.name for path in expected} == {
        "c08-enterprise-public-v2.schema.json",
        "c08-enterprise-evaluator-v2.schema.json",
        "c08-enterprise-submission-v2.schema.json",
        "c08-enterprise-report-v2.schema.json",
    }
    report_path = next(
        path
        for path in expected
        if path.name == "c08-enterprise-report-v2.schema.json"
    )
    report_schema = json.loads(expected[report_path])
    assert "measurement_scope" in report_schema["required"]
    tool.write_schema_files(tmp_path)
    assert tool.main(["--check"]) == 0
    tool.check_schema_files(tmp_path)
    assert all(path.read_bytes() == payload for path, payload in expected.items())
    assert all(path.read_bytes().endswith(b"\n") for path in expected)

    unexpected = tmp_path / "schemas" / "c08-enterprise-unexpected-v2.schema.json"
    unexpected.write_bytes(b"{}\n")
    with pytest.raises(tool.C08SchemaDriftError, match="unexpected"):
        tool.check_schema_files(tmp_path)
    unexpected.unlink()

    drifted = next(iter(expected))
    drifted.write_bytes(drifted.read_bytes() + b"\n")
    with pytest.raises(tool.C08SchemaDriftError, match="drifted"):
        tool.check_schema_files(tmp_path)

    drifted.write_bytes(expected[drifted])
    drifted.unlink()
    with pytest.raises(tool.C08SchemaDriftError, match="missing"):
        tool.check_schema_files(tmp_path)
