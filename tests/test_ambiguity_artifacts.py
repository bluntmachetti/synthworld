"""Frozen artifacts, seed variants, and the cluster view of a pair submission."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections import Counter, defaultdict
from importlib.resources import files
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.ambiguity import (
    AmbiguityBenchmark,
    PairDisposition,
    PairPrediction,
    ScenarioKind,
)
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
    AmbiguityVariantError,
    ambiguity_variant_metadata,
    generate_ambiguity_variant,
    validate_ambiguity_variant,
)
from synthworld.connection import (
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
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


def _scenario_records(
    benchmark: AmbiguityBenchmark, scenario: ScenarioKind
) -> tuple[PublicIdentityRecord, PublicIdentityRecord]:
    pair = next(
        item for item in benchmark.answer_key.pairs if item.scenario is scenario
    )
    records = {item.id: item for item in benchmark.public.corpus.identity_records}
    return records[pair.left_record_id], records[pair.right_record_id]


def _replace_records(
    benchmark: AmbiguityBenchmark, *replacements: PublicIdentityRecord
) -> AmbiguityBenchmark:
    by_id = {item.id: item for item in replacements}
    records = tuple(
        by_id.get(item.id, item) for item in benchmark.public.corpus.identity_records
    )
    corpus = benchmark.public.corpus.model_copy(update={"identity_records": records})
    public = benchmark.public.model_copy(update={"corpus": corpus})
    return benchmark.model_copy(update={"public": public})


def _replace_attribute_value(
    record: PublicIdentityRecord,
    kind: PublicIdentityAttributeKind,
    value: str,
) -> PublicIdentityRecord:
    found = any(item.kind is kind for item in record.attributes)
    assert found
    attributes = tuple(
        item.model_copy(update={"value": value}) if item.kind is kind else item
        for item in record.attributes
    )
    return record.model_copy(update={"attributes": attributes})


def _replace_attribute_kind(
    record: PublicIdentityRecord,
    old: PublicIdentityAttributeKind,
    new: PublicIdentityAttributeKind,
) -> PublicIdentityRecord:
    found = any(item.kind is old for item in record.attributes)
    assert found
    attributes = tuple(
        item.model_copy(update={"kind": new}) if item.kind is old else item
        for item in record.attributes
    )
    return record.model_copy(update={"attributes": attributes})


def _values(record: PublicIdentityRecord) -> dict[PublicIdentityAttributeKind, str]:
    return {item.kind: item.value for item in record.attributes}


def test_every_seed_in_a_documented_sweep_generates() -> None:
    """Seeds 0..99 are the declared correlated robustness sweep, not 100 samples."""

    for seed in _SWEEP:
        benchmark = generate_ambiguity_variant(seed=seed)
        validate_ambiguity_variant(benchmark)


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


def test_no_value_or_display_name_collides_across_scenarios() -> None:
    for seed in _SWEEP:
        benchmark = generate_ambiguity_variant(seed=seed)
        records = {item.id: item for item in benchmark.public.corpus.identity_records}
        attribute_origins: dict[
            tuple[PublicIdentityAttributeKind, str], set[ScenarioKind]
        ] = defaultdict(set)
        display_origins: dict[str, set[ScenarioKind]] = defaultdict(set)
        for pair in benchmark.answer_key.pairs:
            for record_id in (pair.left_record_id, pair.right_record_id):
                record = records[record_id]
                display_origins[record.display_name.casefold()].add(pair.scenario)
                for attribute in record.attributes:
                    attribute_origins[(attribute.kind, attribute.value)].add(
                        pair.scenario
                    )

        assert all(len(origins) == 1 for origins in attribute_origins.values())
        assert all(len(origins) == 1 for origins in display_origins.values())


@pytest.mark.parametrize("scenario", tuple(ScenarioKind))
def test_each_scenario_rejects_position_dependent_shared_values(
    scenario: ScenarioKind,
) -> None:
    """Splitting any planned equality simulates the original ordinal-key defect."""

    benchmark = generate_ambiguity_variant(seed=42)
    left, right = _scenario_records(benchmark, scenario)
    left_values = _values(left)
    right_values = _values(right)
    shared = sorted(
        (kind for kind in left_values if left_values[kind] == right_values[kind]),
        key=lambda kind: kind.value,
    )
    assert shared
    replacement = _replace_attribute_value(
        right, shared[0], f"{right_values[shared[0]]}-position-dependent"
    )

    with pytest.raises(AmbiguityVariantError, match="public evidence"):
        validate_ambiguity_variant(_replace_records(benchmark, replacement))


@pytest.mark.parametrize("scenario", tuple(ScenarioKind))
def test_each_scenario_rejects_a_display_name_semantic_mutation(
    scenario: ScenarioKind,
) -> None:
    """Every named scenario has a discriminating display-name predicate."""

    benchmark = generate_ambiguity_variant(seed=42)
    left, right = _scenario_records(benchmark, scenario)
    replacement_name = (
        "Corrupt ExampleName"
        if left.display_name.casefold() == right.display_name.casefold()
        else left.display_name
    )
    replacement = right.model_copy(update={"display_name": replacement_name})

    with pytest.raises(
        AmbiguityVariantError,
        match=rf"{scenario.value} display-name relationship",
    ):
        validate_ambiguity_variant(_replace_records(benchmark, replacement))


def test_a_distinct_value_collision_is_rejected() -> None:
    benchmark = generate_ambiguity_variant(seed=42)
    left, right = _scenario_records(benchmark, ScenarioKind.RECYCLED_PHONE)
    replacement = _replace_attribute_value(
        right,
        PublicIdentityAttributeKind.EMAIL,
        _values(left)[PublicIdentityAttributeKind.EMAIL],
    )

    with pytest.raises(AmbiguityVariantError, match="public evidence"):
        validate_ambiguity_variant(_replace_records(benchmark, replacement))


def test_a_missing_selected_realization_is_rejected() -> None:
    """Seed 42 selects school_year; restoring employer must not pass silently."""

    benchmark = generate_ambiguity_variant(seed=42)
    metadata = ambiguity_variant_metadata(seed=42)
    selected = {
        item.scenario: item.attribute_kind for item in metadata.selected_realizations
    }
    scenario = ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE
    assert selected[scenario] is PublicIdentityAttributeKind.SCHOOL_YEAR
    left, right = _scenario_records(benchmark, scenario)
    replacements = tuple(
        _replace_attribute_kind(
            record,
            PublicIdentityAttributeKind.SCHOOL_YEAR,
            PublicIdentityAttributeKind.EMPLOYER,
        )
        for record in (left, right)
    )

    with pytest.raises(AmbiguityVariantError, match="wrong attribute"):
        validate_ambiguity_variant(
            _replace_records(benchmark, *replacements), metadata=metadata
        )


def test_lost_unicode_evidence_is_rejected() -> None:
    benchmark = generate_ambiguity_variant(seed=42)
    left, right = _scenario_records(benchmark, ScenarioKind.UNICODE_VARIANT)
    replacements = (
        left.model_copy(update={"display_name": "Zoe Dvorak"}),
        right.model_copy(update={"display_name": "Zoe Dvorak"}),
    )

    with pytest.raises(AmbiguityVariantError, match="unicode_variant display-name"):
        validate_ambiguity_variant(_replace_records(benchmark, *replacements))


def test_unrelated_unicode_family_values_are_rejected() -> None:
    benchmark = generate_ambiguity_variant(seed=42)
    _, right = _scenario_records(benchmark, ScenarioKind.UNICODE_VARIANT)
    replacement = _replace_attribute_value(
        right, PublicIdentityAttributeKind.FAMILY_NAME, "UnrelatedSurname"
    )

    with pytest.raises(AmbiguityVariantError, match="family evidence"):
        validate_ambiguity_variant(_replace_records(benchmark, replacement))


def test_an_accidental_cross_scenario_match_is_rejected() -> None:
    benchmark = generate_ambiguity_variant(seed=42)
    recycled, _ = _scenario_records(benchmark, ScenarioKind.RECYCLED_PHONE)
    duplicate_left, duplicate_right = _scenario_records(
        benchmark, ScenarioKind.DUPLICATE_OBSERVATION
    )
    # Case differences are not a meaningful escape from a cross-scenario email
    # collision, so the validator compares a canonical collision key.
    recycled_email = _values(recycled)[PublicIdentityAttributeKind.EMAIL].upper()
    replacements = tuple(
        _replace_attribute_value(
            record, PublicIdentityAttributeKind.EMAIL, recycled_email
        )
        for record in (duplicate_left, duplicate_right)
    )

    with pytest.raises(AmbiguityVariantError, match="collides across scenarios"):
        validate_ambiguity_variant(_replace_records(benchmark, *replacements))


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

    # The exact population is the declared 0..99 sweep. It need only contain more
    # than one semantic structure; correlated variants are not independent samples.
    assert len({fingerprint(seed) for seed in _SWEEP}) > 1


def test_the_declared_sweep_exercises_every_supported_realization() -> None:
    seen: dict[ScenarioKind, set[PublicIdentityAttributeKind]] = defaultdict(set)
    for seed in _SWEEP:
        for item in ambiguity_variant_metadata(seed=seed).selected_realizations:
            seen[item.scenario].add(item.attribute_kind)

    assert all(len(choices) > 1 for choices in REALIZATIONS.values())
    assert seen == {
        scenario: set(choices) for scenario, choices in REALIZATIONS.items()
    }


def test_selected_realizations_are_constructed_in_both_records() -> None:
    different = {
        ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS,
        ScenarioKind.STALE_ATTRIBUTE,
        ScenarioKind.PARTIAL_WITH_CONTRADICTION,
    }
    for seed in _SWEEP:
        benchmark = generate_ambiguity_variant(seed=seed)
        for item in ambiguity_variant_metadata(seed=seed).selected_realizations:
            left, right = _scenario_records(benchmark, item.scenario)
            left_values = _values(left)
            right_values = _values(right)
            assert item.attribute_kind in left_values
            assert item.attribute_kind in right_values
            assert (
                left_values[item.attribute_kind] != right_values[item.attribute_kind]
            ) is (item.scenario in different)


def _positional_scenarios(benchmark: AmbiguityBenchmark) -> tuple[ScenarioKind, ...]:
    """Each public pair's true scenario, in the order the public task lists them."""

    truth = {
        (item.left_record_id, item.right_record_id): item
        for item in benchmark.answer_key.pairs
    }
    return tuple(
        truth[(item.left_record_id, item.right_record_id)].scenario
        for item in benchmark.public.pairs_to_decide
    )


