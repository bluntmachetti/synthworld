"""Deliberately weak public-only continuous-assurance baselines."""

from __future__ import annotations

from collections.abc import Callable

from synthworld.continuous_assurance.models import (
    AssuranceObservedState,
    ContinuousAssurancePredictionRowV1,
    ContinuousAssurancePredictionV1,
    ContinuousAssurancePublicV1,
    ContinuousAssuranceRemediationV1,
    ContinuousAssuranceSignalV1,
)
from synthworld.continuous_assurance.replay import (
    validate_continuous_assurance_public,
)

type ContinuousAssuranceBaseline = Callable[
    [ContinuousAssurancePublicV1], ContinuousAssurancePredictionV1
]

_PROBLEM_STATES = {
    AssuranceObservedState.ACTIVE,
    AssuranceObservedState.CHANGED,
    AssuranceObservedState.MISSING,
    AssuranceObservedState.PRESENT,
}
_CLEAR_STATES = {
    AssuranceObservedState.HEALTHY,
    AssuranceObservedState.INACTIVE,
    AssuranceObservedState.RETAINED,
    AssuranceObservedState.WITHDRAWN,
}


def latest_observed_state_baseline(
    public: ContinuousAssurancePublicV1,
) -> ContinuousAssurancePredictionV1:
    """Collapse each history to its final observed state."""

    return _observed_prediction(public, mode="latest")


def effective_time_is_detection_time_baseline(
    public: ContinuousAssurancePublicV1,
) -> ContinuousAssurancePredictionV1:
    """Incorrectly open findings when changes become effective, before observation."""

    return _observed_prediction(public, mode="effective")


def never_clear_findings_baseline(
    public: ContinuousAssurancePublicV1,
) -> ContinuousAssurancePredictionV1:
    """Detect visible drift but retain every opened finding through the horizon."""

    return _observed_prediction(public, mode="never_clear")


CONTINUOUS_ASSURANCE_BASELINES: tuple[tuple[str, ContinuousAssuranceBaseline], ...] = (
    ("Latest observed state", latest_observed_state_baseline),
    ("Effective time is detection time", effective_time_is_detection_time_baseline),
    ("Never clear findings", never_clear_findings_baseline),
)


def _observed_prediction(
    public: ContinuousAssurancePublicV1,
    *,
    mode: str,
) -> ContinuousAssurancePredictionV1:
    validate_continuous_assurance_public(public)
    signals = {item.signal_id: item for item in public.signals}
    remediations = {item.remediation_id: item for item in public.remediations}
    rows = []
    for case in public.cases:
        case_signals = tuple(signals[item] for item in case.signal_ids)
        case_remediations = tuple(remediations[item] for item in case.remediation_ids)
        problem_signals = tuple(
            sorted(
                (
                    item
                    for item in case_signals
                    if item.observed_state in _PROBLEM_STATES
                ),
                key=lambda item: (item.observation_tick, item.signal_id),
            )
        )
        if mode == "latest":
            rows.append(
                _latest_state_row(case.case_id, case_signals, case_remediations)
            )
            continue
        if not problem_signals:
            rows.append(ContinuousAssurancePredictionRowV1(case_id=case.case_id))
            continue
        first = problem_signals[0]
        opened_tick = (
            first.effective_tick if mode == "effective" else first.observation_tick
        )
        recurrence_ticks = tuple(
            (item.effective_tick if mode == "effective" else item.observation_tick)
            for item in problem_signals[1:]
        )
        clear_ticks: tuple[int, ...] = ()
        if mode != "never_clear":
            clear_ticks = _clear_ticks(case_signals, case_remediations)
        rows.append(
            ContinuousAssurancePredictionRowV1(
                case_id=case.case_id,
                predicted_drift_kind=first.dimension,
                finding_opened_tick=opened_tick,
                finding_cleared_ticks=clear_ticks,
                recurrence_opened_ticks=recurrence_ticks,
                remediation_complete=_remediation_guess(case_remediations),
                evidence_continuous=all(
                    item.observed_state is not AssuranceObservedState.MISSING
                    for item in case_signals
                ),
            )
        )
    return ContinuousAssurancePredictionV1(
        rows=tuple(sorted(rows, key=lambda item: item.case_id))
    )


def _latest_state_row(
    case_id: str,
    signals: tuple[ContinuousAssuranceSignalV1, ...],
    remediations: tuple[ContinuousAssuranceRemediationV1, ...],
) -> ContinuousAssurancePredictionRowV1:
    observed: tuple[ContinuousAssuranceSignalV1 | ContinuousAssuranceRemediationV1, ...]
    observed = (*signals, *remediations)
    latest = max(
        observed,
        key=lambda item: (
            item.observation_tick,
            getattr(item, "signal_id", getattr(item, "remediation_id", "")),
        ),
    )
    if latest.observed_state in _CLEAR_STATES:
        return ContinuousAssurancePredictionRowV1(case_id=case_id)
    return ContinuousAssurancePredictionRowV1(
        case_id=case_id,
        predicted_drift_kind=latest.dimension,
        finding_opened_tick=latest.observation_tick,
        remediation_complete=_remediation_guess(remediations),
        evidence_continuous=(
            latest.observed_state is not AssuranceObservedState.MISSING
        ),
    )


def _clear_ticks(
    signals: tuple[ContinuousAssuranceSignalV1, ...],
    remediations: tuple[ContinuousAssuranceRemediationV1, ...],
) -> tuple[int, ...]:
    signal_ticks = {
        item.observation_tick
        for item in signals
        if item.observed_state in _CLEAR_STATES
    }
    remediation_ticks = {
        item.observation_tick
        for item in remediations
        if item.observed_state in _CLEAR_STATES
    }
    return tuple(sorted(signal_ticks | remediation_ticks))


def _remediation_guess(
    remediations: tuple[ContinuousAssuranceRemediationV1, ...],
) -> bool | None:
    if not remediations:
        return None
    return all(item.observed_state in _CLEAR_STATES for item in remediations)


__all__ = [
    "CONTINUOUS_ASSURANCE_BASELINES",
    "ContinuousAssuranceBaseline",
    "effective_time_is_detection_time_baseline",
    "latest_observed_state_baseline",
    "never_clear_findings_baseline",
]
