"""What the ambiguity channel has to prove, enumerated rather than sampled.

Issue #80 closes with a list of invariants that are *suprema over classes* and
*exact law checks*, not attacker scores. This module asserts them on the shipped
channel: the noise law is a distribution, the FAR kernel is stationary, the
one-value marginal is identical under every relation, sibling-landing mass clears
the gate per base, and the forms keep their three promises - bijectivity,
form-independence of distance, and a constant cross-form distance. Where a promise
is distributional (NEAR nearer than FAR, FAR sometimes byte-equal) it is asserted
distributionally, because the point of #80 is that the old byte-equality guarantees
were exactly what leaked.
"""

from __future__ import annotations

import pytest

from synthworld.ambiguity_channel import (
    CHANNEL,
    _applications,
    _editable_positions,
    base_outcomes,
    capped_distance,
    core_distance,
    distance_law,
    distance_probability,
    emission_index,
    emitters_of,
    far_outcomes,
    form_defect,
    likelihood_of,
    mass_breakdown,
    min_sibling_mass,
    noise_outcomes,
    noise_support,
    render_relation,
    render_value,
    same_core_probability,
    side_two_total_variation,
    single_value_defect,
    stationarity_defect,
    validate_operations,
)
from synthworld.ambiguity_evidence import EvidenceKind as K
from synthworld.ambiguity_evidence import Relation
from synthworld.ambiguity_surfaces import (
    KindSurface,
    base_probability,
    bases,
    cluster_of,
    invert_form,
    render_form,
    siblings_of,
    surface_of,
)

_KEY = b"channel-test-key"
_KINDS = tuple(sorted(K))


@pytest.mark.parametrize("kind", _KINDS)
def test_the_noise_law_is_a_distribution(kind: K) -> None:
    """Every base's noise outcomes sum to one: it is a law, not a menu."""

    for base in bases(kind):
        total = sum(mass for _, mass in noise_outcomes(kind, base))
        assert total == pytest.approx(1.0), (kind.value, base)


@pytest.mark.parametrize("kind", _KINDS)
def test_the_base_law_is_a_distribution(kind: K) -> None:
    total = sum(mass for _, mass in base_outcomes(kind))
    assert total == pytest.approx(1.0), kind.value


@pytest.mark.parametrize("kind", _KINDS)
def test_the_far_kernel_is_a_stochastic_map_and_stationary(kind: K) -> None:
    """Each row of the FAR kernel sums to one, and inflow reproduces ``pi``.

    Stationarity is the whole of the #84 fix one level down: if the kernel leaked,
    a single right-hand value would classify NEAR against FAR, and the side-two
    marginal would differ across relations. The defect is measured, not argued.
    """

    for base in bases(kind):
        row = sum(mass for _, mass in far_outcomes(kind, base))
        assert row == pytest.approx(1.0), (kind.value, base)
    assert stationarity_defect(kind) < 1e-9, kind.value


@pytest.mark.parametrize("kind", _KINDS)
def test_the_side_two_marginal_is_relation_invariant(kind: K) -> None:
    assert side_two_total_variation(kind) < 1e-9, kind.value


@pytest.mark.parametrize("kind", _KINDS)
def test_a_single_value_does_not_reveal_its_relation(kind: K) -> None:
    """The one-value marginal is identical under EQUAL, NEAR and FAR.

    This is the distribution the signature guarantee cannot see: damage applied only
    under one relation made pool membership an oracle, and the defect shows up here,
    not in a parameter list.
    """

    assert single_value_defect(kind) < 1e-9, kind.value


@pytest.mark.parametrize("kind", _KINDS)
def test_sibling_landing_mass_clears_the_gate_per_base(kind: K) -> None:
    """The gate is on the per-base minimum, not the pool average.

    A single low-``a`` base recreates the single-value leak locally while the pool
    average sails through, so the minimum is what is asserted.
    """

    assert min_sibling_mass(kind) >= CHANNEL.a_min, kind.value


@pytest.mark.parametrize("kind", _KINDS)
def test_the_mass_breakdown_partitions_the_law(kind: K) -> None:
    for base in bases(kind):
        breakdown = mass_breakdown(kind, base)
        assert set(breakdown) == {"q", "a", "sh", "pv"}
        assert sum(breakdown.values()) == pytest.approx(1.0), (kind.value, base)
        assert breakdown["q"] >= 0.0 and breakdown["a"] >= CHANNEL.a_min - 1e-9


@pytest.mark.parametrize("kind", _KINDS)
def test_the_forms_keep_their_promises(kind: K) -> None:
    """Bijectivity, form-independence and constant cross-form distance, at 0.0."""

    assert form_defect(kind) == 0.0, kind.value


@pytest.mark.parametrize("kind", _KINDS)
def test_forms_round_trip_on_every_noisy_core(kind: K) -> None:
    """Inversion is exact over the full noise support, not just clean bases."""

    surface = surface_of(kind)
    for core in noise_support(kind):
        for form in range(surface.form_count):
            rendered = render_form(kind, form, core)
            assert invert_form(kind, rendered) == (form, core), (kind.value, core, form)


