from __future__ import annotations

from uuid import UUID, uuid5

from synthworld.exposure_generator import generate_exposure_corpus
from synthworld.risk import (
    BreachRiskFactorTruth,
    PublicBreachRiskObservation,
    PublicRiskCase,
    PublicRiskCorpus,
    RiskAnswerKey,
    RiskBenchmark,
    RiskCaseTruth,
    band_for_score,
    data_points,
    severity_points,
)

_RISK_NAMESPACE = UUID("19985c09-86d9-53bf-8b99-213f54f51fb4")


def generate_risk_benchmark(*, seed: int, persona_count: int) -> RiskBenchmark:
    """Derive opaque public breach facts and their separate calibration truth."""

    corpus = generate_exposure_corpus(seed=seed, persona_count=persona_count)
    public_cases: list[PublicRiskCase] = []
    truth_cases: list[RiskCaseTruth] = []
    for case_index, script in enumerate(corpus.exposure_scripts, start=1):
        case_id = _ordered_uuid(seed=seed, kind="risk-case", index=case_index)
        observations: list[PublicBreachRiskObservation] = []
        factors: list[BreachRiskFactorTruth] = []
        for breach_index, breach in enumerate(script.breaches, start=1):
            source_record_id = _ordered_uuid(
                seed=seed,
                kind="risk-breach",
                index=(case_index << 16) | breach_index,
            )
            observation = PublicBreachRiskObservation(
                source_record_id=source_record_id,
                occurred_on=breach.occurred_on,
                severity=breach.severity,
                exposed_data=breach.exposed_data,
            )
            observations.append(observation)
            severity_value = severity_points(breach.severity)
            data_value = data_points(breach.exposed_data)
            factors.append(
                BreachRiskFactorTruth(
                    source_record_id=source_record_id,
                    severity=breach.severity,
                    exposed_data=breach.exposed_data,
                    severity_points=severity_value,
                    data_points=data_value,
                    points=severity_value + data_value,
                )
            )
        public_cases.append(PublicRiskCase(id=case_id, breaches=tuple(observations)))
        score = min(100, sum(item.points for item in factors))
        truth_cases.append(
            RiskCaseTruth(
                case_id=case_id,
                score=score,
                band=band_for_score(score),
                factors=tuple(factors),
            )
        )

    return RiskBenchmark(
        seed=seed,
        public=PublicRiskCorpus(seed=seed, cases=tuple(public_cases)),
        answer_key=RiskAnswerKey(seed=seed, cases=tuple(truth_cases)),
    )


def _ordered_uuid(*, seed: int, kind: str, index: int) -> UUID:
    # UUID5 keeps case and breach references stable without encoding a
    # recoverable corpus ordinal in their bytes.
    return uuid5(_RISK_NAMESPACE, f"{kind}:{seed}:{index}")


__all__ = ["generate_risk_benchmark"]
