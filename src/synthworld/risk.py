from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from synthworld.exposures import DataClass, ExposureSeverity
from synthworld.models import SyntheticModel

RISK_FORMULA_VERSION = "breach-exposure-v1"

_SEVERITY_POINTS: dict[ExposureSeverity, int] = {
    ExposureSeverity.LOW: 5,
    ExposureSeverity.MEDIUM: 10,
    ExposureSeverity.HIGH: 15,
    ExposureSeverity.CRITICAL: 20,
}
_DATA_POINTS: dict[DataClass, int] = {
    DataClass.EMAIL: 1,
    DataClass.USERNAME: 1,
    DataClass.PHONE: 3,
    DataClass.ADDRESS: 4,
    DataClass.DATE_OF_BIRTH: 5,
    DataClass.EMPLOYER: 1,
    DataClass.EDUCATION: 1,
    DataClass.NATIONAL_ID: 10,
    DataClass.PASSWORD: 10,
}


class RiskBand(StrEnum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class PublicBreachRiskObservation(SyntheticModel):
    source_record_id: UUID
    occurred_on: date
    severity: ExposureSeverity
    exposed_data: tuple[DataClass, ...] = Field(min_length=1)

    @field_validator("exposed_data")
    @classmethod
    def sort_unique_data_classes(
        cls,
        value: tuple[DataClass, ...],
    ) -> tuple[DataClass, ...]:
        if len(value) != len(set(value)):
            raise ValueError("risk observation data classes must be unique")
        return tuple(sorted(value, key=lambda item: item.value))


class PublicRiskCase(SyntheticModel):
    id: UUID
    breaches: tuple[PublicBreachRiskObservation, ...]

    @field_validator("breaches")
    @classmethod
    def sort_unique_breaches(
        cls,
        value: tuple[PublicBreachRiskObservation, ...],
    ) -> tuple[PublicBreachRiskObservation, ...]:
        _require_unique_ids(
            tuple(item.source_record_id for item in value),
            "public risk breaches",
        )
        return tuple(sorted(value, key=lambda item: item.source_record_id.int))


class PublicRiskCorpus(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    cases: tuple[PublicRiskCase, ...] = Field(min_length=1)

    @field_validator("cases")
    @classmethod
    def sort_unique_cases(
        cls,
        value: tuple[PublicRiskCase, ...],
    ) -> tuple[PublicRiskCase, ...]:
        _require_unique_ids(tuple(item.id for item in value), "public risk cases")
        return tuple(sorted(value, key=lambda item: item.id.int))


class BreachRiskFactorTruth(SyntheticModel):
    source_record_id: UUID
    severity: ExposureSeverity
    exposed_data: tuple[DataClass, ...] = Field(min_length=1)
    severity_points: int = Field(ge=0, le=20)
    data_points: int = Field(ge=0)
    points: int = Field(ge=0)

    @field_validator("exposed_data")
    @classmethod
    def sort_unique_data_classes(
        cls,
        value: tuple[DataClass, ...],
    ) -> tuple[DataClass, ...]:
        if len(value) != len(set(value)):
            raise ValueError("risk truth data classes must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @model_validator(mode="after")
    def require_consistent_total(self) -> Self:
        if self.severity_points != severity_points(self.severity):
            raise ValueError("risk factor severity points must match its severity")
        if self.data_points != data_points(self.exposed_data):
            raise ValueError("risk factor data points must match its exposed data")
        if self.points != self.severity_points + self.data_points:
            raise ValueError("risk factor points must equal their components")
        return self


class RiskCaseTruth(SyntheticModel):
    case_id: UUID
    score: int = Field(ge=0, le=100)
    band: RiskBand
    factors: tuple[BreachRiskFactorTruth, ...]

    @field_validator("factors")
    @classmethod
    def sort_unique_factors(
        cls,
        value: tuple[BreachRiskFactorTruth, ...],
    ) -> tuple[BreachRiskFactorTruth, ...]:
        _require_unique_ids(
            tuple(item.source_record_id for item in value),
            "risk truth factors",
        )
        return tuple(sorted(value, key=lambda item: item.source_record_id.int))

    @model_validator(mode="after")
    def require_consistent_score_and_band(self) -> Self:
        expected_score = min(100, sum(item.points for item in self.factors))
        if self.score != expected_score:
            raise ValueError("risk truth score must equal capped factor points")
        if self.band is not band_for_score(expected_score):
            raise ValueError("risk truth band must match its score")
        return self


class RiskAnswerKey(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    cases: tuple[RiskCaseTruth, ...] = Field(min_length=1)

    @field_validator("cases")
    @classmethod
    def sort_unique_cases(
        cls,
        value: tuple[RiskCaseTruth, ...],
    ) -> tuple[RiskCaseTruth, ...]:
        _require_unique_ids(tuple(item.case_id for item in value), "risk truth cases")
        return tuple(sorted(value, key=lambda item: item.case_id.int))


class RiskBenchmark(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    public: PublicRiskCorpus
    answer_key: RiskAnswerKey

    @model_validator(mode="after")
    def require_exact_separated_truth(self) -> Self:
        if self.public.seed != self.seed or self.answer_key.seed != self.seed:
            raise ValueError("risk benchmark seeds must match")

        public_cases = {item.id: item for item in self.public.cases}
        truth_cases = {item.case_id: item for item in self.answer_key.cases}
        if public_cases.keys() != truth_cases.keys():
            raise ValueError("risk benchmark public and truth cases must match")

        for case_id, public_case in public_cases.items():
            truth_case = truth_cases[case_id]
            observations = {
                item.source_record_id: item for item in public_case.breaches
            }
            factors = {item.source_record_id: item for item in truth_case.factors}
            if observations.keys() != factors.keys():
                raise ValueError("risk benchmark breaches and factors must match")
            for source_record_id, observation in observations.items():
                factor = factors[source_record_id]
                expected_severity_points = severity_points(observation.severity)
                expected_data_points = data_points(observation.exposed_data)
                if (
                    factor.severity != observation.severity
                    or factor.exposed_data != observation.exposed_data
                    or factor.severity_points != expected_severity_points
                    or factor.data_points != expected_data_points
                    or factor.points != expected_severity_points + expected_data_points
                ):
                    raise ValueError("risk benchmark factor truth is inconsistent")
            expected_score = min(100, sum(item.points for item in factors.values()))
            if truth_case.score != expected_score:
                raise ValueError("risk benchmark score truth is inconsistent")
            if truth_case.band is not band_for_score(expected_score):
                raise ValueError("risk benchmark band truth is inconsistent")
        return self


def severity_points(severity: ExposureSeverity) -> int:
    return _SEVERITY_POINTS[severity]


def data_points(exposed_data: tuple[DataClass, ...]) -> int:
    return sum(_DATA_POINTS[item] for item in set(exposed_data))


def band_for_score(score: int) -> RiskBand:
    if not 0 <= score <= 100:
        raise ValueError("breach-exposure score must be between zero and 100")
    if score == 0:
        return RiskBand.NONE
    if score <= 24:
        return RiskBand.LOW
    if score <= 49:
        return RiskBand.MODERATE
    if score <= 74:
        return RiskBand.HIGH
    return RiskBand.CRITICAL


def _require_unique_ids(ids: tuple[UUID, ...], label: str) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} require unique IDs")


__all__ = [
    "RISK_FORMULA_VERSION",
    "BreachRiskFactorTruth",
    "PublicBreachRiskObservation",
    "PublicRiskCase",
    "PublicRiskCorpus",
    "RiskAnswerKey",
    "RiskBand",
    "RiskBenchmark",
    "RiskCaseTruth",
    "band_for_score",
    "data_points",
    "severity_points",
]