def test_the_position_of_a_public_pair_is_not_an_answer_key() -> None:
    """The channel no attribute-level check could see, because it is not in the data.

    Both generators built `pairs_to_decide` by walking their drafts, and the drafts
    are in `ScenarioKind` declaration order. So `pairs_to_decide[i]` was
    `list(ScenarioKind)[i]` - measured 15/15 on the frozen pack and 750/750 across
    fifty variant seeds, which decodes every disposition through the public
    `SCENARIO_DISPOSITIONS` map without reading a single attribute. The pack shipped
    that way, and `b"scenario" not in public_bytes` passed the whole time.
    """

    kinds = list(ScenarioKind)
    canonical = _positional_scenarios(load_golden_ambiguity_benchmark())

    assert canonical != tuple(kinds)

    # Across seeds the map from position to scenario must actually move. A generator
    # that sorted by some other fixed key would satisfy the assertion above while
    # still handing out one decoder that works on every seed.
    observed = [
        _positional_scenarios(generate_ambiguity_variant(seed=seed))
        for seed in range(12)
    ]
    hits = sum(
        1
        for order in observed
        for index, scenario in enumerate(order)
        if scenario is kinds[index]
    )
    positions = len(observed) * len(kinds)

    assert len(set(observed)) == len(observed)
    # A fixed order scores `positions`; chance is `positions / len(kinds)`. The bound
    # is loose on purpose - the point is to separate "no channel" from "a channel",
    # not to assert an exact coincidence count.
    assert hits < positions // 4


