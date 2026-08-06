"""Defensive validation and scorer edge cases for continuous assurance."""

from __future__ import annotations

from dataclasses import replace

import pytest

import synthworld.continuous_assurance.generator as generator_module
import synthworld.continuous_assurance.metrics as metrics_module
from synthworld.continuous_assurance import (
    ContinuousAssuranceEvaluationError,
    ContinuousAssuranceIntegrityError,
    ContinuousAssurancePredictionV1,
    ContinuousAssuranceSourceFamily,
    canonical_signals_as_of,
    case_inventory_digest,
    evaluate_continuous_assurance_prediction,
    expected_finding_state_at,
    generate_continuous_assurance,
    observed_remediations_as_of,
    observed_signals_as_of,
    perfect_continuous_assurance_prediction,
    reference_continuous_assurance,
    reference_continuous_assurance_sources,
    source_public_bindings_digest,
    validate_continuous_assurance_evaluator,
    validate_continuous_assurance_public,
)
from synthworld.continuous_assurance.models import (
    ContinuousAssuranceConfigV1,
    ContinuousAssuranceFeedWindowV1,
    ContinuousAssurancePredictionRowV1,
    ContinuousAssurancePublicV1,
)
from synthworld.enterprise.canonical import synthetic_digest


def _bound_public(
    public: ContinuousAssurancePublicV1, **updates: object
) -> ContinuousAssurancePublicV1:
    changed = public.model_copy(update=updates)
    benchmark = changed.benchmark.model_copy(
        update={
            "source_public_bindings_digest": source_public_bindings_digest(
                changed.source_bindings
            ),
            "case_inventory_digest": case_inventory_digest(changed),
        }
    )
    return changed.model_copy(update={"benchmark": benchmark})


def _assert_public_error(public: ContinuousAssurancePublicV1, message: str) -> None:
    with pytest.raises(ContinuousAssuranceIntegrityError, match=message):
        validate_continuous_assurance_public(public)


def test_public_validator_rejects_binding_and_identifier_corruption() -> None:
    public = reference_continuous_assurance().public

    _assert_public_error(
        _bound_public(public, source_bindings=public.source_bindings[:-1]),
        "source family inventory",
    )
    _assert_public_error(
        public.model_copy(
            update={
                "benchmark": public.benchmark.model_copy(
                    update={
                        "source_public_bindings_digest": synthetic_digest(
                            b"wrong sources\n"
                        )
                    }
                )
            }
        ),
        "source binding digest",
    )
    _assert_public_error(
        public.model_copy(
            update={
                "benchmark": public.benchmark.model_copy(
                    update={"case_inventory_digest": synthetic_digest(b"wrong cases\n")}
                )
            }
        ),
        "case inventory digest",
    )
    _assert_public_error(
        _bound_public(public, signals=(*public.signals, public.signals[0])),
        "signal identifiers",
    )
    _assert_public_error(
        _bound_public(
            public, remediations=(*public.remediations, public.remediations[0])
        ),
        "remediation identifiers",
    )


def test_public_validator_rejects_unknown_and_shared_case_references() -> None:
    public = reference_continuous_assurance().public

    unknown_signal_case = public.cases[0].model_copy(
        update={"signal_ids": ("unknown-signal",)}
    )
    _assert_public_error(
        _bound_public(public, cases=(unknown_signal_case, *public.cases[1:])),
        "unknown signal",
    )

    unknown_remediation_case = public.cases[0].model_copy(
        update={"remediation_ids": ("unknown-remediation",)}
    )
    _assert_public_error(
        _bound_public(public, cases=(unknown_remediation_case, *public.cases[1:])),
        "unknown remediation",
    )

    shared_signal_case = public.cases[1].model_copy(
        update={
            "signal_ids": tuple(
                sorted((*public.cases[1].signal_ids, public.cases[0].signal_ids[0]))
            )
        }
    )
    _assert_public_error(
        _bound_public(
            public,
            cases=(public.cases[0], shared_signal_case, *public.cases[2:]),
        ),
        "signal belongs to more than one case",
    )

    remediation_owners = {
        remediation_id: index
        for index, case in enumerate(public.cases)
        for remediation_id in case.remediation_ids
    }
    remediation_id, owner_index = next(
        (item, index)
        for item, index in remediation_owners.items()
        if index < len(public.cases) - 1
    )
    target_index = owner_index + 1
    target = public.cases[target_index].model_copy(
        update={
            "remediation_ids": tuple(
                sorted((*public.cases[target_index].remediation_ids, remediation_id))
            )
        }
    )
    cases = list(public.cases)
    cases[target_index] = target
    _assert_public_error(
        _bound_public(public, cases=tuple(cases)),
        "remediation belongs to more than one case",
    )


