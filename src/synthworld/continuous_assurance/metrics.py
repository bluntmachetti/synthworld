"""Independent longitudinal assurance findings and denominator-bearing metrics."""

from __future__ import annotations

from synthworld.continuous_assurance.models import (
    ContinuousAssuranceCaseFindingV1,
    ContinuousAssuranceCaseTruthV1,
    ContinuousAssuranceEvaluatorV1,
    ContinuousAssuranceMetricAggregation,
    ContinuousAssuranceMetricFamily,
    ContinuousAssuranceMetricV1,
    ContinuousAssurancePredictionRowV1,
    ContinuousAssurancePredictionV1,
    ContinuousAssurancePublicV1,
    ContinuousAssuranceReportV1,
    FindingLifecycleState,
)
from synthworld.continuous_assurance.replay import (
    ContinuousAssuranceIntegrityError,
    expected_finding_state_at,
    validate_continuous_assurance_evaluator,
)


class ContinuousAssuranceEvaluationError(ValueError):
    """Raised when a continuous-assurance submission cannot be scored."""


def perfect_continuous_assurance_prediction(
    evaluator: ContinuousAssuranceEvaluatorV1,
) -> ContinuousAssurancePredictionV1:
    """Build exact expected lifecycle rows for scorer conformance."""

    return ContinuousAssurancePredictionV1(
        rows=tuple(_prediction_from_truth(item) for item in evaluator.truth)
    )


