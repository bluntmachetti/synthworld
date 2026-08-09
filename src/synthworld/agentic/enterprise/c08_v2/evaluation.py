"""Independent C08 v2 evidence metrics and case classification."""

from __future__ import annotations

from collections import defaultdict

from synthworld.agentic.enterprise.c08_v2.errors import (
    C08EvaluationError,
    C08ProjectionError,
)
from synthworld.agentic.enterprise.c08_v2.models import (
    C08CaseOutcomeV2,
    C08CaseResultV2,
    C08EvaluationMetricV2,
    C08EvaluationReportV2,
    C08EvidenceObservationV2,
    C08EvaluatorTruthV2,
    C08PublicInputV2,
    C08SubmissionV2,
)
from synthworld.agentic.enterprise.c08_v2.projection import (
    c08_public_input_digest,
    validate_c08_truth_against_public,
)


def _metric(
    name: str, numerator: int, denominator: int, meaning: str
) -> C08EvaluationMetricV2:
    if denominator:
        return C08EvaluationMetricV2(
            name=name,
            value=numerator / denominator,
            numerator=numerator,
            denominator=denominator,
            denominator_meaning=meaning,
        )
    return C08EvaluationMetricV2(
        name=name,
        value=None,
        numerator=0,
        denominator=0,
        denominator_meaning=meaning,
        undefined_reason="no submitted evidence observations",
    )


def evaluate_c08(
    *,
    public: C08PublicInputV2,
    evaluator: C08EvaluatorTruthV2,
    submission: C08SubmissionV2,
) -> C08EvaluationReportV2:
    """Score exact evidence binding without inspecting or proving retention."""

    expected_digest = c08_public_input_digest(public)
    if evaluator.public_input_digest != expected_digest:
        raise C08EvaluationError("C08 evaluator truth binds a different public input")
    if submission.public_input_digest != expected_digest:
        raise C08EvaluationError("C08 submission binds a different public input")

    actions = {item.action_id: item for item in public.actions}
    bindings = {item.action_id: item for item in evaluator.bindings}
    if set(actions) != set(bindings):
        raise C08EvaluationError("C08 actions and evaluator bindings differ")
    try:
        validate_c08_truth_against_public(public, evaluator)
    except C08ProjectionError as error:
        raise C08EvaluationError(str(error)) from error

    by_action: dict[str, list[C08EvidenceObservationV2]] = defaultdict(list)
    for observation in submission.observations:
        if observation.action_id not in actions:
            raise C08EvaluationError("C08 observation references an unknown action")
        by_action[observation.action_id].append(observation)

    known_owner = {
        event.evidence_id: (event.action_id, event.tenant_id)
        for event in public.evidence_events
    }
    outcomes: list[C08CaseResultV2] = []
    matched_required = 0
    correct_observations = 0
    submitted_count = len(submission.observations)
    fabricated_count = 0
    wrong_action_count = 0
    extra_count = 0
    required_count = sum(
        len(binding.required_evidence_ids) for binding in evaluator.bindings
    )

    for action in public.actions:
        binding = bindings[action.action_id]
        observations = by_action[action.action_id]
        required = set(binding.required_evidence_ids)
        seen_required: set[str] = set()
        action_fabricated = False
        action_wrong = False
        action_extra = False
        for observation in observations:
            owner = known_owner.get(observation.evidence_id)
            if owner is None:
                fabricated_count += 1
                action_fabricated = True
            elif owner != (action.action_id, action.tenant_id) or (
                observation.tenant_id != action.tenant_id
            ):
                wrong_action_count += 1
                action_wrong = True
            elif observation.evidence_id not in required:
                extra_count += 1
                action_extra = True
            elif observation.evidence_id in seen_required:
                extra_count += 1
                action_extra = True
            else:
                correct_observations += 1
                seen_required.add(observation.evidence_id)

        matched_required += len(seen_required)
        if action_fabricated:
            outcome = C08CaseOutcomeV2.FABRICATED
        elif action_wrong:
            outcome = C08CaseOutcomeV2.WRONG_ACTION
        elif action_extra:
            outcome = C08CaseOutcomeV2.EXTRA
        elif seen_required != required:
            outcome = C08CaseOutcomeV2.MISSING
        else:
            outcome = C08CaseOutcomeV2.EXACT
        outcomes.append(
            C08CaseResultV2(
                action_id=action.action_id,
                outcome=outcome,
                required_count=len(required),
                submitted_count=len(observations),
            )
        )

    metrics = (
        _metric(
            "evidence_action_binding_accuracy",
            correct_observations,
            submitted_count,
            "submitted evidence observations",
        ),
        _metric(
            "evidence_completeness_recall",
            matched_required,
            required_count,
            "evaluator-required evidence observations",
        ),
        _metric(
            "evidence_exact_match_accuracy",
            sum(item.outcome is C08CaseOutcomeV2.EXACT for item in outcomes),
            len(outcomes),
            "public actions",
        ),
        _metric(
            "evidence_extra_rate",
            extra_count,
            submitted_count,
            "submitted evidence observations",
        ),
        _metric(
            "evidence_fabrication_rate",
            fabricated_count,
            submitted_count,
            "submitted evidence observations",
        ),
        _metric(
            "evidence_wrong_action_rate",
            wrong_action_count,
            submitted_count,
            "submitted evidence observations",
        ),
    )
    return C08EvaluationReportV2(
        public_input_digest=expected_digest,
        outcomes=tuple(sorted(outcomes, key=lambda item: item.action_id)),
        metrics=tuple(sorted(metrics, key=lambda item: item.name)),
    )


__all__ = ["evaluate_c08"]
