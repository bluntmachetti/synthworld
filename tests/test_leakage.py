"""The leakage detector's own discriminating tests.

A detector that flags everything is as useless as one that flags nothing, so every
positive here is paired with a negative that must stay quiet.
"""

from __future__ import annotations

from hashlib import blake2b

import pytest

from synthworld.generator import generate_world
from synthworld.leakage import (
    field_recoverability,
    lexical_projection,
    numeric_projection,
    rank_correlation,
    step_ratio,
    world_recoverability,
)

_COUNT = 100


def _literal_ordinal() -> list[str]:
    """What the shipped core profile emits: the index, spelled out."""

    return [f"synth_person_{index:04d}@example.test" for index in range(_COUNT)]


def _affine_modular() -> list[str]:
    """The scheme proposed for issue #43. No ordinal, not monotone, still a leak."""

    return [
        f"SYN-{(39_916_801 * index + 12345) % 10**8:08d}" for index in range(_COUNT)
    ]


def _keyed_hash() -> list[str]:
    """Derived from content under a key, with no dependence on the index."""

    return [
        "h-" + blake2b(f"name{index}".encode(), digest_size=6, key=b"k").hexdigest()
        for index in range(_COUNT)
    ]


def test_literal_ordinal_is_reported_as_leaking() -> None:
    result = field_recoverability(
        field="email", values_in_index_order=_literal_ordinal()
    )

    assert result.verdict == "leaking"
    assert result.numeric_step_ratio is not None
    assert result.numeric_step_ratio < 0.05
    assert result.reasons


def test_affine_modular_encoding_is_reported_as_leaking() -> None:
    """The case a substring search cannot see, and the reason this module exists.

    The value contains no ordinal, is not monotone in the index, and looks like
    noise. Its first differences take exactly two values - the step and the wrap.
    """

    result = field_recoverability(field="nid", values_in_index_order=_affine_modular())

    assert result.verdict == "leaking"
    assert result.numeric_step_ratio is not None
    assert result.numeric_step_ratio < 0.05
    # The property that makes it invisible to the other two signals.
    assert abs(result.numeric_rank_correlation or 0.0) < 0.5
    assert "0000" not in "".join(_affine_modular())


def test_keyed_hash_values_are_reported_as_clean() -> None:
    """The negative control. Without it the detector could flag everything."""

    result = field_recoverability(field="handle", values_in_index_order=_keyed_hash())

    assert result.verdict == "clean"
    assert result.reasons == ()
    assert result.distinctness == 1.0


def test_the_control_must_not_be_an_affine_permutation() -> None:
    """Regression for a real defect in the first revision of this module.

    Its control was ``(index * stride + 1) % count``. Composing an affine map with
    an arithmetic progression gives another arithmetic progression, so the control
    scored as structured as the leak and suppressed every positive - the module
    passed the modular scheme it was written to catch. The control's own step ratio
    must therefore be high on exactly the input that leaks most.
    """

    result = field_recoverability(field="nid", values_in_index_order=_affine_modular())

    assert result.control_step_ratio > 0.5
    assert result.numeric_step_ratio is not None
    assert result.control_step_ratio > result.numeric_step_ratio * 10


def test_shipped_core_profile_leaks_on_four_fields() -> None:
    """Point it at the real generator: it must reproduce the audited finding."""

    world = generate_world(seed=42, persona_count=_COUNT)
    personas = sorted(world.personas, key=lambda item: item.id)
    scored = {
        item.field: item
        for item in world_recoverability(
            {
                "email": [item.emails[0].value for item in personas],
                "employer": [item.employment[0].organization for item in personas],
                "school": [item.education[0].institution for item in personas],
                "family_name": [item.family_name for item in personas],
            }
        )
    }

    assert scored["email"].verdict == "leaking"
    assert scored["employer"].verdict == "leaking"
    assert scored["school"].verdict == "leaking"
    # Names come from Faker's distribution and carry no index dependence, so the
    # detector must leave them alone even though they sit beside three leaks.
    assert scored["family_name"].verdict == "clean"


def test_report_is_ordered_worst_first() -> None:
    """A report that buries a leak below clean rows is a report nobody reads."""

    report = world_recoverability(
        {"zzz_clean": _keyed_hash(), "aaa_leaking": _literal_ordinal()}
    )

    assert [item.field for item in report] == ["aaa_leaking", "zzz_clean"]


def test_a_field_with_few_distinct_values_is_not_flagged() -> None:
    """The control working in the other direction, which is what makes it a control.

    Three shared employers across a hundred people is realistic and carries no
    index dependence, but its lexical projection only has three ranks, so its first
    differences are necessarily repetitive however the values are assigned. The
    control is equally repetitive, which is the signal that the structure lives in
    the value distribution rather than in who got which value - so no positive is
    raised. Without this gate the detector would report every shared institution,
    household and workplace in the new profile as a leak.
    """

    clustered = [f"Example Works {index % 3}" for index in range(_COUNT)]
    result = field_recoverability(field="employer", values_in_index_order=clustered)

    assert result.control_step_ratio < 0.5
    assert result.lexical_step_ratio < 0.5
    assert result.verdict == "clean"
    assert result.reasons == ()


def test_partial_structure_is_reported_as_suspect_rather_than_resolved() -> None:
    """Between the thresholds the honest answer is "look at this", not a verdict."""

    half = [f"v{index // 2:03d}" for index in range(_COUNT)]
    result = field_recoverability(field="half", values_in_index_order=half)

    assert result.verdict in {"suspect", "leaking"}


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ("abc-0042-xy", 42),
        ("no digits here", None),
        # Longest run wins: an eight-digit payload must not hide behind a year.
        ("SYN-99887766-2026", 99_887_766),
    ],
)
def test_numeric_projection_takes_the_longest_digit_run(
    values: str, expected: int | None
) -> None:
    assert numeric_projection(values) == expected


def test_lexical_projection_ranks_among_distinct_values() -> None:
    assert lexical_projection(("b", "a", "b", "c")) == (1, 0, 1, 2)


def test_step_ratio_and_rank_correlation_handle_degenerate_input() -> None:
    assert step_ratio(()) == 1.0
    assert step_ratio((5,)) == 1.0
    assert rank_correlation(()) == 0.0
    # Every value identical: no spread, so no correlation can be claimed.
    assert rank_correlation((7, 7, 7, 7)) == 0.0
    assert rank_correlation((0, 1, 2, 3)) == pytest.approx(1.0)
    assert rank_correlation((3, 2, 1, 0)) == pytest.approx(-1.0)


def test_empty_field_does_not_divide_by_zero() -> None:
    result = field_recoverability(field="empty", values_in_index_order=[])

    assert result.support == 0
    assert result.distinctness == 0.0
    assert result.verdict == "clean"


def test_values_without_digits_skip_the_numeric_signals() -> None:
    result = field_recoverability(
        field="letters", values_in_index_order=["alpha", "beta", "gamma"]
    )

    assert result.numeric_step_ratio is None
    assert result.numeric_rank_correlation is None
