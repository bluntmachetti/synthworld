from __future__ import annotations

from collections import Counter

from synthworld import (
    RiskBand,
    generate_risk_benchmark,
    public_risk_corpus_to_json,
    risk_answer_key_to_json,
)


def test_golden_risk_benchmark_has_exact_reviewed_calibration() -> None:
    benchmark = generate_risk_benchmark(seed=20_260_719, persona_count=10)

    assert [item.score for item in benchmark.answer_key.cases] == [
        75,
        0,
        31,
        49,
        65,
        80,
        26,
        39,
        16,
        49,
    ]
    assert Counter(item.band for item in benchmark.answer_key.cases) == {
        RiskBand.NONE: 1,
        RiskBand.LOW: 1,
        RiskBand.MODERATE: 5,
        RiskBand.HIGH: 1,
        RiskBand.CRITICAL: 2,
    }
    assert sum(len(item.factors) for item in benchmark.answer_key.cases) == 18


def test_generated_risk_tier_has_exact_distribution() -> None:
    benchmark = generate_risk_benchmark(seed=20_260_719, persona_count=100)

    assert len(benchmark.public.cases) == 100
    assert sum(len(item.factors) for item in benchmark.answer_key.cases) == 198
    assert sum(item.score for item in benchmark.answer_key.cases) == 4_780
    assert Counter(item.band for item in benchmark.answer_key.cases) == {
        RiskBand.NONE: 1,
        RiskBand.LOW: 17,
        RiskBand.MODERATE: 41,
        RiskBand.HIGH: 24,
        RiskBand.CRITICAL: 17,
    }


def test_risk_generation_is_seeded_and_public_input_is_canonical() -> None:
    first = generate_risk_benchmark(seed=20_260_719, persona_count=10)
    replay = generate_risk_benchmark(seed=20_260_719, persona_count=10)
    changed = generate_risk_benchmark(seed=20_260_720, persona_count=10)

    reordered_cases = tuple(
        item.model_copy(update={"breaches": tuple(reversed(item.breaches))})
        for item in reversed(first.public.cases)
    )
    reordered_public = first.public.model_copy(update={"cases": reordered_cases})

    assert public_risk_corpus_to_json(first.public) == public_risk_corpus_to_json(
        replay.public
    )
    assert risk_answer_key_to_json(first.answer_key) == risk_answer_key_to_json(
        replay.answer_key
    )
    assert public_risk_corpus_to_json(first.public) != public_risk_corpus_to_json(
        changed.public
    )
    assert public_risk_corpus_to_json(reordered_public) == public_risk_corpus_to_json(
        first.public
    )


def test_public_risk_input_contains_no_answer_key_or_identity_oracles() -> None:
    benchmark = generate_risk_benchmark(seed=20_260_719, persona_count=10)
    serialized = public_risk_corpus_to_json(benchmark.public)

    for forbidden in (
        "answer_key",
        "persona_id",
        "actual_persona_id",
        "match_kind",
        "lifecycle",
        "connected_person_ids",
        "relationship",
        "expected",
        "severity_points",
        "data_points",
        '"score"',
        '"band"',
    ):
        assert forbidden not in serialized


def test_public_risk_uuids_do_not_encode_corpus_ordinals() -> None:
    benchmark = generate_risk_benchmark(seed=20_260_719, persona_count=10)
    low_bits = (1 << 32) - 1
    case_ordinals = set(range(1, 11))
    breach_ordinals = {
        (case_index << 16) | breach_index
        for case_index in range(1, 11)
        for breach_index in range(1, 4)
    }

    assert all(
        (case.id.int & low_bits) not in case_ordinals for case in benchmark.public.cases
    )
    assert all(
        (breach.source_record_id.int & low_bits) not in breach_ordinals
        for case in benchmark.public.cases
        for breach in case.breaches
    )
