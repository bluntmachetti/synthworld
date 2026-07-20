from __future__ import annotations

from copy import deepcopy
from datetime import date
from uuid import UUID

import pytest
from pydantic import ValidationError

from synthworld import (
    DataClass,
    ExposureSeverity,
    PublicBreachRiskObservation,
    PublicRiskCorpus,
    RiskAnswerKey,
    RiskBand,
    RiskBenchmark,
    band_for_score,
    data_points,
    generate_risk_benchmark,
    severity_points,
)

_SEED = 20_260_719


def test_formula_weights_and_band_boundaries_are_exact() -> None:
    assert [severity_points(item) for item in ExposureSeverity] == [5, 10, 15, 20]
    assert {item: data_points((item,)) for item in DataClass} == {
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
    assert data_points((DataClass.PASSWORD, DataClass.PASSWORD)) == 10
    assert [(score, band_for_score(score)) for score in (0, 1, 24, 25, 49)] == [
        (0, RiskBand.NONE),
        (1, RiskBand.LOW),
        (24, RiskBand.LOW),
        (25, RiskBand.MODERATE),
        (49, RiskBand.MODERATE),
    ]
    assert [(score, band_for_score(score)) for score in (50, 74, 75, 100)] == [
        (50, RiskBand.HIGH),
        (74, RiskBand.HIGH),
        (75, RiskBand.CRITICAL),
        (100, RiskBand.CRITICAL),
    ]
    for invalid in (-1, 101):
        with pytest.raises(ValueError, match="between zero and 100"):
            band_for_score(invalid)


def test_public_risk_models_sort_inputs_and_reject_duplicates() -> None:
    benchmark = generate_risk_benchmark(seed=_SEED, persona_count=10)
    observation = benchmark.public.cases[2].breaches[0]
    reordered = PublicBreachRiskObservation(
        source_record_id=observation.source_record_id,
        occurred_on=observation.occurred_on,
        severity=observation.severity,
        exposed_data=tuple(reversed(observation.exposed_data)),
    )

    assert reordered.exposed_data == observation.exposed_data
    with pytest.raises(ValidationError, match="data classes must be unique"):
        PublicBreachRiskObservation(
            source_record_id=UUID(int=1),
            occurred_on=date(2026, 7, 19),
            severity=ExposureSeverity.LOW,
            exposed_data=(DataClass.EMAIL, DataClass.EMAIL),
        )

    public_payload = benchmark.public.model_dump(mode="python")
    public_payload["cases"][0]["breaches"] = (
        public_payload["cases"][0]["breaches"][0],
        public_payload["cases"][0]["breaches"][0],
    )
    with pytest.raises(ValidationError, match="breaches require unique IDs"):
        PublicRiskCorpus.model_validate(public_payload)

    duplicate_case = benchmark.public.model_dump(mode="python")
    duplicate_case["cases"] = (
        duplicate_case["cases"][0],
        duplicate_case["cases"][0],
    )
    with pytest.raises(ValidationError, match="cases require unique IDs"):
        PublicRiskCorpus.model_validate(duplicate_case)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("persona_id", "persona-0001"),
        ("match_kind", "true_match"),
        ("lifecycle", [{"state": "reappeared"}]),
        ("expected_score", 100),
    ],
)
def test_public_schema_rejects_oracle_and_extra_fields(
    field: str,
    value: object,
) -> None:
    payload = generate_risk_benchmark(
        seed=_SEED,
        persona_count=10,
    ).public.model_dump(mode="python")
    payload["cases"][0][field] = value

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PublicRiskCorpus.model_validate(payload)


