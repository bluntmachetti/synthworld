"""What the computed floor has to prove: the number, the gates, and the digest.

The floor is the Bayes error of the shipped generator - the accuracy of a genie
holding the public law, the observed comparable structure and the true prevalence.
This module pins it three ways: the machinery is correct on controlled pairs, the
estimate replays deterministically at toy scale through the same code path the
publication uses, and the published numbers satisfy the gates of issue #80 under a
digest that binds them to every decision-relevant constant.
"""

from __future__ import annotations

from typing import cast

import pytest

from synthworld.ambiguity import PairDisposition
from synthworld.ambiguity_evidence import EvidenceKind as K
from synthworld.ambiguity_floor import (
    FLOOR_BAND,
    FLOOR_PUBLICATION,
    MINIMUM_PREMIUM,
    KindObservation,
    PairObservation,
    _vectors_for,
    decide_pair,
    decision_inputs,
    estimate_floor,
    evaluate_gates,
    floor_digest,
    observe_pair,
    pack_prevalence,
    wilson_interval,
)
from synthworld.ambiguity_grammar import relation_vectors
from synthworld.ambiguity_v2_generator import (
    generate_ambiguity_v2_pack,
    prevalence_of,
)

_KEY = b"floor-suite-key"


def test_relation_vectors_enumerate_the_latent_space() -> None:
    """Every vector appears once, weighted, with the rule's own disposition."""

    kinds = (K.EMAIL, K.PHONE)
    vectors = list(relation_vectors(kinds))
    assert len(vectors) == 3 ** len(kinds)
    seen = {relations for relations, _, _, _ in vectors}
    assert len(seen) == len(vectors)
    for _relations, disposition, m_weight, u_weight in vectors:
        assert disposition in set(PairDisposition)
        assert m_weight > 0.0 and u_weight > 0.0


def test_vectors_are_cached_per_kind_set() -> None:
    kinds = (K.EMAIL,)
    assert _vectors_for(kinds) is _vectors_for(kinds)


def test_wilson_interval_bounds_a_proportion() -> None:
    low, high = wilson_interval(50, 100)
    assert 0.0 <= low <= 0.5 <= high <= 1.0
    degenerate_low, degenerate_high = wilson_interval(0, 0)
    assert (degenerate_low, degenerate_high) == (0.0, 1.0)


def test_observe_pair_reduces_a_public_pair_to_cores() -> None:
    """The observation is read only off the public records, forms inverted."""

    task, truths = generate_ambiguity_v2_pack(seed=11, key=_KEY)
    by_id = {record.id: record for record in task.corpus.identity_records}
    observed = 0
    for truth in truths:
        observation = observe_pair(
            by_id[truth.left_record_id], by_id[truth.right_record_id]
        )
        observed += 1
        assert observation.kinds
        assert len(observation.per_kind) == len(observation.kinds)
    assert observed


def test_decide_pair_refuses_an_impossible_observation() -> None:
    """An observation the channel cannot emit has zero posterior everywhere, and the
    machinery surfaces that loudly instead of dividing by it."""

    task, truths = generate_ambiguity_v2_pack(seed=13, key=_KEY)
    del task
    impossible = PairObservation(
        kinds=(K.EMAIL,),
        per_kind=(
            KindObservation(
                left_core="not-a-core-the-pool-can-emit",
                right_core="not-a-core-the-pool-can-emit",
                left_form=0,
                right_form=0,
                rendered_equal=True,
            ),
        ),
    )
    with pytest.raises(ValueError, match="impossible under the modelled law"):
        decide_pair(impossible, truths[0], 0.5)


def test_decide_pair_returns_a_decision_for_every_class() -> None:
    task, truths = generate_ambiguity_v2_pack(seed=12, key=_KEY)
    prevalence = pack_prevalence(12, _KEY)
    by_id = {record.id: record for record in task.corpus.identity_records}
    truth = truths[0]
    observation = observe_pair(
        by_id[truth.left_record_id], by_id[truth.right_record_id]
    )
    decision = decide_pair(observation, truth, prevalence)
    for decided in (decision.genie, decision.c0, decision.c1, decision.premium):
        assert decided in set(PairDisposition)
    assert 0.0 <= decision.genie_confidence <= 1.0