def test_editable_positions_follow_the_kind_mask() -> None:
    """Edits concentrate where transcription error actually does."""

    date = "1985-03-07"
    assert all(
        date[index].isdigit() for index in _editable_positions(K.DATE_OF_BIRTH, date)
    )
    email = "jkaur@example.test"
    local = email.partition("@")[0]
    assert _editable_positions(K.EMAIL, email) == tuple(range(len(local)))
    address = "12|Example Street 100|Testville|00000|ZZ"
    assert all(
        address[index].isdigit()
        for index in _editable_positions(K.FULL_ADDRESS, address)
    )
    name = "Sorensen"
    assert _editable_positions(K.FAMILY_NAME, name) == tuple(range(len(name)))


def test_applications_cover_each_operation() -> None:
    """Each edit operation produces outcomes, and the guards behave."""

    core = "Sorensen"
    assert _applications("identity", core, K.FAMILY_NAME) == (core,)
    assert len(_applications("transpose", core, K.FAMILY_NAME)) >= 1
    assert len(_applications("delete", core, K.FAMILY_NAME)) >= 1
    assert len(_applications("double", core, K.FAMILY_NAME)) >= 1
    assert len(_applications("substitute", core, K.FAMILY_NAME)) >= 1
    assert set(_applications("variant", core, K.FAMILY_NAME)) == set(
        siblings_of(K.FAMILY_NAME, core)
    )

    # A single-character core has no deletion to offer: the guard returns empty.
    assert _applications("delete", "a", K.FAMILY_NAME) == ()

    with pytest.raises(ValueError, match="unknown operation"):
        _applications("interpolate", core, K.FAMILY_NAME)


def test_the_shipped_pool_admits_every_operation() -> None:
    """Import-time validation passes on the shipped surfaces."""

    validate_operations()


def test_a_pool_the_edit_law_cannot_act_on_is_refused() -> None:
    """The validation refuses lone clusters and dead operations.

    An empty outcome set would divide the noise law by zero, and a lone base leaves
    the variant draw nowhere to jump; both are refused at validation rather than
    skewing the law at draw time.
    """

    lone = KindSurface(
        clusters=(("Sorensen",),),
        cluster_masses=(1.0,),
        member_masses=((1.0,),),
        width=8,
        pad="*",
        alphabets=({},),
    )
    with pytest.raises(ValueError, match="too small"):
        validate_operations({K.FAMILY_NAME: lone})

    # `1-2` under the date mask edits only at the digits, which are not adjacent:
    # no transposition exists, so the pool is refused.
    dead = KindSurface(
        clusters=(("1-2", "1-3"),),
        cluster_masses=(1.0,),
        member_masses=((0.5, 0.5),),
        width=3,
        pad="*",
        alphabets=({},),
    )
    with pytest.raises(ValueError, match="admits no transpose"):
        validate_operations({K.DATE_OF_BIRTH: dead})


@pytest.mark.parametrize("kind", _KINDS)
def test_distance_law_is_a_distribution_per_relation(kind: K) -> None:
    for relation, law in distance_law(kind):
        assert sum(law) == pytest.approx(1.0), (kind.value, relation)


def test_capped_distance_reports_the_cap() -> None:
    assert capped_distance("abc", "abc") == 0
    assert capped_distance("abc", "abd") == 1
    assert capped_distance("abcdef", "zyxwvu", cap=2) == 3
    # Equal length but far beyond the cap still saturates at cap + 1.
    assert capped_distance("aaaa", "bbbb", cap=2) == 3
    assert core_distance("kitten", "sitting") == 3


@pytest.mark.parametrize("kind", _KINDS)
def test_likelihoods_agree_with_the_diagonal_identity(kind: K) -> None:
    """EQUAL's shared-draw mixture lands its sigma mass on the diagonal."""

    near_same = same_core_probability(kind, Relation.NEAR)
    equal_same = same_core_probability(kind, Relation.EQUAL)
    assert equal_same == pytest.approx(
        CHANNEL.sigma + (1.0 - CHANNEL.sigma) * near_same
    ), kind.value
    assert same_core_probability(kind, Relation.FAR) < near_same, kind.value


@pytest.mark.parametrize("kind", _KINDS)
def test_emission_index_inverts_the_noise_table(kind: K) -> None:
    index = dict(emission_index(kind))
    for base in bases(kind):
        for outcome, mass in noise_outcomes(kind, base):
            emitters = dict(index[outcome])
            assert emitters[base] == pytest.approx(mass), (kind.value, base, outcome)
    assert emitters_of(kind, "no-such-core-anywhere") == ()


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("relation", (Relation.EQUAL, Relation.NEAR, Relation.FAR))
def test_distance_probability_reads_the_law(kind: K, relation: Relation) -> None:
    law = dict(distance_law(kind))[relation]
    for bucket, mass in enumerate(law):
        assert distance_probability(kind, relation, bucket) == pytest.approx(mass)
    # Anything at or beyond the cap lands in the final bucket.
    assert distance_probability(kind, relation, 10_000) == pytest.approx(law[-1])


