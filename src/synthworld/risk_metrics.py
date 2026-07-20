from __future__ import annotations

import re
from collections import Counter

from pydantic import Field

from synthworld.models import SyntheticModel
from synthworld.risk import RiskBand, RiskBenchmark
from synthworld.risk_generator import generate_risk_benchmark
from synthworld.risk_serialization import (
    load_golden_risk_benchmark,
    public_risk_corpus_to_json,
    risk_answer_key_to_json,
)

_GOLDEN_SEED = 20_260_719
_GOLDEN_PERSONA_COUNT = 10
_PERSONA_ID = re.compile(r"\bpersona-\d{4}\b")
_SEVERITY_POINTS = {"low": 5, "medium": 10, "high": 15, "critical": 20}
_DATA_POINTS = {
    "email": 1,
    "username": 1,
    "phone": 3,
    "address": 4,
    "date_of_birth": 5,
    "employer": 1,
    "education": 1,
    "national_id": 10,
    "password": 10,
}
_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "actual_persona_id",
        "answer_key",
        "band",
        "connected_person_ids",
        "data_points",
        "expected_band",
        "expected_score",
        "lifecycle",
        "match_kind",
        "persona_id",
        "points",
        "relationship_truth",
        "score",
        "severity_points",
    }
)


class RiskBenchmarkMetrics(SyntheticModel):
    seed: int
    persona_count: int = Field(ge=0)
    case_count: int = Field(ge=0)
    factor_count: int = Field(ge=0)
    score_sum: int = Field(ge=0)
    band_distribution: dict[RiskBand, int]
    safely_fake_record_rate: float = Field(ge=0.0, le=1.0)
    answer_key_separation_integrity: float = Field(ge=0.0, le=1.0)
    cross_file_case_integrity: float = Field(ge=0.0, le=1.0)
    factor_arithmetic_integrity: float = Field(ge=0.0, le=1.0)
    score_integrity: float = Field(ge=0.0, le=1.0)
    band_integrity: float = Field(ge=0.0, le=1.0)
    deterministic_replay_integrity: float = Field(ge=0.0, le=1.0)
    frozen_artifact_checked: bool
    frozen_artifact_integrity: float | None = Field(default=None, ge=0.0, le=1.0)


def evaluate_risk_benchmark(benchmark: RiskBenchmark) -> RiskBenchmarkMetrics:
    """Independently measure risk truth integrity and frozen reproduction."""

    public_by_id = {item.id: item for item in benchmark.public.cases}
    truth_by_id = {item.case_id: item for item in benchmark.answer_key.cases}
    public_ids = set(public_by_id)
    truth_ids = set(truth_by_id)
    matching_case_ids = public_ids & truth_ids
    factor_count = sum(len(item.factors) for item in benchmark.answer_key.cases)

    factor_checks: list[bool] = []
    score_checks: list[bool] = []
    band_checks: list[bool] = []
    for case_id in matching_case_ids:
        public_case = public_by_id[case_id]
        truth_case = truth_by_id[case_id]
        observations = {item.source_record_id: item for item in public_case.breaches}
        factors = {item.source_record_id: item for item in truth_case.factors}
        factor_checks.append(observations.keys() == factors.keys())
        for source_record_id in observations.keys() & factors.keys():
            observation = observations[source_record_id]
            factor = factors[source_record_id]
            severity_points = _SEVERITY_POINTS[observation.severity.value]
            data_points = sum(
                _DATA_POINTS[item.value] for item in set(observation.exposed_data)
            )
            factor_checks.append(
                factor.severity == observation.severity
                and factor.exposed_data == observation.exposed_data
                and factor.severity_points == severity_points
                and factor.data_points == data_points
                and factor.points == severity_points + data_points
            )
        expected_score = min(100, sum(item.points for item in factors.values()))
        score_checks.append(truth_case.score == expected_score)
        band_checks.append(truth_case.band is _independent_band(expected_score))

    records = (
        benchmark.public,
        *benchmark.public.cases,
        *(item for case in benchmark.public.cases for item in case.breaches),
        benchmark.answer_key,
        *benchmark.answer_key.cases,
        *(item for case in benchmark.answer_key.cases for item in case.factors),
    )
    public_payload = benchmark.public.model_dump(mode="json")
    public_keys = set(_iter_keys(public_payload))
    public_json = public_risk_corpus_to_json(benchmark.public)
    replay = generate_risk_benchmark(
        seed=benchmark.seed,
        persona_count=len(benchmark.public.cases),
    )
    replay_matches = public_risk_corpus_to_json(
        replay.public
    ) == public_json and risk_answer_key_to_json(
        replay.answer_key
    ) == risk_answer_key_to_json(benchmark.answer_key)

    frozen_checked = (
        benchmark.seed == _GOLDEN_SEED
        and len(benchmark.public.cases) == _GOLDEN_PERSONA_COUNT
    )
    frozen_integrity: float | None = None
    if frozen_checked:
        frozen = load_golden_risk_benchmark()
        frozen_integrity = float(
            public_risk_corpus_to_json(frozen.public) == public_json
            and risk_answer_key_to_json(frozen.answer_key)
            == risk_answer_key_to_json(benchmark.answer_key)
        )

    return RiskBenchmarkMetrics(
        seed=benchmark.seed,
        persona_count=len(benchmark.public.cases),
        case_count=len(benchmark.answer_key.cases),
        factor_count=factor_count,
        score_sum=sum(item.score for item in benchmark.answer_key.cases),
        band_distribution=dict(
            Counter(item.band for item in benchmark.answer_key.cases)
        ),
        safely_fake_record_rate=_rate(
            sum(item.synthetic is True for item in records),
            len(records),
        ),
        answer_key_separation_integrity=float(
            not (public_keys & _FORBIDDEN_PUBLIC_KEYS)
            and _PERSONA_ID.search(public_json) is None
        ),
        cross_file_case_integrity=float(public_ids == truth_ids),
        factor_arithmetic_integrity=_all_rate(factor_checks),
        score_integrity=_all_rate(score_checks),
        band_integrity=_all_rate(band_checks),
        deterministic_replay_integrity=float(replay_matches),
        frozen_artifact_checked=frozen_checked,
        frozen_artifact_integrity=frozen_integrity,
    )


def _independent_band(score: int) -> RiskBand:
    if score == 0:
        return RiskBand.NONE
    if score <= 24:
        return RiskBand.LOW
    if score <= 49:
        return RiskBand.MODERATE
    if score <= 74:
        return RiskBand.HIGH
    return RiskBand.CRITICAL


def _iter_keys(value: object) -> tuple[str, ...]:
    if isinstance(value, dict):
        return tuple(value) + tuple(
            key for item in value.values() for key in _iter_keys(item)
        )
    if isinstance(value, list):
        return tuple(key for item in value for key in _iter_keys(item))
    return ()


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _all_rate(checks: list[bool]) -> float:
    return _rate(sum(checks), len(checks))


__all__ = ["RiskBenchmarkMetrics", "evaluate_risk_benchmark"]
