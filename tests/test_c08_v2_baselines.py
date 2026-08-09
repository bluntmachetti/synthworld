"""Tests for disclosure-safe C08 v2 aggregate baseline records."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parent / "fixtures/c08_v2"
ASTERIA_FILE = ROOT / "asteria/baseline-records.json"
ENTERPRISE_FILE = ROOT / "enterprise/baseline-records.json"
SEED = 20260809
ASTERIA_FAILURE_MODES = (
    "exact",
    "missing",
    "fabricated",
    "wrong_action",
    "extra",
    "discarded",
)
ENTERPRISE_FAILURE_MODES = (
    "exact",
    "missing",
    "fabricated",
    "wrong_action",
    "extra",
)


def _load_tool() -> Any:
    path = Path("tools/generate_c08_v2_baselines.py")
    spec = importlib.util.spec_from_file_location("c08_baseline_generator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(path: Path) -> dict[str, Any]:
    payload_bytes = path.read_bytes()
    payload = json.loads(payload_bytes)
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
    assert payload_bytes == expected
    assert payload_bytes.decode("utf-8").endswith("\n")
    assert not payload_bytes.decode("utf-8").endswith("\n\n")
    return payload


def _assert_shape(
    payload: dict[str, Any],
    *,
    benchmark_id: str,
    failure_modes: tuple[str, ...],
) -> None:
    assert set(payload) == {
        "benchmark_id",
        "schema_version",
        "public_input_digest",
        "records",
    }
    assert payload["benchmark_id"] == benchmark_id
    assert payload["schema_version"] == "2.0.0"
    assert re.fullmatch(r"[0-9a-f]{64}", payload["public_input_digest"])
    records = payload["records"]
    assert isinstance(records, list)
    assert tuple(record["failure_mode"] for record in records) == failure_modes
    submission_digests: set[str] = set()
    for record in records:
        assert set(record) == {"failure_mode", "submission_digest", "metrics"}
        assert re.fullmatch(r"[0-9a-f]{64}", record["submission_digest"])
        submission_digests.add(record["submission_digest"])
        metrics = record["metrics"]
        assert isinstance(metrics, list)
        names: set[str] = set()
        for metric in metrics:
            assert set(metric) == {
                "name",
                "numerator",
                "denominator",
                "value",
                "denominator_meaning",
            }
            assert isinstance(metric["name"], str)
            assert metric["name"] not in names
            names.add(metric["name"])
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
    assert len(submission_digests) == len(records)
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        '"case"',
        '"submission"',
        '"observation_id"',
        '"evidence_id"',
        '"action_id"',
        '"outcomes"',
        '"evaluator"',
        '"truth"',
    ):
        assert forbidden not in serialized


def _records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {record["failure_mode"]: record for record in payload["records"]}


def _metric(record: dict[str, Any], name: str) -> float:
    value = next(
        metric["value"]
        for metric in record["metrics"]
        if metric["name"] == name
    )
    assert isinstance(value, float)
    return value


def test_fixture_inventory_is_exact() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
    }
    assert actual == {
        "asteria/baseline-records.json",
        "enterprise/baseline-records.json",
    }
    assert not any(path.is_symlink() for path in ROOT.rglob("*"))


def test_asteria_aggregate_shape_reproduction_and_directions() -> None:
    tool = _load_tool()
    payload = _fixture(ASTERIA_FILE)
    assert payload == tool.build_asteria_baseline_records(SEED)
    _assert_shape(
        payload,
        benchmark_id="asteria-agentic-c08-v2",
        failure_modes=ASTERIA_FAILURE_MODES,
    )
    records = _records(payload)
    exact = records["exact"]
    assert _metric(records["missing"], "missing_or_discarded_free") < _metric(
        exact, "missing_or_discarded_free"
    )
    assert _metric(records["discarded"], "missing_or_discarded_free") < _metric(
        exact, "missing_or_discarded_free"
    )
    assert _metric(records["fabricated"], "fabricated_evidence_free") < _metric(
        exact, "fabricated_evidence_free"
    )
    assert _metric(
        records["wrong_action"], "wrong_action_evidence_free"
    ) < _metric(exact, "wrong_action_evidence_free")
    assert _metric(records["extra"], "extra_evidence_free") < _metric(
        exact, "extra_evidence_free"
    )


def test_enterprise_aggregate_shape_reproduction_and_directions() -> None:
    tool = _load_tool()
    payload = _fixture(ENTERPRISE_FILE)
    assert payload == tool.build_enterprise_baseline_records(SEED)
    _assert_shape(
        payload,
        benchmark_id="enterprise-agentic-c08-v2",
        failure_modes=ENTERPRISE_FAILURE_MODES,
    )
    records = _records(payload)
    exact = records["exact"]
    assert _metric(records["missing"], "evidence_completeness_recall") < _metric(
        exact, "evidence_completeness_recall"
    )
    assert _metric(records["fabricated"], "evidence_fabrication_rate") > _metric(
        exact, "evidence_fabrication_rate"
    )
    assert _metric(
        records["wrong_action"], "evidence_wrong_action_rate"
    ) > _metric(exact, "evidence_wrong_action_rate")
    assert _metric(records["extra"], "evidence_extra_rate") > _metric(
        exact, "evidence_extra_rate"
    )


def test_generator_rejects_unexpected_fixture_entries(tmp_path: Path) -> None:
    tool = _load_tool()
    tmp_path.joinpath("unexpected.json").write_bytes(b"{}\n")
    with pytest.raises(RuntimeError, match="unexpected"):
        tool.write_baselines(tmp_path)


def test_generator_rejects_symlinked_output_root(tmp_path: Path) -> None:
    tool = _load_tool()
    real_root = tmp_path / "real"
    real_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink"):
        tool.write_baselines(linked_root)


def test_generator_is_deterministic(tmp_path: Path) -> None:
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
