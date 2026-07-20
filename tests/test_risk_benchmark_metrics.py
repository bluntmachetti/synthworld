from __future__ import annotations

from synthworld import RiskBand, evaluate_risk_benchmark, generate_risk_benchmark


def test_golden_risk_benchmark_metrics_check_frozen_artifacts() -> None:
    metrics = evaluate_risk_benchmark(
        generate_risk_benchmark(seed=20_260_719, persona_count=10)
    )

    assert metrics.persona_count == metrics.case_count == 10
    assert metrics.factor_count == 18
    assert metrics.score_sum == 430
    assert metrics.band_distribution == {
        RiskBand.NONE: 1,
        RiskBand.LOW: 1,
        RiskBand.MODERATE: 5,
        RiskBand.HIGH: 1,
        RiskBand.CRITICAL: 2,
    }
    assert metrics.safely_fake_record_rate == 1.0
    assert metrics.answer_key_separation_integrity == 1.0
    assert metrics.cross_file_case_integrity == 1.0
    assert metrics.factor_arithmetic_integrity == 1.0
    assert metrics.score_integrity == 1.0
    assert metrics.band_integrity == 1.0
    assert metrics.deterministic_replay_integrity == 1.0
    assert metrics.frozen_artifact_checked is True
    assert metrics.frozen_artifact_integrity == 1.0


def test_generated_risk_metrics_are_dynamic_and_exact() -> None:
    metrics = evaluate_risk_benchmark(
        generate_risk_benchmark(seed=20_260_719, persona_count=100)
    )

    assert metrics.persona_count == metrics.case_count == 100
    assert metrics.factor_count == 198
    assert metrics.score_sum == 4_780
    assert metrics.band_distribution == {
        RiskBand.NONE: 1,
        RiskBand.LOW: 17,
        RiskBand.MODERATE: 41,
        RiskBand.HIGH: 24,
        RiskBand.CRITICAL: 17,
    }
    assert metrics.safely_fake_record_rate == 1.0
    assert metrics.answer_key_separation_integrity == 1.0
    assert metrics.cross_file_case_integrity == 1.0
    assert metrics.factor_arithmetic_integrity == 1.0
    assert metrics.score_integrity == 1.0
    assert metrics.band_integrity == 1.0
    assert metrics.deterministic_replay_integrity == 1.0
    assert metrics.frozen_artifact_checked is False
    assert metrics.frozen_artifact_integrity is None


def test_non_golden_seed_is_replayed_without_claiming_a_frozen_check() -> None:
    metrics = evaluate_risk_benchmark(
        generate_risk_benchmark(seed=20_260_720, persona_count=10)
    )

    assert metrics.deterministic_replay_integrity == 1.0
    assert metrics.frozen_artifact_checked is False
    assert metrics.frozen_artifact_integrity is None
