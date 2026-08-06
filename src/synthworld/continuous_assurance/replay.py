"""Structural validation and one-clock replay for continuous assurance."""

from __future__ import annotations

from collections.abc import Iterable

from synthworld.continuous_assurance.models import (
    ContinuousAssuranceCaseTruthV1,
    ContinuousAssuranceEvaluatorV1,
    ContinuousAssurancePublicV1,
    ContinuousAssuranceRemediationV1,
    ContinuousAssuranceSignalV1,
    ContinuousAssuranceSourceBindingV1,
    ContinuousAssuranceSourceFamily,
    FindingLifecycleState,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
    synthetic_digest,
)
from synthworld.enterprise.models import SyntheticDigestV1


class ContinuousAssuranceIntegrityError(ValueError):
    """Raised when assurance artifacts violate their deterministic contract."""


def source_public_bindings_digest(
    bindings: Iterable[ContinuousAssuranceSourceBindingV1],
) -> SyntheticDigestV1:
    """Digest the canonical public projection of the source binding tuple."""

    values = tuple(item.model_dump(mode="json") for item in bindings)
    return synthetic_digest(canonical_json_value_bytes(values))


def case_inventory_digest(
    public: ContinuousAssurancePublicV1,
) -> SyntheticDigestV1:
    """Digest only the public case inventory and its explicit references."""

    values = tuple(item.model_dump(mode="json") for item in public.cases)
    return synthetic_digest(canonical_json_value_bytes(values))


def validate_continuous_assurance_public(
    public: ContinuousAssurancePublicV1,
) -> None:
    """Validate references and checkpoints without interpreting drift truth."""

    expected_families = set(ContinuousAssuranceSourceFamily)
    bindings = {item.family: item for item in public.source_bindings}
    if set(bindings) != expected_families:
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance source family inventory differs"
        )
    if public.benchmark.source_public_bindings_digest != source_public_bindings_digest(
        public.source_bindings
    ):
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance source binding digest differs"
        )
    if public.benchmark.case_inventory_digest != case_inventory_digest(public):
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance case inventory digest differs"
        )

    signals = {item.signal_id: item for item in public.signals}
    remediations = {item.remediation_id: item for item in public.remediations}
    feed_windows = {item.feed_window_id: item for item in public.feed_windows}
    if len(signals) != len(public.signals):
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance signal identifiers must be unique"
        )
    if len(remediations) != len(public.remediations):
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance remediation identifiers must be unique"
        )

    used_signals: set[str] = set()
    used_remediations: set[str] = set()
    used_windows: set[str] = set()
    for case in public.cases:
        if not set(case.signal_ids) <= set(signals):
            raise ContinuousAssuranceIntegrityError(
                "continuous-assurance case references an unknown signal"
            )
        if not set(case.remediation_ids) <= set(remediations):
            raise ContinuousAssuranceIntegrityError(
                "continuous-assurance case references an unknown remediation"
            )
        if used_signals & set(case.signal_ids):
            raise ContinuousAssuranceIntegrityError(
                "continuous-assurance signal belongs to more than one case"
            )
        if used_remediations & set(case.remediation_ids):
            raise ContinuousAssuranceIntegrityError(
                "continuous-assurance remediation belongs to more than one case"
            )
        used_signals.update(case.signal_ids)
        used_remediations.update(case.remediation_ids)
        if case.feed_window_id is not None:
            if case.feed_window_id not in feed_windows:
                raise ContinuousAssuranceIntegrityError(
                    "continuous-assurance case references an unknown feed window"
                )
            if case.feed_window_id in used_windows:
                raise ContinuousAssuranceIntegrityError(
                    "continuous-assurance feed window belongs to more than one case"
                )
            used_windows.add(case.feed_window_id)
        for signal_id in case.signal_ids:
            signal = signals[signal_id]
            if signal.case_id != case.case_id:
                raise ContinuousAssuranceIntegrityError(
                    "continuous-assurance case and signal identifiers differ"
                )
        for remediation_id in case.remediation_ids:
            remediation = remediations[remediation_id]
            if remediation.case_id != case.case_id:
                raise ContinuousAssuranceIntegrityError(
                    "continuous-assurance case and remediation identifiers differ"
                )

    if used_signals != set(signals) or used_remediations != set(remediations):
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance case event inventory differs"
        )
    if used_windows != set(feed_windows):
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance case feed-window inventory differs"
        )

    for window in public.feed_windows:
        if not set(window.delayed_signal_ids) <= set(signals):
            raise ContinuousAssuranceIntegrityError(
                "continuous-assurance feed window references an unknown signal"
            )
        for signal_id in window.delayed_signal_ids:
            signal = signals[signal_id]
            if signal.source.family is not window.source_family:
                raise ContinuousAssuranceIntegrityError(
                    "continuous-assurance feed window source differs from signal"
                )
            if not (
                window.unavailable_from_tick
                <= signal.effective_tick
                < window.restored_at_tick
                <= signal.observation_tick
            ):
                raise ContinuousAssuranceIntegrityError(
                    "continuous-assurance delayed signal is outside its feed window"
                )

    maximum_tick = max(
        *(item.audit_tick for item in public.signals),
        *(item.audit_tick for item in public.remediations),
        *(item.restored_at_tick for item in public.feed_windows),
    )
    if maximum_tick > public.horizon_tick:
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance horizon precedes an event"
        )
    for checkpoint in public.checkpoints:
        expected_signals = tuple(
            sorted(
                item.signal_id
                for item in public.signals
                if item.observation_tick <= checkpoint.tick
            )
        )
        expected_remediations = tuple(
            sorted(
                item.remediation_id
                for item in public.remediations
                if item.observation_tick <= checkpoint.tick
            )
        )
        signal_evidence = {
            evidence
            for item in public.signals
            if item.audit_tick <= checkpoint.tick
            for evidence in item.evidence_refs
        }
        remediation_evidence = {
            evidence
            for item in public.remediations
            if item.audit_tick <= checkpoint.tick
            for evidence in item.evidence_refs
        }
        expected_evidence = tuple(sorted(signal_evidence | remediation_evidence))
        if (
            checkpoint.observed_signal_ids != expected_signals
            or checkpoint.observed_remediation_ids != expected_remediations
            or checkpoint.available_evidence_refs != expected_evidence
        ):
            raise ContinuousAssuranceIntegrityError(
                "continuous-assurance checkpoint projection differs"
            )