def test_public_validator_rejects_feed_case_and_event_inconsistency() -> None:
    public = reference_continuous_assurance().public
    feed_case_index = next(
        index
        for index, item in enumerate(public.cases)
        if item.feed_window_id is not None
    )
    feed_case = public.cases[feed_case_index]

    unknown = feed_case.model_copy(update={"feed_window_id": "unknown-window"})
    cases = list(public.cases)
    cases[feed_case_index] = unknown
    _assert_public_error(
        _bound_public(public, cases=tuple(cases)),
        "unknown feed window",
    )

    target_index = 0 if feed_case_index != 0 else 1
    shared = public.cases[target_index].model_copy(
        update={"feed_window_id": feed_case.feed_window_id}
    )
    cases = [feed_case, shared]
    cases.extend(
        item
        for index, item in enumerate(public.cases)
        if index not in {feed_case_index, target_index}
    )
    _assert_public_error(
        _bound_public(public, cases=tuple(cases)),
        "feed window belongs to more than one case",
    )

    signal_id = public.cases[0].signal_ids[0]
    signal_index = next(
        index
        for index, item in enumerate(public.signals)
        if item.signal_id == signal_id
    )
    changed_signal = public.signals[signal_index].model_copy(
        update={"case_id": "different-case"}
    )
    signals = list(public.signals)
    signals[signal_index] = changed_signal
    _assert_public_error(
        _bound_public(public, signals=tuple(signals)),
        "case and signal identifiers differ",
    )

    remediation_id = next(
        item.remediation_ids[0] for item in public.cases if item.remediation_ids
    )
    remediation_index = next(
        index
        for index, item in enumerate(public.remediations)
        if item.remediation_id == remediation_id
    )
    changed_remediation = public.remediations[remediation_index].model_copy(
        update={"case_id": "different-case"}
    )
    remediations = list(public.remediations)
    remediations[remediation_index] = changed_remediation
    _assert_public_error(
        _bound_public(public, remediations=tuple(remediations)),
        "case and remediation identifiers differ",
    )


@pytest.mark.parametrize("orphan_kind", ["signal", "remediation"])
def test_public_validator_rejects_orphan_events(orphan_kind: str) -> None:
    public = reference_continuous_assurance().public
    if orphan_kind == "signal":
        orphan_signal = public.signals[0].model_copy(
            update={"signal_id": "orphan-signal"}
        )
        changed = _bound_public(
            public,
            signals=tuple(
                sorted(
                    (*public.signals, orphan_signal),
                    key=lambda item: (item.effective_tick, item.signal_id),
                )
            ),
        )
    else:
        orphan_remediation = public.remediations[0].model_copy(
            update={"remediation_id": "orphan-remediation"}
        )
        changed = _bound_public(
            public,
            remediations=tuple(
                sorted(
                    (*public.remediations, orphan_remediation),
                    key=lambda item: (item.effective_tick, item.remediation_id),
                )
            ),
        )
    _assert_public_error(changed, "case event inventory differs")


