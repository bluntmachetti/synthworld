"""Measure whether evaluator truth is recoverable from public values.

A syntactic leak check asks "does the persona ordinal appear in this string?".
That question is answerable and nearly useless: it passes any encoding that is not
a literal substring. A proposed identifier scheme for issue #43 rendered the
national identifier as ``(39_916_801 * index + offset) mod 10**8``, which contains
no ordinal, is not monotone, and looks like noise - and hands the index back to
anyone who takes first differences, because a modular arithmetic progression has
exactly two distinct steps.

So this module asks the question that matters instead: **given only the public
value, how much of the truth comes back?** It is evaluator-side and holds the
truth already, so it does not have to guess the encoding - it measures whether a
cheap function of the public value predicts the truth, and compares that against
the same measurement on a shuffled assignment.

Three signals, because one is not enough:

``distinctness``
    Fraction of entities whose value belongs to them alone. High is not itself a
    leak - real email addresses are unique per person - but a field that is both a
    perfect key *and* ordered by generation is an answer key.

``step_ratio``
    Distinct first differences of the projected values, taken in true index order,
    over the number of differences. An independent field gives a ratio near 1: its
    successive gaps are arbitrary. Any affine encoding of the index collapses it to
    near zero - a literal counter has one distinct step, and an affine-modular
    encoding has exactly two, one of them the wrap. This is the signal that catches
    what a substring search cannot.

``rank_correlation``
    Spearman correlation between projected value and true index, catching
    order-preserving encodings that are not affine.

Each is computed twice: once on the true index, once on a keyed-hash shuffle of it.
The shuffle is the control. A signal that fires on both is measuring the shape of
the value distribution rather than a dependence on identity, and is discarded.

The control has to be chosen with some care, and the first revision of this module
got it wrong in a way worth recording. It used an affine permutation, which is
deterministic and fixed-point-free and therefore looked adequate. But composing an
affine map with an arithmetic progression yields another arithmetic progression, so
the control scored exactly as structured as the leak and cancelled every positive:
the module reported the modular national identifier it was written to catch, along
with four real leaks in the shipped core profile, as clean. Determinism and
structurelessness are separate requirements and only the second one was checked.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import blake2b
from itertools import pairwise
from typing import Literal

from synthworld.models import SyntheticModel

#: Below this, successive gaps are too repetitive to have arisen independently of
#: the index. The separation is not marginal and does not need tuning: a literal
#: counter scores 1/(n-1) and an affine-modular encoding 2/(n-1), while an
#: independent field scores above 0.9 at any useful size. Anything in between is
#: reported as `suspect` rather than silently resolved either way.
_STEP_RATIO_LEAKING = 0.10
_STEP_RATIO_CLEAN = 0.50

#: Spearman magnitude above which the projection is effectively a relabelling of
#: the index. Exact monotone encodings score 1.0.
_RANK_LEAKING = 0.90

#: The control must be clearly unstructured for a positive to count, otherwise the
#: signal is a property of the values rather than of their assignment to entities.
_CONTROL_MIN_STEP_RATIO = 0.50

_DIGIT_RUN = re.compile(r"\d+")


class FieldRecoverability(SyntheticModel):
    """How much of the truth a single public field gives back."""

    field: str
    support: int
    distinctness: float
    numeric_step_ratio: float | None
    numeric_rank_correlation: float | None
    lexical_step_ratio: float
    lexical_rank_correlation: float
    control_step_ratio: float
    verdict: Literal["clean", "suspect", "leaking"]
    reasons: tuple[str, ...]


def numeric_projection(value: str) -> int | None:
    """Longest digit run as an integer, or ``None`` when the value has no digits.

    Longest rather than first: a leak hidden in an eight-digit payload should not
    be masked by a two-digit year sharing the string.
    """

    runs = _DIGIT_RUN.findall(value)
    if not runs:
        return None
    return int(max(runs, key=len))


def lexical_projection(values: Sequence[str]) -> tuple[int, ...]:
    """Rank each value among the sorted distinct values.

    Catches order-preserving encodings over any alphabet, including ones with no
    digits for :func:`numeric_projection` to find.
    """

    order = {value: rank for rank, value in enumerate(sorted(set(values)))}
    return tuple(order[value] for value in values)


def step_ratio(projected: Sequence[int]) -> float:
    """Distinct first differences over the number of differences.

    Near zero means the sequence advances by a repeating step, which is what an
    encoding of the index looks like however it is dressed up.
    """

    if len(projected) < 2:
        return 1.0
    steps = [later - earlier for earlier, later in pairwise(projected)]
    return len(set(steps)) / len(steps)


def rank_correlation(projected: Sequence[int]) -> float:
    """Spearman correlation of the projection against position, in ``[-1, 1]``.

    Ties are averaged, so a field with few distinct values cannot manufacture a
    correlation out of its own repetition.
    """

    count = len(projected)
    if count < 2:
        return 0.0
    ranks = _average_ranks(projected)
    positions = _average_ranks(range(count))
    mean_rank = sum(ranks) / count
    mean_position = sum(positions) / count
    covariance = sum(
        (rank - mean_rank) * (position - mean_position)
        for rank, position in zip(ranks, positions, strict=True)
    )
    rank_spread = sum((rank - mean_rank) ** 2 for rank in ranks)
    position_spread = sum((position - mean_position) ** 2 for position in positions)
    if rank_spread == 0.0 or position_spread == 0.0:
        return 0.0
    return float(covariance / (rank_spread * position_spread) ** 0.5)


def _average_ranks(values: Sequence[float] | range) -> tuple[float, ...]:
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(ordered)
    position = 0
    while position < len(ordered):
        end = position
        while (
            end + 1 < len(ordered)
            and values[ordered[end + 1]] == values[ordered[position]]
        ):
            end += 1
        shared = (position + end) / 2
        for index in range(position, end + 1):
            ranks[ordered[index]] = shared
        position = end + 1
    return tuple(ranks)


def _control_order(count: int) -> tuple[int, ...]:
    """A deterministic shuffle that destroys arithmetic structure.

    An affine permutation such as ``(index * stride + 1) % count`` is deterministic
    and fixed-point-free and still useless here: composing an affine map with an
    arithmetic progression yields another arithmetic progression, so the control
    scores exactly as structured as the leak and cancels every positive. A first
    revision of this module did that, and reported the modular national identifier
    it was written to catch as clean.

    Keyed-hash ordering has no algebraic relationship to the index, and blake2b is
    stable across runs, platforms and Python versions, so the control is
    reproducible without being structured.
    """

    return tuple(
        sorted(
            range(count),
            key=lambda index: blake2b(
                str(index).encode("utf-8"), digest_size=8, key=b"leakage-control"
            ).digest(),
        )
    )


def field_recoverability(
    *,
    field: str,
    values_in_index_order: Sequence[str],
) -> FieldRecoverability:
    """Score one field's public values against the true generation order.

    ``values_in_index_order`` is the public value for entity 0, entity 1, and so on
    in the world's own generation order. That order is evaluator-side knowledge;
    the point of the measurement is to find out how much of it the public values
    hand back.
    """

    support = len(values_in_index_order)
    counts = Counter(values_in_index_order)
    distinctness = (
        sum(1 for value in values_in_index_order if counts[value] == 1) / support
        if support
        else 0.0
    )

    lexical = lexical_projection(values_in_index_order)
    lexical_step = step_ratio(lexical)
    lexical_rank = rank_correlation(lexical)

    projected = [numeric_projection(value) for value in values_in_index_order]
    numeric_step: float | None = None
    numeric_rank: float | None = None
    if all(item is not None for item in projected) and support >= 2:
        numeric = [item for item in projected if item is not None]
        numeric_step = step_ratio(numeric)
        numeric_rank = rank_correlation(numeric)

    permutation = _control_order(support)
    control = [values_in_index_order[index] for index in permutation]
    control_step = step_ratio(lexical_projection(control))

    reasons: list[str] = []
    # The control gates every positive. Without it a field whose values are
    # naturally clustered - a dozen shared employers, say - reads as structured no
    # matter how it was assigned, and the detector reports leaks that are not there.
    if control_step >= _CONTROL_MIN_STEP_RATIO:
        for label, ratio in (("lexical", lexical_step), ("numeric", numeric_step)):
            if ratio is not None and ratio <= _STEP_RATIO_LEAKING:
                reasons.append(f"{label} values advance by a repeating step")
        for label, value in (("lexical", lexical_rank), ("numeric", numeric_rank)):
            if value is not None and abs(value) >= _RANK_LEAKING:
                reasons.append(f"{label} values are ordered by generation index")

    suspect = control_step >= _CONTROL_MIN_STEP_RATIO and any(
        ratio is not None and _STEP_RATIO_LEAKING < ratio < _STEP_RATIO_CLEAN
        for ratio in (lexical_step, numeric_step)
    )
    verdict: Literal["clean", "suspect", "leaking"] = (
        "leaking" if reasons else "suspect" if suspect else "clean"
    )
    return FieldRecoverability(
        field=field,
        support=support,
        distinctness=distinctness,
        numeric_step_ratio=numeric_step,
        numeric_rank_correlation=numeric_rank,
        lexical_step_ratio=lexical_step,
        lexical_rank_correlation=lexical_rank,
        control_step_ratio=control_step,
        verdict=verdict,
        reasons=tuple(reasons),
    )


def world_recoverability(
    fields: Mapping[str, Sequence[str]],
) -> tuple[FieldRecoverability, ...]:
    """Score every field, ordered worst first so a report cannot bury a leak."""

    scored = [
        field_recoverability(field=field, values_in_index_order=values)
        for field, values in sorted(fields.items())
    ]
    severity = {"leaking": 0, "suspect": 1, "clean": 2}
    return tuple(sorted(scored, key=lambda item: (severity[item.verdict], item.field)))


__all__ = [
    "FieldRecoverability",
    "field_recoverability",
    "lexical_projection",
    "numeric_projection",
    "rank_correlation",
    "step_ratio",
    "world_recoverability",
]
