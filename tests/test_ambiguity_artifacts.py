"""Frozen artifacts, seed variants, and the cluster view of a pair submission."""

from __future__ import annotations

import hashlib
from collections import Counter
from importlib.resources import files

import pytest

from synthworld.ambiguity import PairDisposition, PairPrediction, ScenarioKind
from synthworld.ambiguity_baselines import (
    AMBIGUITY_BASELINE_SEED,
    AMBIGUITY_BASELINES,
    exact_strong_identifier,
    precision_first,
    run_ambiguity_baseline,
)
from synthworld.ambiguity_generator import generate_ambiguity_benchmark
from synthworld.ambiguity_metrics import evaluate_ambiguity_predictions
from synthworld.ambiguity_serialization import (
    AmbiguityIntegrityError,
    ambiguity_artifacts,
    ambiguity_manifest,
    load_golden_ambiguity_benchmark,
)
from synthworld.ambiguity_variants import (
    FIXED_REALIZATION,
    REALIZATIONS,
    generate_ambiguity_variant,
)

_VARIANT_SEEDS = (1, 2, 3)


def test_the_frozen_artifacts_match_regeneration() -> None:
    canonical = generate_ambiguity_benchmark(seed=AMBIGUITY_BASELINE_SEED)
    directory = files("synthworld.benchmarks")

    for name, content in ambiguity_artifacts(canonical).items():
        assert directory.joinpath(name).read_bytes() == content


def test_the_manifest_covers_every_artifact() -> None:
    canonical = generate_ambiguity_benchmark(seed=AMBIGUITY_BASELINE_SEED)
    artifacts = ambiguity_artifacts(canonical)
    manifest = (
        files("synthworld.benchmarks")
        .joinpath("AMBIGUITY_SHA256SUMS")
        .read_text(encoding="utf-8")
    )

    assert manifest == ambiguity_manifest(artifacts)
    for name, content in artifacts.items():
        assert hashlib.sha256(content).hexdigest() in manifest
        assert name in manifest


def test_the_two_truths_are_in_different_files() -> None:
    """Separation of access, not merely of fields.

    A consumer holding the public corpus must be able to do so without either
    truth; one scoring clusters needs memberships and not dispositions. In one file
    that is discipline, in three it is access.
    """

    artifacts = ambiguity_artifacts(
        generate_ambiguity_benchmark(seed=AMBIGUITY_BASELINE_SEED)
    )
    public = artifacts["ambiguity-public-v1.json"].decode()
    memberships = artifacts["ambiguity-memberships-v1.json"].decode()
    dispositions = artifacts["ambiguity-dispositions-v1.json"].decode()

    assert "entity_id" not in public
    assert "disposition" not in public
    assert "disposition" not in memberships
    assert "entity_id" not in dispositions


def test_the_loader_verifies_before_recombining() -> None:
    assert load_golden_ambiguity_benchmark() == generate_ambiguity_benchmark(
        seed=AMBIGUITY_BASELINE_SEED
    )


def test_a_tampered_artifact_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from synthworld import ambiguity_serialization as module

    real = files("synthworld.benchmarks")

    class _Tampered:
        def joinpath(self, name: str) -> object:
            if name == "AMBIGUITY_SHA256SUMS":
                return real.joinpath(name)
            return self

        def read_bytes(self) -> bytes:
            return b"{}"

    monkeypatch.setattr(module, "files", lambda _package: _Tampered())

    with pytest.raises(AmbiguityIntegrityError, match="checksum differs"):
        module.load_golden_ambiguity_benchmark()


def test_an_incomplete_manifest_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from synthworld import ambiguity_serialization as module

    class _Short:
        def joinpath(self, name: str) -> object:
            return self

        def read_text(self, encoding: str) -> str:
            return "abc  ambiguity-public-v1.json\n"

    monkeypatch.setattr(module, "files", lambda _package: _Short())

    with pytest.raises(AmbiguityIntegrityError, match="manifest is incomplete"):
        module.load_golden_ambiguity_benchmark()


_SWEEP = range(100)


