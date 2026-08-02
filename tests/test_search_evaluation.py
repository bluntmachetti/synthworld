"""Scoring the search projection, and what the report refuses to hide."""

from __future__ import annotations

from collections import Counter

import pytest
from pydantic import ValidationError

from synthworld.search import SearchMatchTruth
from synthworld.search_baselines import (
    SEARCH_BASELINES,
    Policy,
    accept_everything,
    exact_name_in_title,
    folded_name_with_abstention,
    run_search_baseline,
)
from synthworld.search_generator import SearchProjection, generate_search_projection
from synthworld.search_metrics import (
    ResultDecision,
    ResultJudgement,
    SearchEvaluation,
    SearchEvaluationError,
    evaluate_search_judgements,
)

_SEEDS = (1, 2, 3)


def _projection(seed: int = 1) -> SearchProjection:
    return generate_search_projection(seed=seed)


def test_accepting_everything_finds_every_true_match_and_every_collision() -> None:
    """The floor a report must not flatter.

    Accepting everything achieves perfect recall and attaches every stranger's
    record to the subject. Any measure that rewards it is measuring the wrong thing.
    """

    metrics = run_search_baseline(accept_everything, projection=_projection()).metrics

    assert metrics.false_rejects == 0
    assert metrics.false_accepts > 0
    assert metrics.unwarranted_decisions > 0
    assert metrics.coverage == 1.0


def test_exact_matching_fails_the_transliterated_spelling() -> None:
    """Both spellings of one identity exist so this is measurable.

    An earlier generator alternated spellings by subject, so a consumer that
    normalises one direction and not the other was never exercised.
    """

    exact = run_search_baseline(exact_name_in_title, projection=_projection()).metrics
    folded = run_search_baseline(
        folded_name_with_abstention, projection=_projection()
    ).metrics

    assert exact.false_rejects > folded.false_rejects


def test_abstention_buys_precision_at_the_cost_of_coverage() -> None:
    deciding = run_search_baseline(accept_everything, projection=_projection()).metrics
    abstaining = run_search_baseline(
        folded_name_with_abstention, projection=_projection()
    ).metrics

    assert abstaining.coverage < deciding.coverage
    assert deciding.decided_precision is not None
    assert abstaining.decided_precision is not None
    assert abstaining.decided_precision > deciding.decided_precision
    assert abstaining.unwarranted_decisions < deciding.unwarranted_decisions


def test_syndicated_copies_are_reported_apart_from_findings() -> None:
    """Three aggregator copies of one source record are one finding.

    A consumer counting them separately overstates exposure threefold, and the gap
    between accepted results and distinct findings is where that shows.
    """

    metrics = run_search_baseline(accept_everything, projection=_projection()).metrics

    assert metrics.distinct_findings < metrics.accepted_results


def test_stale_acceptances_are_counted() -> None:
    """Accepting a long-superseded observation is a distinct kind of wrong."""

    metrics = run_search_baseline(accept_everything, projection=_projection()).metrics

    assert metrics.stale_accepted > 0


def test_false_accepts_and_false_rejects_are_never_merged() -> None:
    """Different harms: one attaches a stranger's exposure, the other loses real
    exposure. A single figure trades them silently."""

    fields = set(SearchEvaluation.model_fields) | set(
        run_search_baseline(
            accept_everything, projection=_projection()
        ).metrics.__class__.model_fields
    )

    assert "false_accepts" in fields and "false_rejects" in fields
    assert not {"accuracy", "f1", "score"} & fields


def test_deciding_an_undecidable_result_is_counted_apart() -> None:
    """Not a wrong answer - an unwarranted one."""

    projection = _projection()
    undecidable = [
        item.result_id
        for item in projection.truth.results
        if item.match is SearchMatchTruth.INSUFFICIENT_EVIDENCE
    ]
    judgements = [
        ResultJudgement(
            result_id=item.result_id,
            decision=(
                ResultDecision.ACCEPT
                if item.result_id in undecidable
                else ResultDecision.ABSTAIN
            ),
        )
        for item in projection.truth.results
    ]
    metrics = evaluate_search_judgements(judgements, truth=projection.truth).metrics

    assert metrics.unwarranted_decisions == len(undecidable)
    assert metrics.false_accepts == 0
    assert metrics.false_rejects == 0