def test_public_validator_rejects_unused_and_invalid_feed_windows() -> None:
    public = reference_continuous_assurance().public
    window = public.feed_windows[0]
    unused = window.model_copy(update={"feed_window_id": "unused-window"})
    _assert_public_error(
        _bound_public(
            public,
            feed_windows=tuple(
                sorted(
                    (*public.feed_windows, unused),
                    key=lambda item: item.feed_window_id,
                )
            ),
        ),
        "feed-window inventory differs",
    )

    def replace_window(
        updated: ContinuousAssuranceFeedWindowV1,
    ) -> ContinuousAssurancePublicV1:
        return _bound_public(public, feed_windows=(updated,))

    _assert_public_error(
        replace_window(window.model_copy(update={"delayed_signal_ids": ("unknown",)})),
        "unknown signal",
    )
    other_family = next(
        item
        for item in ContinuousAssuranceSourceFamily
        if item is not window.source_family
    )
    _assert_public_error(
        replace_window(window.model_copy(update={"source_family": other_family})),
        "source differs from signal",
    )
    delayed_signal = next(
        item
        for item in public.signals
        if item.signal_id == window.delayed_signal_ids[0]
    )
    _assert_public_error(
        replace_window(
            window.model_copy(
                update={"unavailable_from_tick": delayed_signal.effective_tick + 1}
            )
        ),
        "outside its feed window",
    )


def test_public_validator_rejects_horizon_and_checkpoint_corruption() -> None:
    public = reference_continuous_assurance().public
    _assert_public_error(
        _bound_public(public, horizon_tick=0),
        "horizon precedes an event",
    )
    bad_checkpoint = public.checkpoints[0].model_copy(
        update={"available_evidence_refs": ("unexpected",)}
    )
    _assert_public_error(
        _bound_public(
            public,
            checkpoints=(bad_checkpoint, *public.checkpoints[1:]),
        ),
        "checkpoint projection differs",
    )


def test_evaluator_validator_rejects_every_cross_tree_mismatch() -> None:
    benchmark = reference_continuous_assurance()
    evaluator = benchmark.evaluator

    with pytest.raises(ContinuousAssuranceIntegrityError, match="public digest"):
        validate_continuous_assurance_evaluator(
            benchmark.public,
            evaluator.model_copy(
                update={"public_digest": synthetic_digest(b"wrong public\n")}
            ),
        )
    wrong_source = evaluator.source_bindings[0].model_copy(
        update={"public_digest": synthetic_digest(b"wrong source\n")}
    )
    with pytest.raises(ContinuousAssuranceIntegrityError, match="source bindings"):
        validate_continuous_assurance_evaluator(
            benchmark.public,
            evaluator.model_copy(
                update={
                    "source_bindings": (wrong_source, *evaluator.source_bindings[1:])
                }
            ),
        )
    with pytest.raises(ContinuousAssuranceIntegrityError, match="inventory differs"):
        validate_continuous_assurance_evaluator(
            benchmark.public,
            evaluator.model_copy(update={"truth": tuple(reversed(evaluator.truth))}),
        )

    truth_index = next(
        index for index, item in enumerate(evaluator.truth) if item.lifecycle
    )
    truth = evaluator.truth[truth_index]
    late_transition = truth.lifecycle[-1].model_copy(
        update={"tick": benchmark.public.horizon_tick + 1}
    )
    late_truth = truth.model_copy(
        update={"lifecycle": (*truth.lifecycle[:-1], late_transition)}
    )
    late_truth_rows = list(evaluator.truth)
    late_truth_rows[truth_index] = late_truth
    with pytest.raises(ContinuousAssuranceIntegrityError, match="lifecycle exceeds"):
        validate_continuous_assurance_evaluator(
            benchmark.public,
            evaluator.model_copy(update={"truth": tuple(late_truth_rows)}),
        )

    recurrence_index = next(
        index
        for index, item in enumerate(evaluator.truth)
        if item.expected_recurrence_opened_ticks
    )
    recurrence = evaluator.truth[recurrence_index].model_copy(
        update={
            "expected_recurrence_opened_ticks": (benchmark.public.horizon_tick + 1,)
        }
    )
    truth_rows = list(evaluator.truth)
    truth_rows[recurrence_index] = recurrence
    with pytest.raises(ContinuousAssuranceIntegrityError, match="recurrence exceeds"):
        validate_continuous_assurance_evaluator(
            benchmark.public,
            evaluator.model_copy(update={"truth": tuple(truth_rows)}),
        )