def test_public_schema_rejects_noncanonical_labels_and_synthetic_markers() -> None:
    payload = generate_risk_benchmark(
        seed=_SEED,
        persona_count=10,
    ).public.model_dump(mode="python")
    payload["cases"][0]["breaches"][0]["exposed_data"] = ("Email",)
    with pytest.raises(ValidationError):
        PublicRiskCorpus.model_validate(payload)

    unsafe = generate_risk_benchmark(
        seed=_SEED,
        persona_count=10,
    ).public.model_dump(mode="python")
    unsafe["cases"][0]["breaches"][0]["synthetic"] = False
    with pytest.raises(ValidationError):
        PublicRiskCorpus.model_validate(unsafe)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_case",
        "extra_case",
        "missing_factor",
        "extra_factor",
        "wrong_severity",
        "wrong_data",
        "wrong_severity_points",
        "wrong_data_points",
        "wrong_total",
        "wrong_score",
        "wrong_band",
        "wrong_public_seed",
        "wrong_answer_seed",
    ],
)
def test_combined_benchmark_rejects_every_cross_file_drift(mutation: str) -> None:
    payload = deepcopy(
        generate_risk_benchmark(seed=_SEED, persona_count=10).model_dump(mode="python")
    )
    truth_cases = payload["answer_key"]["cases"]
    if mutation == "missing_case":
        payload["answer_key"]["cases"] = truth_cases[:-1]
    elif mutation == "extra_case":
        extra = deepcopy(truth_cases[-1])
        extra["case_id"] = UUID(int=2**120)
        payload["answer_key"]["cases"] = (*truth_cases, extra)
    elif mutation == "missing_factor":
        truth_cases[0]["factors"] = truth_cases[0]["factors"][:-1]
    elif mutation == "extra_factor":
        extra = deepcopy(truth_cases[0]["factors"][0])
        extra["source_record_id"] = UUID(int=2**119)
        truth_cases[0]["factors"] = (*truth_cases[0]["factors"], extra)
    elif mutation == "wrong_severity":
        truth_cases[0]["factors"][0]["severity"] = ExposureSeverity.CRITICAL
    elif mutation == "wrong_data":
        truth_cases[0]["factors"][0]["exposed_data"] = (DataClass.EMAIL,)
    elif mutation == "wrong_severity_points":
        factor = truth_cases[0]["factors"][0]
        factor["severity_points"] += 1
        factor["points"] += 1
    elif mutation == "wrong_data_points":
        factor = truth_cases[0]["factors"][0]
        factor["data_points"] += 1
        factor["points"] += 1
    elif mutation == "wrong_total":
        truth_cases[0]["factors"][0]["points"] += 1
    elif mutation == "wrong_score":
        truth_cases[0]["score"] += 1
    elif mutation == "wrong_band":
        truth_cases[0]["band"] = (
            RiskBand.LOW
            if truth_cases[0]["band"] is RiskBand.CRITICAL
            else RiskBand.CRITICAL
        )
    elif mutation == "wrong_public_seed":
        payload["public"]["seed"] += 1
    else:
        assert mutation == "wrong_answer_seed"
        payload["answer_key"]["seed"] += 1

    with pytest.raises(ValidationError):
        RiskBenchmark.model_validate(payload)