def test_every_seed_in_a_documented_sweep_generates() -> None:
    """Generation must not fail on a seed a consumer might reasonably pick.

    Forty of the first hundred seeds raised: a realization could remove a record's
    only attribute and leave it invalid. Found by an external review running the
    sweep, not by three hand-picked seeds.
    """

    failures = []
    for seed in _SWEEP:
        try:
            generate_ambiguity_variant(seed=seed)
        except Exception as error:
            failures.append((seed, type(error).__name__))

    assert failures == []


def test_merge_pairs_keep_the_evidence_that_makes_them_merges() -> None:
    """The invariant a prevalence check cannot see, swept over 100 seeds.

    Substitution keyed the replacement on the record's ordinal as well as the value,
    so two records sharing a value received different replacements and every merge
    pair lost its shared attribute. The declared prevalence was untouched, because
    the answer key is copied from the canonical drafts and survives any corruption
    of the data beneath it - so the test that existed passed on corrupt worlds.
    """

    for seed in _SWEEP:
        variant = generate_ambiguity_variant(seed=seed)
        records = {item.id: item for item in variant.public.corpus.identity_records}
        for pair in variant.answer_key.pairs:
            if pair.disposition is not PairDisposition.MERGE:
                continue
            left = {
                (item.kind, item.value)
                for item in records[pair.left_record_id].attributes
            }
            right = {
                (item.kind, item.value)
                for item in records[pair.right_record_id].attributes
            }
            assert left & right, (
                f"seed {seed}: {pair.scenario.value} declares a merge but its "
                "records share no attribute"
            )


def test_no_variant_record_is_left_empty() -> None:
    for seed in _SWEEP:
        for record in generate_ambiguity_variant(
            seed=seed
        ).public.corpus.identity_records:
            assert record.attributes


def test_the_generator_refuses_a_variant_whose_evidence_did_not_survive() -> None:
    """Structural, so the defect cannot return quietly.

    Corrupting the substitution reintroduces exactly the original bug, and
    generation must refuse rather than emit a world asserting a disposition its
    data no longer supports.
    """

    from itertools import count

    from synthworld import ambiguity_variants as module

    # Position-dependent substitution: the original defect exactly. Two records
    # sharing a value must receive the *same* replacement, so a counter breaks the
    # property while leaving every value individually plausible.
    counter = count()
    original = module._substituted
    try:
        module._substituted = lambda value, kind, seed: f"{value}-{next(counter)}"
        with pytest.raises(module.AmbiguityVariantError, match="share no attribute"):
            module.generate_ambiguity_variant(seed=1)
    finally:
        module._substituted = original


@pytest.mark.parametrize("seed", _VARIANT_SEEDS)
def test_variants_preserve_declared_prevalence(seed: int) -> None:
    canonical = Counter(
        item.disposition
        for item in generate_ambiguity_benchmark(
            seed=AMBIGUITY_BASELINE_SEED
        ).answer_key.pairs
    )
    variant = Counter(
        item.disposition
        for item in generate_ambiguity_variant(seed=seed).answer_key.pairs
    )

    assert variant == canonical


def test_variants_change_structure_not_only_identifiers() -> None:
    """The defect issue #43 documented: byte inequality is not enough.

    The fingerprint is the multiset of attribute-kind sets per record, so it is
    blind to values and moves only when a scenario is realized differently.
    """

    def fingerprint(seed: int) -> tuple[tuple[str, ...], ...]:
        world = generate_ambiguity_variant(seed=seed)
        return tuple(
            sorted(
                tuple(sorted(item.kind.value for item in record.attributes))
                for record in world.public.corpus.identity_records
            )
        )

    assert len({fingerprint(seed) for seed in _VARIANT_SEEDS}) == len(_VARIANT_SEEDS)


def test_every_scenario_still_appears_in_every_variant() -> None:
    for seed in _VARIANT_SEEDS:
        scenarios = {
            item.scenario
            for item in generate_ambiguity_variant(seed=seed).answer_key.pairs
        }
        assert scenarios == set(ScenarioKind)


def test_the_realization_split_covers_every_scenario() -> None:
    """Each scenario either names its own attribute or offers choices, never both.

    Stated as a partition so a scenario added later cannot be silently omitted from
    variation without someone deciding which side it belongs on.
    """

    assert FIXED_REALIZATION | set(REALIZATIONS) == set(ScenarioKind)
    assert not FIXED_REALIZATION & set(REALIZATIONS)