def evaluate_continuous_assurance_prediction(
    *,
    public: ContinuousAssurancePublicV1,
    evaluator: ContinuousAssuranceEvaluatorV1,
    prediction: ContinuousAssurancePredictionV1,
) -> ContinuousAssuranceReportV1:
    """Score detection, staleness, recurrence, remediation, and evidence separately."""

    try:
        validate_continuous_assurance_evaluator(public, evaluator)
    except ContinuousAssuranceIntegrityError as error:
        raise ContinuousAssuranceEvaluationError(
            "continuous-assurance benchmark is invalid"
        ) from error
    truth_ids = tuple(item.case_id for item in evaluator.truth)
    prediction_ids = tuple(item.case_id for item in prediction.rows)
    if prediction_ids != truth_ids:
        raise ContinuousAssuranceEvaluationError(
            "continuous-assurance prediction inventory differs from truth"
        )
    if any(
        tick > public.horizon_tick
        for row in prediction.rows
        for tick in (
            *(
                (row.finding_opened_tick,)
                if row.finding_opened_tick is not None
                else ()
            ),
            *row.finding_cleared_ticks,
            *row.recurrence_opened_ticks,
        )
    ):
        raise ContinuousAssuranceEvaluationError(
            "continuous-assurance prediction lifecycle exceeds the horizon"
        )
    rows = {item.case_id: item for item in prediction.rows}
    pairs = tuple((truth, rows[truth.case_id]) for truth in evaluator.truth)
    findings = tuple(_finding(public, truth, row) for truth, row in pairs)

    positives = tuple(pair for pair in pairs if pair[0].finding_required)
    negatives = tuple(pair for pair in pairs if not pair[0].finding_required)
    valid_detections = tuple(
        (truth, row) for truth, row in positives if _valid_detection(truth, row)
    )
    predicted_findings = tuple(
        pair for pair in pairs if pair[1].finding_opened_tick is not None
    )
    false_positives = sum(row.finding_opened_tick is not None for _, row in negatives)
    early_openings = sum(
        row.finding_opened_tick is not None
        and truth.first_observable_tick is not None
        and row.finding_opened_tick < truth.first_observable_tick
        for truth, row in positives
    )
    metrics = [
        _ratio(
            ContinuousAssuranceMetricFamily.DETECTION,
            "finding_detection_recall",
            len(valid_detections),
            len(positives),
            "truth cases requiring a finding",
        ),
        _ratio(
            ContinuousAssuranceMetricFamily.DETECTION,
            "false_negative_rate",
            len(positives) - len(valid_detections),
            len(positives),
            "truth cases requiring a finding",
        ),
        _ratio(
            ContinuousAssuranceMetricFamily.DETECTION,
            "false_positive_rate",
            false_positives,
            len(negatives),
            "truth cases requiring no finding",
        ),
        _ratio(
            ContinuousAssuranceMetricFamily.DETECTION,
            "finding_precision",
            len(valid_detections),
            len(predicted_findings),
            "submitted finding openings",
        ),
        _ratio(
            ContinuousAssuranceMetricFamily.DETECTION,
            "pre_observation_opening_rate",
            early_openings,
            len(positives),
            "truth cases requiring a finding",
        ),
        _ratio(
            ContinuousAssuranceMetricFamily.DETECTION,
            "finding_open_tick_accuracy",
            sum(
                row.finding_opened_tick == truth.expected_finding_opened_tick
                for truth, row in positives
            ),
            len(positives),
            "truth cases with an expected finding-open tick",
        ),
        _mean_ticks(
            ContinuousAssuranceMetricFamily.DETECTION,
            "detection_latency_mean_ticks",
            sum(_detection_latency(truth, row) for truth, row in valid_detections),
            len(valid_detections),
            "validly detected truth findings",
        ),
        _ratio(
            ContinuousAssuranceMetricFamily.CLASSIFICATION,
            "drift_classification_accuracy",
            sum(
                row.predicted_drift_kind is truth.drift_kind for truth, row in positives
            ),
            len(positives),
            "truth cases requiring drift classification",
        ),
    ]

    expected_clears = tuple(
        (truth, row, index, expected_tick)
        for truth, row in positives
        for index, expected_tick in enumerate(truth.expected_finding_cleared_ticks)
    )
    metrics.extend(
        (
            _ratio(
                ContinuousAssuranceMetricFamily.STALENESS,
                "finding_clear_tick_accuracy",
                sum(
                    index < len(row.finding_cleared_ticks)
                    and row.finding_cleared_ticks[index] == expected_tick
                    for _, row, index, expected_tick in expected_clears
                ),
                len(expected_clears),
                "expected finding-clear transitions",
            ),
            _mean_ticks(
                ContinuousAssuranceMetricFamily.STALENESS,
                "stale_finding_duration_mean_ticks",
                sum(
                    _stale_duration(
                        public.horizon_tick,
                        row,
                        index=index,
                        expected_tick=expected_tick,
                    )
                    for _, row, index, expected_tick in expected_clears
                ),
                len(expected_clears),
                "expected finding-clear transitions",
            ),
            _ratio(
                ContinuousAssuranceMetricFamily.STALENESS,
                "premature_clear_rate",
                sum(
                    index < len(row.finding_cleared_ticks)
                    and row.finding_cleared_ticks[index] < expected_tick
                    for _, row, index, expected_tick in expected_clears
                ),
                len(expected_clears),
                "expected finding-clear transitions",
            ),
        )
    )

    recurrence_expected = sum(
        len(truth.expected_recurrence_opened_ticks) for truth, _ in positives
    )
    recurrence_submitted = sum(len(row.recurrence_opened_ticks) for _, row in pairs)
    recurrence_matches = sum(
        len(
            set(truth.expected_recurrence_opened_ticks)
            & set(row.recurrence_opened_ticks)
        )
        for truth, row in positives
    )
    metrics.extend(
        (
            _ratio(
                ContinuousAssuranceMetricFamily.RECURRENCE,
                "recurrence_recall",
                recurrence_matches,
                recurrence_expected,
                "expected recurrence openings",
            ),
            _ratio(
                ContinuousAssuranceMetricFamily.RECURRENCE,
                "recurrence_precision",
                recurrence_matches,
                recurrence_submitted,
                "submitted recurrence openings",
            ),
        )
    )

    remediation_pairs = tuple(
        (truth, row)
        for truth, row in positives
        if truth.expected_remediation_complete is not None
    )
    evidence_pairs = tuple(
        (truth, row)
        for truth, row in positives
        if truth.expected_evidence_continuous is not None
    )
    checkpoint_total = len(public.checkpoints) * len(pairs)
    checkpoint_matches = sum(
        _checkpoint_state_matches(public, truth, row) for truth, row in pairs
    )
    metrics.extend(
        (
            _ratio(
                ContinuousAssuranceMetricFamily.REMEDIATION,
                "remediation_completeness_accuracy",
                sum(
                    row.remediation_complete is truth.expected_remediation_complete
                    for truth, row in remediation_pairs
                ),
                len(remediation_pairs),
                "truth cases with remediation-completeness truth",
            ),
            _ratio(
                ContinuousAssuranceMetricFamily.EVIDENCE,
                "evidence_continuity_accuracy",
                sum(
                    row.evidence_continuous is truth.expected_evidence_continuous
                    for truth, row in evidence_pairs
                ),
                len(evidence_pairs),
                "truth findings with evidence-continuity truth",
            ),
            _ratio(
                ContinuousAssuranceMetricFamily.DETECTION,
                "checkpoint_finding_state_accuracy",
                checkpoint_matches,
                checkpoint_total,
                "case and declared-checkpoint finding-state cells",
            ),
        )
    )
    return ContinuousAssuranceReportV1(
        findings=findings,
        metrics=tuple(sorted(metrics, key=lambda item: (item.family.value, item.name))),
    )


def _prediction_from_truth(
    truth: ContinuousAssuranceCaseTruthV1,
) -> ContinuousAssurancePredictionRowV1:
    if not truth.finding_required:
        return ContinuousAssurancePredictionRowV1(case_id=truth.case_id)
    return ContinuousAssurancePredictionRowV1(
        case_id=truth.case_id,
        predicted_drift_kind=truth.drift_kind,
        finding_opened_tick=truth.expected_finding_opened_tick,
        finding_cleared_ticks=truth.expected_finding_cleared_ticks,
        recurrence_opened_ticks=truth.expected_recurrence_opened_ticks,
        remediation_complete=truth.expected_remediation_complete,
        evidence_continuous=truth.expected_evidence_continuous,
    )