def validate_continuous_assurance_evaluator(
    public: ContinuousAssurancePublicV1,
    evaluator: ContinuousAssuranceEvaluatorV1,
) -> None:
    """Validate the physical boundary and evaluator inventory."""

    validate_continuous_assurance_public(public)
    if evaluator.public_digest != synthetic_digest(canonical_json_bytes(public)):
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance evaluator public digest differs"
        )
    evaluator_public_sources = tuple(
        ContinuousAssuranceSourceBindingV1(
            family=item.family,
            public_schema_version=item.public_schema_version,
            public_digest=item.public_digest,
        )
        for item in evaluator.source_bindings
    )
    if evaluator_public_sources != public.source_bindings:
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance evaluator source bindings differ"
        )
    case_ids = tuple(item.case_id for item in public.cases)
    truth_ids = tuple(item.case_id for item in evaluator.truth)
    if truth_ids != case_ids:
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance evaluator inventory differs"
        )
    for truth in evaluator.truth:
        if any(item.tick > public.horizon_tick for item in truth.lifecycle):
            raise ContinuousAssuranceIntegrityError(
                "continuous-assurance truth lifecycle exceeds the horizon"
            )
        if any(
            item > public.horizon_tick
            for item in truth.expected_recurrence_opened_ticks
        ):
            raise ContinuousAssuranceIntegrityError(
                "continuous-assurance recurrence exceeds the horizon"
            )


def canonical_signals_as_of(
    public: ContinuousAssurancePublicV1, *, tick: int
) -> tuple[ContinuousAssuranceSignalV1, ...]:
    """Return effective source state without applying observation delays."""

    _require_replay_tick(tick)
    validate_continuous_assurance_public(public)
    return tuple(item for item in public.signals if item.effective_tick <= tick)


def observed_signals_as_of(
    public: ContinuousAssurancePublicV1, *, tick: int
) -> tuple[ContinuousAssuranceSignalV1, ...]:
    """Return only signals actually observable by a checkpoint tick."""

    _require_replay_tick(tick)
    validate_continuous_assurance_public(public)
    return tuple(item for item in public.signals if item.observation_tick <= tick)


def observed_remediations_as_of(
    public: ContinuousAssurancePublicV1, *, tick: int
) -> tuple[ContinuousAssuranceRemediationV1, ...]:
    """Return remediation observations available at one tick."""

    _require_replay_tick(tick)
    validate_continuous_assurance_public(public)
    return tuple(item for item in public.remediations if item.observation_tick <= tick)


def expected_finding_state_at(
    truth: ContinuousAssuranceCaseTruthV1, *, tick: int
) -> FindingLifecycleState:
    """Replay the expected finding lifecycle through one inclusive tick."""

    _require_replay_tick(tick)
    state = FindingLifecycleState.CLEAR
    for transition in truth.lifecycle:
        if transition.tick > tick:
            break
        state = transition.state
    return state


def _require_replay_tick(tick: int) -> None:
    if tick < 0:
        raise ContinuousAssuranceIntegrityError(
            "continuous-assurance replay tick must be nonnegative"
        )


__all__ = [
    "ContinuousAssuranceIntegrityError",
    "canonical_signals_as_of",
    "case_inventory_digest",
    "expected_finding_state_at",
    "observed_remediations_as_of",
    "observed_signals_as_of",
    "source_public_bindings_digest",
    "validate_continuous_assurance_evaluator",
    "validate_continuous_assurance_public",
]
