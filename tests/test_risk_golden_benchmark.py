from __future__ import annotations

import hashlib
from importlib.resources import files
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld import (
    RiskBenchmarkIntegrityError,
    generate_risk_benchmark,
    load_golden_public_risk_corpus,
    load_golden_risk_answer_key,
    load_golden_risk_benchmark,
    public_risk_corpus_to_json,
    risk_answer_key_to_json,
    risk_serialization,
)

_SEED = 20_260_719


def test_frozen_risk_artifacts_and_manifests_match_generation() -> None:
    generated = generate_risk_benchmark(seed=_SEED, persona_count=10)
    benchmark_directory = files("synthworld.benchmarks")
    public_artifact = benchmark_directory.joinpath("risk-public-golden-v1.json")
    answer_artifact = benchmark_directory.joinpath("risk-answer-golden-v1.json")

    assert public_risk_corpus_to_json(
        load_golden_public_risk_corpus()
    ) == public_risk_corpus_to_json(generated.public)
    assert risk_answer_key_to_json(
        load_golden_risk_answer_key()
    ) == risk_answer_key_to_json(generated.answer_key)
    assert load_golden_risk_benchmark() == generated
    assert (
        _manifest_hash("RISK_PUBLIC_SHA256SUMS")
        == hashlib.sha256(public_artifact.read_bytes()).hexdigest()
    )
    assert (
        _manifest_hash("RISK_ANSWER_SHA256SUMS")
        == hashlib.sha256(answer_artifact.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("manifest", ["empty", "wrong_name", "wrong_hash"])
def test_frozen_loader_rejects_manifest_and_checksum_tampering(
    manifest: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = public_risk_corpus_to_json(
        generate_risk_benchmark(seed=_SEED, persona_count=10).public
    ).encode()
    (tmp_path / "risk-public-golden-v1.json").write_bytes(artifact)
    expected_hash = hashlib.sha256(artifact).hexdigest()
    manifest_content = {
        "empty": "",
        "wrong_name": f"{expected_hash} wrong.json\n",
        "wrong_hash": f"{'0' * 64} risk-public-golden-v1.json\n",
    }[manifest]
    (tmp_path / "RISK_PUBLIC_SHA256SUMS").write_text(
        manifest_content,
        encoding="utf-8",
    )
    monkeypatch.setattr(risk_serialization, "files", lambda package: tmp_path)

    with pytest.raises(RiskBenchmarkIntegrityError):
        load_golden_public_risk_corpus()


def test_frozen_loader_rejects_schema_drift_after_a_valid_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = b"{}\n"
    (tmp_path / "risk-answer-golden-v1.json").write_bytes(artifact)
    (tmp_path / "RISK_ANSWER_SHA256SUMS").write_text(
        f"{hashlib.sha256(artifact).hexdigest()} risk-answer-golden-v1.json\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(risk_serialization, "files", lambda package: tmp_path)

    with pytest.raises(ValidationError):
        load_golden_risk_answer_key()


def test_combined_loader_rejects_seed_and_cross_file_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = generate_risk_benchmark(seed=_SEED, persona_count=10)
    changed_seed = benchmark.answer_key.model_copy(update={"seed": _SEED + 1})
    monkeypatch.setattr(
        risk_serialization,
        "load_golden_public_risk_corpus",
        lambda: benchmark.public,
    )
    monkeypatch.setattr(
        risk_serialization,
        "load_golden_risk_answer_key",
        lambda: changed_seed,
    )
    with pytest.raises(RiskBenchmarkIntegrityError, match="seeds differ"):
        load_golden_risk_benchmark()

    missing_case = benchmark.answer_key.model_copy(
        update={"cases": benchmark.answer_key.cases[:-1]}
    )
    monkeypatch.setattr(
        risk_serialization,
        "load_golden_risk_answer_key",
        lambda: missing_case,
    )
    with pytest.raises(RiskBenchmarkIntegrityError, match="cross-file drift"):
        load_golden_risk_benchmark()


def _manifest_hash(name: str) -> str:
    manifest = files("synthworld.benchmarks").joinpath(name).read_text(encoding="utf-8")
    expected_hash, _filename = manifest.strip().split()
    return expected_hash
