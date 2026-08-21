"""External performance receipt coverage for generated scale tiers."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from synthworld.agentic.enterprise.generated_scale import (
    default_enterprise_agentic_generation_config_v2,
    generate_enterprise_agentic_scale_world,
)
from synthworld.agentic.enterprise.generated_scale_models import (
    EnterpriseAgenticPerformanceReceiptV1,
    EnterpriseAgenticScaleTierV2,
)
from synthworld.agentic.enterprise.generated_scale_serialization import (
    generated_enterprise_agentic_scale_public_artifacts,
)
from synthworld.agentic.enterprise.generated_serialization import (
    generated_enterprise_agentic_artifact_set_sha256,
)
from tools import measure_enterprise_agentic_scale as measurement


def test_scale_measurement_records_each_tier_and_artifact_binding(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "lock"
    lock.write_text("locked\n", encoding="utf-8")
    receipt = measurement.measure_enterprise_agentic_scale(
        source_revision="test-revision",
        dependency_lock=lock,
        iterations=1,
    )

    assert receipt.source_revision == "test-revision"
    assert tuple(item.tier for item in receipt.measurements) == tuple(
        EnterpriseAgenticScaleTierV2
    )
    assert all(item.iterations == 1 for item in receipt.measurements)
    assert all(item.peak_memory_bytes > 0 for item in receipt.measurements)
    assert all(item.generation_seconds_median > 0 for item in receipt.measurements)
    assert all(
        len(item.public_artifact_set_sha256) == 64 for item in receipt.measurements
    )


def test_scale_measurement_rejects_invalid_operator_inputs(tmp_path: Path) -> None:
    lock = tmp_path / "lock"
    lock.write_text("locked\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source revision"):
        measurement.measure_enterprise_agentic_scale(
            source_revision=" ", dependency_lock=lock, iterations=1
        )
    with pytest.raises(ValueError, match="iterations"):
        measurement.measure_enterprise_agentic_scale(
            source_revision="revision", dependency_lock=lock, iterations=0
        )


def test_checked_in_scale_receipt_binds_lock_and_generated_artifacts() -> None:
    root = Path(__file__).parents[1]
    receipt = EnterpriseAgenticPerformanceReceiptV1.model_validate_json(
        (root / "docs/_data/enterprise-agentic-tier-performance.json").read_bytes()
    )
    assert (
        receipt.dependency_lock_sha256
        == hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
    )
    assert tuple(item.tier for item in receipt.measurements) == tuple(
        EnterpriseAgenticScaleTierV2
    )
    for measurement_row in receipt.measurements:
        config = default_enterprise_agentic_generation_config_v2(
            measurement_row.tier,
            seed=20_260_821 + measurement_row.iterations - 1,
        )
        generated = generate_enterprise_agentic_scale_world(config)
        assert generated.identity.configuration_sha256 == (
            measurement_row.configuration_sha256
        )
        assert (
            generated_enterprise_agentic_artifact_set_sha256(
                generated_enterprise_agentic_scale_public_artifacts(generated)
            )
            == measurement_row.public_artifact_set_sha256
        )


def test_scale_measurement_cli_writes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = tmp_path / "lock"
    lock.write_text("locked\n", encoding="utf-8")
    receipt = EnterpriseAgenticPerformanceReceiptV1(
        source_revision="revision",
        dependency_lock_sha256="0" * 64,
        python_version="3.12.test",
        platform="test-platform",
        measurements=(),
    )
    monkeypatch.setattr(
        measurement,
        "measure_enterprise_agentic_scale",
        lambda **_kwargs: receipt,
    )
    output = tmp_path / "receipt.json"
    arguments = [
        "--source-revision",
        "revision",
        "--dependency-lock",
        str(lock),
        "--iterations",
        "1",
        "--output",
        str(output),
    ]
    assert measurement.main(arguments) == 0
    assert (
        EnterpriseAgenticPerformanceReceiptV1.model_validate_json(output.read_bytes())
        == receipt
    )
    with pytest.raises(SystemExit):
        measurement.main(arguments)