@pytest.mark.parametrize("kind", _KINDS)
def test_rendering_replays_and_is_keyed(kind: K) -> None:
    first = render_relation(kind, Relation.NEAR, seed=3, key=_KEY, slot=0)
    again = render_relation(kind, Relation.NEAR, seed=3, key=_KEY, slot=0)
    keyed = render_relation(kind, Relation.NEAR, seed=3, key=b"another", slot=0)
    assert first == again
    assert first != keyed


@pytest.mark.parametrize("kind", _KINDS)
def test_rendering_an_absence_is_refused(kind: K) -> None:
    with pytest.raises(ValueError, match="absence, not a comparison"):
        render_relation(kind, Relation.LOPSIDED, seed=1, key=_KEY, slot=0)


@pytest.mark.parametrize("kind", _KINDS)
def test_a_one_sided_value_follows_the_side_one_law(kind: K) -> None:
    """`render_value` draws exactly as a pair's first side does.

    The purposes are the same, so the draws are the same: checked byte-for-byte
    against a `NEAR` pair, whose first side never shares a noise draw. (`EQUAL`
    shares draws with probability ``sigma``, so its left side is the same *law* but
    not the same string.) A one-sided value cannot be told from a two-sided one,
    which is what keeps missingness from being readable off the value.
    """

    for seed in range(40):
        one_sided = render_value(kind, seed=seed, key=_KEY, slot=0)
        paired_left = render_relation(kind, Relation.NEAR, seed=seed, key=_KEY, slot=0)[
            0
        ]
        assert one_sided == paired_left, (kind.value, seed)


@pytest.mark.parametrize("kind", _KINDS)
def test_near_is_nearer_than_far_in_distribution(kind: K) -> None:
    """The replacement for the old byte guarantee, stated distributionally.

    NEAR pairs concentrate at low capped distance; FAR pairs spread toward and beyond
    the cap. The means must separate, which is the overlap the floor is computed over.
    """

    def mean_distance(relation: Relation) -> float:
        total = 0.0
        for seed in range(120):
            left, right = render_relation(
                kind, relation, seed=seed, key=_KEY, slot=seed
            )
            left_form, left_core = invert_form(kind, left)
            right_form, right_core = invert_form(kind, right)
            if left_form == right_form:
                total += capped_distance(left_core, right_core)
            else:
                total += 10  # cross-form: no graded signal, counted at the cap+1 bucket
        return total / 120

    assert mean_distance(Relation.NEAR) < mean_distance(Relation.FAR), kind.value


@pytest.mark.parametrize("kind", _KINDS)
def test_far_can_render_two_equal_values(kind: K) -> None:
    """The old invariant, retired: FAR same-base redraws make byte-equality possible.

    Two different people can share a name, so a FAR pair may render identically; the
    guarantee that used to forbid it was what made pool membership an oracle. Asserted
    on the exact law rather than by hoping a sample hits it.
    """

    assert same_core_probability(kind, Relation.FAR) > 0.0, kind.value


def test_surface_lookups_refuse_unknown_bases() -> None:
    with pytest.raises(KeyError, match="has no base"):
        base_probability(K.FAMILY_NAME, "NotABase")
    with pytest.raises(KeyError, match="has no base"):
        cluster_of(K.FAMILY_NAME, "NotABase")


def test_render_form_refuses_a_bad_form_or_overlong_core() -> None:
    with pytest.raises(ValueError, match="form index out of range"):
        render_form(K.FAMILY_NAME, 99, "Sorensen")
    with pytest.raises(ValueError, match="form index out of range"):
        render_form(K.FAMILY_NAME, -1, "Sorensen")
    width = surface_of(K.FAMILY_NAME).width
    with pytest.raises(ValueError, match="longer than the kind's padded width"):
        render_form(K.FAMILY_NAME, 0, "x" * (width + 1))


def test_invert_form_refuses_foreign_values() -> None:
    width = surface_of(K.FAMILY_NAME).width
    with pytest.raises(ValueError, match="wrong width"):
        invert_form(K.FAMILY_NAME, "short")
    # Correct width, but a character no form's alphabet emits (a backtick is not in
    # any of the three disjoint image sets).
    with pytest.raises(ValueError, match="belongs to no form"):
        invert_form(K.FAMILY_NAME, "`" * width)


@pytest.mark.parametrize("relation", (Relation.EQUAL, Relation.NEAR, Relation.FAR))
def test_likelihood_of_an_off_pool_core_is_zero(relation: Relation) -> None:
    """A core the noise law can emit has no likelihood: the law is closed."""

    assert likelihood_of(K.FAMILY_NAME, relation, "zz-not-a-core", "Sorensen") == 0.0
    assert likelihood_of(K.FAMILY_NAME, relation, "Sorensen", "zz-not-a-core") == 0.0


def test_form_defect_flags_a_core_the_forms_cannot_round_trip() -> None:
    """A core ending in the pad character loses it on inversion, so the promise
    breaks and the defect reports 1.0. Shipped cores never end in the pad; this
    exercises the failure path the invariant exists to catch."""

    pad = surface_of(K.FAMILY_NAME).pad
    assert form_defect(K.FAMILY_NAME, (f"Soren{pad}",)) == 1.0