def test_an_unsorted_public_pair_list_is_refused_rather_than_sorted() -> None:
    """Closing the channel in the model, so no future generator can reopen it."""

    task = load_golden_ambiguity_benchmark().public
    reversed_pairs = tuple(reversed(task.pairs_to_decide))

    with pytest.raises(ValidationError, match="canonical record-id order"):
        task.__class__(corpus=task.corpus, pairs_to_decide=reversed_pairs)


def test_variant_metadata_is_evaluator_only() -> None:
    benchmark = generate_ambiguity_variant(seed=42)
    public_bytes = ambiguity_artifacts(benchmark)["ambiguity-public-v1.json"]
    metadata = ambiguity_variant_metadata(seed=42)

    assert metadata.synthetic is True
    assert metadata.selected_realizations
    assert b"selected_realizations" not in public_bytes
    assert b"scenario" not in public_bytes


@pytest.mark.parametrize("seed", (0, 42, 99))
def test_same_seed_variants_serialize_byte_identically(seed: int) -> None:
    first = generate_ambiguity_variant(seed=seed)
    second = generate_ambiguity_variant(seed=seed)

    assert ambiguity_artifacts(first) == ambiguity_artifacts(second)
    assert ambiguity_variant_metadata(seed=seed) == ambiguity_variant_metadata(
        seed=seed
    )


def test_variant_bytes_do_not_depend_on_python_hash_iteration() -> None:
    project_root = Path(__file__).parents[1]
    command = (
        "import hashlib; "
        "from synthworld.ambiguity_serialization import ambiguity_artifacts; "
        "from synthworld.ambiguity_variants import generate_ambiguity_variant; "
        "artifacts=ambiguity_artifacts(generate_ambiguity_variant(seed=42)); "
        "print(hashlib.sha256(b''.join(artifacts[name] for name in "
        "sorted(artifacts))).hexdigest())"
    )
    outputs = []
    for hash_seed in ("1", "8675309"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = hash_seed
        result = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
            [sys.executable, "-c", command],
            cwd=project_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(result.stdout)

    assert len(set(outputs)) == 1


def test_seed_42_realization_regression() -> None:
    assert tuple(
        (item.scenario.value, item.attribute_kind.value)
        for item in ambiguity_variant_metadata(seed=42).selected_realizations
    ) == (
        ("contradictory_strong_identifiers", "email"),
        ("partial_but_sufficient", "date_of_birth"),
        ("partial_with_contradiction", "school_year"),
        ("single_uncorroborated_attribute", "school_year"),
        ("stale_attribute", "full_address"),
    )


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
        _substituted("https://social.example.test/x", "social_profile", 1, 0)
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
