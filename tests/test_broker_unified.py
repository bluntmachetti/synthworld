"""The broker pack through the unified evaluator - #5's last acceptance criterion."""

from __future__ import annotations

import pytest

from synthworld.broker_metrics import (
    BrokerAssessment,
    believe_the_broker,
    match_on_published_evidence,
)
from synthworld.evaluation import EvaluationInputError, evaluate_broker_removal
from synthworld.temporal import materialise
from synthworld.temporal_generator import generate_temporal_world

_SEED = 11


def _assessment(seed: int = _SEED) -> BrokerAssessment:
    world = generate_temporal_world(seed=seed)
    timeline = materialise(world, as_of=world.horizon)
    return match_on_published_evidence(timeline)


def test_the_unified_report_carries_every_family_once() -> None:
    """One parser reads five packs: same shape, families named, support explained.

    The native `BrokerRemovalMetrics` stays the full account; this projection must not
    recompute anything, so each ratio here is asserted equal to a value that also
    appears there. A projection that rescored would eventually disagree with what it
    projects, and nothing would say which one was lying.
    """

    report = evaluate_broker_removal(_assessment(), seed=_SEED)

    assert report.task == "broker_removal"
    assert report.schema_version == "0.2.0"
    families = [metric.family for metric in report.metrics]
    assert families == [
        "discovery",
        "attribution",
        "request_conduct",
        "request_conduct",
        "removal",
        "propagation",
        "propagation",
        "recurrence",
        "recurrence",
    ]
    assert all(metric.support_meaning for metric in report.metrics)
    # Content digests bind the report to the exact bytes scored - the same discipline
    # every other task's report carries.
    assert dict(report.artifact_checksums).keys() == {"public", "truth"}
    assert all(len(value) == 64 for value in dict(report.artifact_checksums).values())


def test_the_projection_never_disagrees_with_the_native_report() -> None:
    from synthworld.broker_metrics import evaluate_broker_assessment

    world = generate_temporal_world(seed=_SEED)
    timeline = materialise(world, as_of=world.horizon)
    submission = believe_the_broker(timeline)
    native = evaluate_broker_assessment(
        submission, timeline=timeline, truth=world.truth
    )

    report = evaluate_broker_removal(submission, seed=_SEED)
    by_name = {metric.name: metric for metric in report.metrics}

    assert by_name["completion_accuracy"].value == native.completion_accuracy.value
    assert by_name["propagation_lag_mean_error"].value == (
        native.propagation_lag.mean_absolute_error
    )
    assert (
        by_name["propagation_lag_mean_error"].support == native.propagation_lag.support
    )


def test_the_precision_halves_separate_a_spammer_from_a_careful_system() -> None:
    """The review finding this codifies: recall alone teaches greed.

    Requesting everything and alerting on everything maximises both recall metrics.
    The native report prices that with `unwarranted_requests` and
    `false_recurrence_alerts`, and a first projection dropped both - so through the
    CLI, the spammer and the careful system were indistinguishable.
    """

    world = generate_temporal_world(seed=_SEED)
    timeline = materialise(world, as_of=world.horizon)
    careful = match_on_published_evidence(timeline)
    spammer = careful.model_copy(
        update={
            "listings": tuple(
                item.model_copy(
                    update={
                        "requested_removal": True,
                        "reappearance_alerted": True,
                        # A listing cannot coherently be believed removed and
                        # reported back; the spammer keeps coherent and greedy.
                        "believed_removed": False,
                    }
                )
                for item in careful.listings
            )
        }
    )

    careful_by = {
        m.name: m for m in evaluate_broker_removal(careful, seed=_SEED).metrics
    }
    spam_by = {m.name: m for m in evaluate_broker_removal(spammer, seed=_SEED).metrics}

    assert spam_by["recurrence_recall"].value == careful_by["recurrence_recall"].value
    assert spam_by["false_recurrence_alerts"].value is not None
    assert careful_by["false_recurrence_alerts"].value is not None
    assert (
        spam_by["false_recurrence_alerts"].value
        > careful_by["false_recurrence_alerts"].value
    )
    assert spam_by["unwarranted_requests"].value is not None
    assert careful_by["unwarranted_requests"].value is not None
    assert (
        spam_by["unwarranted_requests"].value
        >= careful_by["unwarranted_requests"].value
    )


def test_an_assessment_of_unknown_listings_is_a_unified_input_error() -> None:
    """`BrokerEvaluationError` becomes `EvaluationInputError` at the boundary.

    The CLI catches the unified type; before the translation, a structurally valid
    assessment naming an undiscovered listing escaped as a raw traceback.
    """

    world = generate_temporal_world(seed=_SEED)
    timeline = materialise(world, as_of=world.horizon)
    doctored = match_on_published_evidence(timeline).model_copy(
        update={
            "listings": tuple(
                item.model_copy(update={"listing_ref": f"unknown-{index}"})
                for index, item in enumerate(
                    match_on_published_evidence(timeline).listings
                )
            )
        }
    )

    with pytest.raises(EvaluationInputError):
        evaluate_broker_removal(doctored, seed=_SEED)


def test_a_tick_beyond_the_horizon_is_refused_before_scoring() -> None:
    """A submission for a tick the world never reached cannot be scored against it."""

    world = generate_temporal_world(seed=_SEED)
    timeline = materialise(world, as_of=world.horizon)
    late = match_on_published_evidence(timeline).model_copy(
        update={"as_of": world.horizon + 1}
    )

    with pytest.raises(EvaluationInputError, match="after the world's horizon"):
        evaluate_broker_removal(late, seed=_SEED)


def test_the_report_replays_byte_identically() -> None:
    first = evaluate_broker_removal(_assessment(), seed=_SEED)
    again = evaluate_broker_removal(_assessment(), seed=_SEED)

    assert first.model_dump_json() == again.model_dump_json()