def test_pack_prevalence_is_a_rate_in_range() -> None:
    for seed in range(3):
        prevalence = pack_prevalence(seed, _KEY)
        assert 0.0 < prevalence < 1.0
        _, truths = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        realized = prevalence_of(truths)
        assert abs(realized - prevalence) < 0.2


def test_estimate_floor_replays_and_is_bounded() -> None:
    """The same code path as the publication, at toy scale, replays exactly."""

    first = estimate_floor(seed_start=100, seed_count=2, key=_KEY)
    again = estimate_floor(seed_start=100, seed_count=2, key=_KEY)
    assert first == again
    assert 0.0 <= first.floor <= 1.0
    assert first.pair_count > 0
    assert first.genie_correct <= first.pair_count


def test_estimate_floor_classes_are_consistent() -> None:
    estimate = estimate_floor(seed_start=200, seed_count=2, key=_KEY)
    for name in ("genie", "c0", "c1", "premium"):
        assert 0.0 <= estimate.accuracy(name) <= 1.0
    gates = evaluate_gates(estimate)
    assert 0.0 <= gates.floor <= 1.0
    assert gates.delta >= 0.05


def test_decision_inputs_are_deterministic_and_sensitive() -> None:
    first = decision_inputs()
    again = decision_inputs()
    assert first == again
    assert floor_digest() == floor_digest()
    # Perturbing any decision-relevant input must move the digest, or the floor
    # could silently survive the change that invalidates it.
    perturbed = dict(first)
    perturbed["merge_bits"] = cast(float, first["merge_bits"]) + 0.5
    from synthworld.ambiguity_channel import decision_digest

    assert decision_digest(perturbed) != floor_digest()


def test_the_published_floor_satisfies_the_gates() -> None:
    """The standing gate of issue #80, read off the publication.

    The floor sits in the credible band, the technique premium clears its minimum,
    and the digest binds the numbers to the constants they were computed under. If a
    decision-relevant constant moves, the digest check fails until the floor is
    recomputed - loudly, not silently.
    """

    assert FLOOR_BAND[0] <= FLOOR_PUBLICATION.floor <= FLOOR_BAND[1]
    assert FLOOR_PUBLICATION.technique_premium >= MINIMUM_PREMIUM
    assert FLOOR_PUBLICATION.genie_ceiling == pytest.approx(
        1.0 - FLOOR_PUBLICATION.floor, abs=1e-6
    )
    assert FLOOR_PUBLICATION.digest == floor_digest()
    assert FLOOR_PUBLICATION.pair_count > 0
    assert FLOOR_PUBLICATION.floor_half_width > 0.0


def test_the_genie_achieves_its_ceiling_end_to_end() -> None:
    """The achievability witness: a solver holding only the public artifact, the
    published law and the prevalence reaches the ceiling on a held-out seed.

    The genie reads nothing but the rendered values and the pack's prevalence; it is
    handed no truth. Its accuracy on held-out seeds must sit near ``1 - floor``, or
    the published ceiling is not achievable and the claim comes out of the docs.
    """

    correct = total = 0
    for seed in range(900, 903):
        task, truths = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        prevalence = pack_prevalence(seed, _KEY)
        by_id = {record.id: record for record in task.corpus.identity_records}
        for truth in truths:
            observation = observe_pair(
                by_id[truth.left_record_id], by_id[truth.right_record_id]
            )
            decision = decide_pair(observation, truth, prevalence)
            total += 1
            correct += decision.genie is decision.truth
    accuracy = correct / total
    assert accuracy == pytest.approx(FLOOR_PUBLICATION.genie_ceiling, abs=0.05)