def test_answer_models_reject_duplicate_cases_factors_and_invalid_arithmetic() -> None:
    payload = generate_risk_benchmark(
        seed=_SEED,
        persona_count=10,
    ).answer_key.model_dump(mode="python")
    payload["cases"] = (payload["cases"][0], payload["cases"][0])
    with pytest.raises(ValidationError, match="truth cases require unique IDs"):
        RiskAnswerKey.model_validate(payload)

    payload = generate_risk_benchmark(
        seed=_SEED,
        persona_count=10,
    ).answer_key.model_dump(mode="python")
    payload["cases"][0]["factors"] = (
        payload["cases"][0]["factors"][0],
        payload["cases"][0]["factors"][0],
    )
    with pytest.raises(ValidationError, match="truth factors require unique IDs"):
        RiskAnswerKey.model_validate(payload)

    payload = generate_risk_benchmark(
        seed=_SEED,
        persona_count=10,
    ).answer_key.model_dump(mode="python")
    payload["cases"][0]["factors"][0]["points"] += 1
    with pytest.raises(ValidationError, match="must equal their components"):
        RiskAnswerKey.model_validate(payload)

    payload = generate_risk_benchmark(
        seed=_SEED,
        persona_count=10,
    ).answer_key.model_dump(mode="python")
    payload["cases"][0]["factors"][0]["exposed_data"] = (
        DataClass.EMAIL,
        DataClass.EMAIL,
    )
    with pytest.raises(ValidationError, match="truth data classes must be unique"):
        RiskAnswerKey.model_validate(payload)

    baseline = generate_risk_benchmark(
        seed=_SEED,
        persona_count=10,
    ).answer_key.model_dump(mode="python")
    for field, message in (
        ("severity_points", "severity points must match"),
        ("data_points", "data points must match"),
    ):
        payload = deepcopy(baseline)
        payload["cases"][0]["factors"][0][field] += 1
        payload["cases"][0]["factors"][0]["points"] += 1
        payload["cases"][0]["score"] += 1
        with pytest.raises(ValidationError, match=message):
            RiskAnswerKey.model_validate(payload)

    payload = deepcopy(baseline)
    payload["cases"][0]["score"] += 1
    with pytest.raises(ValidationError, match="score must equal capped factor points"):
        RiskAnswerKey.model_validate(payload)

    payload = deepcopy(baseline)
    payload["cases"][0]["band"] = (
        RiskBand.LOW
        if payload["cases"][0]["band"] is RiskBand.CRITICAL
        else RiskBand.CRITICAL
    )
    with pytest.raises(ValidationError, match="band must match"):
        RiskAnswerKey.model_validate(payload)


def test_combined_benchmark_rechecks_bypassed_nested_model_mutations() -> None:
    benchmark = generate_risk_benchmark(seed=_SEED, persona_count=10)
    case = next(item for item in benchmark.answer_key.cases if item.factors)
    case_index = benchmark.answer_key.cases.index(case)

    missing_factor = case.model_copy(update={"factors": case.factors[1:]})
    wrong_factor = case.factors[0].model_copy(
        update={
            "severity": ExposureSeverity.LOW
            if case.factors[0].severity is not ExposureSeverity.LOW
            else ExposureSeverity.CRITICAL
        }
    )
    inconsistent_factor = case.model_copy(
        update={"factors": (wrong_factor, *case.factors[1:])}
    )
    wrong_score = case.model_copy(update={"score": case.score + 1})
    wrong_band = case.model_copy(
        update={
            "band": RiskBand.LOW
            if case.band is RiskBand.CRITICAL
            else RiskBand.CRITICAL
        }
    )

    for mutation, message in (
        (missing_factor, "breaches and factors must match"),
        (inconsistent_factor, "factor truth is inconsistent"),
        (wrong_score, "score truth is inconsistent"),
        (wrong_band, "band truth is inconsistent"),
    ):
        cases = list(benchmark.answer_key.cases)
        cases[case_index] = mutation
        answer_key = benchmark.answer_key.model_copy(update={"cases": tuple(cases)})
        with pytest.raises(ValidationError, match=message):
            RiskBenchmark(
                seed=benchmark.seed,
                public=benchmark.public,
                answer_key=answer_key,
            )


def test_public_schema_has_an_exact_allowlist_and_opaque_ids() -> None:
    public = generate_risk_benchmark(seed=_SEED, persona_count=10).public
    payload = public.model_dump(mode="json")

    assert set(payload) == {"synthetic", "schema_version", "seed", "cases"}
    assert all(
        set(case) == {"synthetic", "id", "breaches"} for case in payload["cases"]
    )
    assert all(
        set(breach)
        == {
            "synthetic",
            "source_record_id",
            "occurred_on",
            "severity",
            "exposed_data",
        }
        for case in payload["cases"]
        for breach in case["breaches"]
    )
    opaque_ids = (
        value
        for case in payload["cases"]
        for value in (
            case["id"],
            *(item["source_record_id"] for item in case["breaches"]),
        )
    )
    assert all("persona-" not in str(value) for value in opaque_ids)