def test_abstaining_everywhere_reports_no_precision_and_no_coverage() -> None:
    projection = _projection()
    metrics = evaluate_search_judgements(
        [
            ResultJudgement(result_id=item.result_id, decision=ResultDecision.ABSTAIN)
            for item in projection.truth.results
        ],
        truth=projection.truth,
    ).metrics

    assert metrics.coverage == 0.0
    assert metrics.decided_precision is None
    assert metrics.accepted_results == 0
    assert metrics.distinct_findings == 0


def test_the_evaluation_names_the_projection_it_scored() -> None:
    """A report paired with a different run's projection is not detectable
    otherwise."""

    projection = _projection()
    evaluation = run_search_baseline(accept_everything, projection=projection)

    assert evaluation.public_digest == projection.truth.public_digest
    assert evaluation.public_digest != _projection(2).truth.public_digest


def test_an_evaluation_without_a_digest_is_refused() -> None:
    from synthworld.search_metrics import SearchMetrics

    with pytest.raises(ValidationError, match="must name the projection"):
        SearchEvaluation(
            seed=1,
            truth_schema_version="1.0.0",
            public_digest="",
            metrics=SearchMetrics(
                result_count=1,
                decided_count=0,
                abstained_count=1,
                decidable_count=0,
                correct_decided_count=0,
                coverage=0.0,
                false_accepts=0,
                false_rejects=0,
                unwarranted_decisions=0,
                decided_precision=None,
                decided_recall=None,
                accepted_results=0,
                distinct_findings=0,
                stale_accepted=0,
            ),
        )


def test_submissions_must_cover_the_projection_exactly() -> None:
    projection = _projection()
    complete = [
        ResultJudgement(result_id=item.result_id, decision=ResultDecision.REJECT)
        for item in projection.truth.results
    ]

    with pytest.raises(SearchEvaluationError, match="exactly"):
        evaluate_search_judgements(complete[:-1], truth=projection.truth)
    with pytest.raises(SearchEvaluationError, match="twice"):
        evaluate_search_judgements([*complete, complete[0]], truth=projection.truth)


@pytest.mark.parametrize(("name", "policy"), SEARCH_BASELINES)
@pytest.mark.parametrize("seed", _SEEDS)
def test_no_baseline_scores_the_projection_cleanly(
    name: str, policy: Policy, seed: int
) -> None:
    """Every shortcut must fail somewhere, on every seed."""

    metrics = run_search_baseline(policy, projection=_projection(seed)).metrics
    wrong = (
        metrics.false_accepts + metrics.false_rejects + metrics.unwarranted_decisions
    )

    assert wrong > 0, f"{name} scored projection {seed} cleanly"


def test_difficulty_is_reported_with_the_support_its_rate_needs() -> None:
    """Which cases a system fails matters more than how many - so counts need a base.

    Reporting errors alone inverts the ranking. The accept-everything baseline makes
    more errors at difficulty 1 than at difficulty 3 purely because tier 1 is larger,
    while tier 3 is where it fails completely.
    """

    projection = _projection()
    metrics = run_search_baseline(exact_name_in_title, projection=projection).metrics
    support = Counter(item.difficulty for item in projection.truth.results)

    assert metrics.by_difficulty
    assert sum(item.errors for item in metrics.by_difficulty) == (
        metrics.false_accepts + metrics.false_rejects + metrics.unwarranted_decisions
    )
    # Every tier the projection contains, not only the ones with errors.
    assert tuple(item.difficulty for item in metrics.by_difficulty) == tuple(
        sorted(support)
    )
    assert all(
        item.support == support[item.difficulty] for item in metrics.by_difficulty
    )
    assert all(item.errors <= item.support for item in metrics.by_difficulty)