@pytest.mark.parametrize("seed", _VARIANT_SEEDS)
def test_variants_remain_adversarial(seed: int) -> None:
    variant = generate_ambiguity_variant(seed=seed)
    records = {item.id: item for item in variant.public.corpus.identity_records}

    for name, decide in AMBIGUITY_BASELINES:
        metrics = evaluate_ambiguity_predictions(
            [
                PairPrediction(
                    left_record_id=pair.left_record_id,
                    right_record_id=pair.right_record_id,
                    disposition=decide(
                        records[pair.left_record_id], records[pair.right_record_id]
                    ),
                )
                for pair in variant.answer_key.pairs
            ],
            benchmark=variant,
        )
        wrong = (
            metrics.false_merges + metrics.false_splits + metrics.unwarranted_decisions
        )
        assert wrong > 0, f"{name} resolved variant {seed}"


def test_pairwise_and_b_cubed_disagree_and_both_are_reported() -> None:
    """Issue #41 asks for both, and the reason is that they weight differently.

    Pairwise weights a large cluster quadratically; B-cubed averages per record. A
    report showing only one hides whichever failure the other would surface.
    """

    metrics = run_ambiguity_baseline(exact_strong_identifier)
    clusters = metrics.clusters

    assert clusters.pairwise_f1 is not None
    assert clusters.pairwise_f1 < clusters.b_cubed_f1


def test_merge_decisions_are_treated_as_transitive() -> None:
    """Deciding a~b and b~c asserts a~c whether or not a system means it to.

    Scoring pairs independently would let a submission that merges everything look
    locally consistent while producing one cluster.
    """

    benchmark = generate_ambiguity_benchmark(seed=AMBIGUITY_BASELINE_SEED)
    metrics = evaluate_ambiguity_predictions(
        [
            PairPrediction(
                left_record_id=pair.left_record_id,
                right_record_id=pair.right_record_id,
                disposition=PairDisposition.MERGE,
            )
            for pair in benchmark.answer_key.pairs
        ],
        benchmark=benchmark,
    )

    # Merging every pair collapses each pair into one cluster, so precision falls
    # while recall cannot: every true co-membership survives.
    assert metrics.clusters.b_cubed_recall == 1.0
    assert metrics.clusters.b_cubed_precision < 1.0


def test_abstaining_leaves_every_record_in_its_own_cluster() -> None:
    metrics = run_ambiguity_baseline(lambda _left, _right: PairDisposition.INSUFFICIENT)

    assert metrics.clusters.b_cubed_precision == 1.0
    assert metrics.clusters.b_cubed_recall < 1.0
    assert metrics.clusters.pairwise_precision is None


def test_precision_first_beats_the_shortcut_on_b_cubed() -> None:
    """Abstention should pay off on the metric that averages per record."""

    assert (
        run_ambiguity_baseline(precision_first).clusters.b_cubed_f1
        > run_ambiguity_baseline(exact_strong_identifier).clusters.b_cubed_f1
    )


def test_an_unknown_attribute_kind_passes_through_substitution() -> None:
    """Variants must not silently drop a kind they were not taught to rewrite.

    The pack uses no `social_profile` attribute today, so this path is unreachable
    through the generator. Passing the value through unchanged is still the right
    behaviour, and pinning it means a kind added later degrades visibly rather than
    vanishing from a variant.
    """

    from synthworld.ambiguity_variants import _substituted

    assert (
        _substituted("https://social.example.test/x", "social_profile", 1)
        == "https://social.example.test/x"
    )


def test_induced_clusters_close_over_transitive_merges() -> None:
    """a~b and b~c must yield one cluster, not two overlapping pairs.

    The canonical pack's pairs are disjoint, so the generator never exercises this.
    A pack whose pairs share records would, and a union that failed to close would
    report a contradictory submission as consistent.
    """

    from uuid import UUID

    from synthworld.ambiguity_metrics import _induced_clusters

    records = [UUID(int=index) for index in (1, 2, 3, 4)]
    clusters = _induced_clusters(
        records,
        [(records[0], records[1]), (records[1], records[2]), (records[0], records[2])],
    )

    assert clusters[records[0]] == frozenset(records[:3])
    assert clusters[records[3]] == frozenset({records[3]})