def _finding(
    public: ContinuousAssurancePublicV1,
    truth: ContinuousAssuranceCaseTruthV1,
    row: ContinuousAssurancePredictionRowV1,
) -> ContinuousAssuranceCaseFindingV1:
    expected_detection = truth.finding_required
    actual_detection = (
        _valid_detection(truth, row)
        if truth.finding_required
        else row.finding_opened_tick is not None
    )
    return ContinuousAssuranceCaseFindingV1(
        case_id=truth.case_id,
        detection_correct=actual_detection is expected_detection,
        classification_correct=(row.predicted_drift_kind is truth.drift_kind),
        opening_tick_correct=(
            row.finding_opened_tick == truth.expected_finding_opened_tick
        ),
        clearing_tick_correct=(
            row.finding_cleared_ticks == truth.expected_finding_cleared_ticks
        ),
        recurrence_correct=(
            row.recurrence_opened_ticks == truth.expected_recurrence_opened_ticks
        ),
        remediation_correct=(
            row.remediation_complete is truth.expected_remediation_complete
        ),
        evidence_continuity_correct=(
            row.evidence_continuous is truth.expected_evidence_continuous
        ),
        checkpoint_state_correct=(
            _checkpoint_state_matches(public, truth, row) == len(public.checkpoints)
        ),
    )


def _valid_detection(
    truth: ContinuousAssuranceCaseTruthV1,
    row: ContinuousAssurancePredictionRowV1,
) -> bool:
    if not truth.finding_required:
        return False
    return (
        row.finding_opened_tick is not None
        and truth.first_observable_tick is not None
        and row.finding_opened_tick >= truth.first_observable_tick
    )


def _detection_latency(
    truth: ContinuousAssuranceCaseTruthV1,
    row: ContinuousAssurancePredictionRowV1,
) -> int:
    if row.finding_opened_tick is None or truth.first_observable_tick is None:
        raise ContinuousAssuranceEvaluationError(
            "detection latency requires a validly detected finding"
        )
    return row.finding_opened_tick - truth.first_observable_tick


def _stale_duration(
    horizon_tick: int,
    row: ContinuousAssurancePredictionRowV1,
    *,
    index: int,
    expected_tick: int,
) -> int:
    if index >= len(row.finding_cleared_ticks):
        return horizon_tick - expected_tick
    return max(0, row.finding_cleared_ticks[index] - expected_tick)


def _checkpoint_state_matches(
    public: ContinuousAssurancePublicV1,
    truth: ContinuousAssuranceCaseTruthV1,
    row: ContinuousAssurancePredictionRowV1,
) -> int:
    return sum(
        _predicted_finding_state_at(row, tick=checkpoint.tick)
        is expected_finding_state_at(truth, tick=checkpoint.tick)
        for checkpoint in public.checkpoints
    )


def _predicted_finding_state_at(
    row: ContinuousAssurancePredictionRowV1, *, tick: int
) -> FindingLifecycleState:
    transitions: list[tuple[int, FindingLifecycleState]] = []
    if row.finding_opened_tick is not None:
        transitions.append((row.finding_opened_tick, FindingLifecycleState.OPEN))
    transitions.extend(
        (item, FindingLifecycleState.CLEAR) for item in row.finding_cleared_ticks
    )
    transitions.extend(
        (item, FindingLifecycleState.OPEN) for item in row.recurrence_opened_ticks
    )
    state = FindingLifecycleState.CLEAR
    for transition_tick, transition_state in sorted(
        transitions,
        key=lambda item: (
            item[0],
            0 if item[1] is FindingLifecycleState.OPEN else 1,
        ),
    ):
        if transition_tick > tick:
            break
        state = transition_state
    return state


def _ratio(
    family: ContinuousAssuranceMetricFamily,
    name: str,
    numerator: int,
    denominator: int,
    denominator_meaning: str,
) -> ContinuousAssuranceMetricV1:
    return _metric(
        family,
        name,
        ContinuousAssuranceMetricAggregation.RATIO,
        numerator,
        denominator,
        denominator_meaning,
    )


def _mean_ticks(
    family: ContinuousAssuranceMetricFamily,
    name: str,
    numerator: int,
    denominator: int,
    denominator_meaning: str,
) -> ContinuousAssuranceMetricV1:
    return _metric(
        family,
        name,
        ContinuousAssuranceMetricAggregation.MEAN_TICKS,
        numerator,
        denominator,
        denominator_meaning,
    )


def _metric(
    family: ContinuousAssuranceMetricFamily,
    name: str,
    aggregation: ContinuousAssuranceMetricAggregation,
    numerator: int,
    denominator: int,
    denominator_meaning: str,
) -> ContinuousAssuranceMetricV1:
    return ContinuousAssuranceMetricV1(
        family=family,
        name=name,
        aggregation=aggregation,
        value=None if denominator == 0 else numerator / denominator,
        numerator=numerator,
        denominator=denominator,
        support=denominator,
        denominator_meaning=denominator_meaning,
    )


__all__ = [
    "ContinuousAssuranceEvaluationError",
    "evaluate_continuous_assurance_prediction",
    "perfect_continuous_assurance_prediction",
]
