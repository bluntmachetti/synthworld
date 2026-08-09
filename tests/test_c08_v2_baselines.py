"""Tests for deterministic, lineage-specific C08 v2 baseline records."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from synthworld.agentic.c08_v2 import (
    C08AsteriaSubmissionV2,
    evaluate_c08_submission,
    generate_c08_asteria_v2,
)
from synthworld.agentic.enterprise.c08_v2 import (
    C08CaseOutcomeV2,
    C08EvaluationReportV2,
    C08SubmissionV2,
    evaluate_c08,
    generate_c08_reference,
)

ROOT = Path(__file__).parent / "fixtures/c08_v2"
SEED = 20260809
ASTERIA_CASES = {
    "exact",
    "missing",
    "fabricated",
    "wrong_action",
    "extra",
    "discarded",
}
ENTERPRISE_CASES = {"exact", "missing", "fabricated", "wrong_action", "extra"}


def _load_tool() -> Any:
    path = Path("tools/generate_c08_v2_baselines.py")
    spec = importlib.util.spec_from_file_location("c08_baseline_generator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_bytes())
    assert isinstance(payload, dict)
    expected = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert path.read_bytes() == expected
    assert path.read_bytes().decode("utf-8").endswith("\n")
    assert not path.read_bytes().decode("utf-8").endswith("\n\n")
    return payload


def _metric_values(result: dict[str, Any]) -> dict[str, float | None]:
    metrics = result["metrics"]
    assert isinstance(metrics, list)
    values: dict[str, float | None] = {}
    for metric in metrics:
        assert isinstance(metric, dict)
        assert set(metric) >= {
            "name",
            "numerator",
            "denominator",
            "value",
            "denominator_meaning",
        }
        assert isinstance(metric["name"], str)
        assert isinstance(metric["numerator"], int)
        assert isinstance(metric["denominator"], int)
        assert metric["numerator"] <= metric["denominator"]
        assert isinstance(metric["denominator_meaning"], str)
        assert metric["denominator_meaning"]
        if metric["denominator"]:
            assert metric["value"] == pytest.approx(
                metric["numerator"] / metric["denominator"]
            )
        else:
            assert metric["value"] is None
        values[metric["name"]] = metric["value"]
    assert len(values) == len(metrics)
    assert "score" not in result
    assert "aggregate" not in result
    return values


def _assert_discriminates(
    exact_result: dict[str, Any], case_result: dict[str, Any]
) -> None:
    exact_values = _metric_values(exact_result)
    case_values = _metric_values(case_result)
    assert any(
        case_values[name] is not None
        and exact_values[name] is not None
        and case_values[name] < exact_values[name]
        for name in exact_values
    )


def test_asteria_baselines_replay_exactly_and_discriminate() -> None:
    benchmark = generate_c08_asteria_v2(SEED)
    paths = sorted((ROOT / "asteria").glob("*.json"))
    assert {path.stem for path in paths} == ASTERIA_CASES
    payloads = {path.stem: _fixture(path) for path in paths}
    exact_result = payloads["exact"]["result"]
    assert isinstance(exact_result, dict)
    for case, payload in payloads.items():
        assert set(payload) == {
            "baseline_id",
            "case",
            "lineage",
            "schema_version",
            "seed",
            "submission",
            "result",
        }
        assert payload["case"] == case
        assert payload["lineage"] == "asteria"
        assert payload["schema_version"] == "2.0.0"
        assert payload["seed"] == SEED
        assert isinstance(payload["submission"], dict)
        submission = C08AsteriaSubmissionV2.model_validate(payload["submission"])
        result = evaluate_c08_submission(benchmark, submission)
        assert payload["result"] == result.model_dump(mode="json")
        assert isinstance(payload["result"], dict)
        _metric_values(payload["result"])
        if case != "exact":
            _assert_discriminates(exact_result, payload["result"])
    assert _metric_values(payloads["discarded"]["result"])[
        "missing_or_discarded_free"
    ] == pytest.approx(5 / 6)


def test_enterprise_baselines_replay_exactly_and_discriminate() -> None:
    bundle = generate_c08_reference(SEED)
    paths = sorted((ROOT / "enterprise").glob("*.json"))
    assert {path.stem for path in paths} == ENTERPRISE_CASES
    payloads = {path.stem: _fixture(path) for path in paths}
    exact_result = payloads["exact"]["result"]
    assert isinstance(exact_result, dict)
    expected_outcomes = {
        "exact": (C08CaseOutcomeV2.EXACT, None),
        "missing": (C08CaseOutcomeV2.MISSING, "write"),
        "fabricated": (C08CaseOutcomeV2.FABRICATED, "delete"),
        "wrong_action": (C08CaseOutcomeV2.WRONG_ACTION, "write"),
        "extra": (C08CaseOutcomeV2.EXTRA, "delete"),
    }
    for case, payload in payloads.items():
        assert payload["lineage"] == "enterprise"
        assert payload["schema_version"] == "2.0.0"
        assert payload["seed"] == SEED
        submission = C08SubmissionV2.model_validate(payload["submission"])
        result = evaluate_c08(
            public=bundle.public,
            evaluator=bundle.evaluator,
            submission=submission,
        )
        assert payload["result"] == result.model_dump(mode="json")
        assert isinstance(payload["result"], dict)
        _metric_values(payload["result"])
        expected_outcome, target_name = expected_outcomes[case]
        typed_result = C08EvaluationReportV2.model_validate(payload["result"])
        if target_name is None:
            assert all(item.outcome is expected_outcome for item in typed_result.outcomes)
        else:
            target = next(
                action for action in bundle.public.actions if action.action == target_name
            )
            outcome = next(
                item.outcome
                for item in typed_result.outcomes
                if item.action_id == target.action_id
            )
            assert outcome is expected_outcome
        if case != "exact":
            _assert_discriminates(exact_result, payload["result"])


def test_baseline_generator_rejects_unexpected_fixture_entries(tmp_path: Path) -> None:
    tool = _load_tool()
    tmp_path.joinpath("unexpected.json").write_bytes(b"{}\n")
    with pytest.raises(RuntimeError, match="unexpected"):
        tool.write_baselines(tmp_path)


def test_baseline_generator_is_deterministic(tmp_path: Path) -> None:
    tool = _load_tool()
    tool.write_baselines(tmp_path, seed=SEED)
    first = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in sorted(tmp_path.rglob("*.json"))
    }
    tool.write_baselines(tmp_path, seed=SEED)
    second = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in sorted(tmp_path.rglob("*.json"))
    }
    assert first == second