def test_replay_rejects_negative_ticks() -> None:
    benchmark = reference_continuous_assurance()
    truth = benchmark.evaluator.truth[0]
    with pytest.raises(ContinuousAssuranceIntegrityError, match="nonnegative"):
        canonical_signals_as_of(benchmark.public, tick=-1)
    with pytest.raises(ContinuousAssuranceIntegrityError, match="nonnegative"):
        observed_signals_as_of(benchmark.public, tick=-1)
    with pytest.raises(ContinuousAssuranceIntegrityError, match="nonnegative"):
        observed_remediations_as_of(benchmark.public, tick=-1)
    with pytest.raises(ContinuousAssuranceIntegrityError, match="nonnegative"):
        expected_finding_state_at(truth, tick=-1)


def test_generator_rejects_invalid_source_bindings_and_empty_catalogues() -> None:
    sources = reference_continuous_assurance_sources()
    bad_evaluator = sources.identity_fabric_evaluator.model_copy(
        update={"public_input_digest": synthetic_digest(b"wrong source\n")}
    )
    with pytest.raises(ValueError, match="source evaluator binding differs"):
        generate_continuous_assurance(
            sources=replace(sources, identity_fabric_evaluator=bad_evaluator),
            config=ContinuousAssuranceConfigV1(),
        )
    with pytest.raises(ValueError, match="source family has no records"):
        generator_module._select_source_record((), ContinuousAssuranceConfigV1(), 0, 0)
    no_remediation = next(
        item for item in generator_module._TEMPLATES if item.remediation_state is None
    )
    with pytest.raises(ValueError, match="no remediation state"):
        generator_module._remediation(
            config=ContinuousAssuranceConfigV1(),
            case_id="case",
            template=no_remediation,
            cycle=0,
            suffix="invalid",
            base_tick=1,
        )


def test_scorer_rejects_bad_benchmarks_inventories_and_future_ticks() -> None:
    benchmark = reference_continuous_assurance()
    prediction = perfect_continuous_assurance_prediction(benchmark.evaluator)
    bad_evaluator = benchmark.evaluator.model_copy(
        update={"public_digest": synthetic_digest(b"wrong public\n")}
    )
    with pytest.raises(
        ContinuousAssuranceEvaluationError, match="benchmark is invalid"
    ):
        evaluate_continuous_assurance_prediction(
            public=benchmark.public,
            evaluator=bad_evaluator,
            prediction=prediction,
        )
    with pytest.raises(
        ContinuousAssuranceEvaluationError, match="prediction inventory differs"
    ):
        evaluate_continuous_assurance_prediction(
            public=benchmark.public,
            evaluator=benchmark.evaluator,
            prediction=ContinuousAssurancePredictionV1(rows=prediction.rows[:-1]),
        )
    future = prediction.rows[0].model_copy(
        update={"finding_opened_tick": benchmark.public.horizon_tick + 1}
    )
    with pytest.raises(ContinuousAssuranceEvaluationError, match="exceeds the horizon"):
        evaluate_continuous_assurance_prediction(
            public=benchmark.public,
            evaluator=benchmark.evaluator,
            prediction=prediction.model_copy(
                update={"rows": (future, *prediction.rows[1:])}
            ),
        )


def test_internal_metric_guards_reject_impossible_latency_inputs() -> None:
    benchmark = reference_continuous_assurance()
    negative = next(
        item for item in benchmark.evaluator.truth if not item.finding_required
    )
    empty_row = ContinuousAssurancePredictionRowV1(case_id=negative.case_id)
    assert not metrics_module._valid_detection(negative, empty_row)
    positive = next(item for item in benchmark.evaluator.truth if item.finding_required)
    with pytest.raises(ContinuousAssuranceEvaluationError, match="requires a valid"):
        metrics_module._detection_latency(positive, empty_row)
