"""Artifact, schema, example, and CLI tests for continuous assurance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from synthworld.cli import main
from synthworld.continuous_assurance import (
    EVALUATOR_CONTINUOUS_ASSURANCE_PATH,
    PUBLIC_CONTINUOUS_ASSURANCE_PATH,
    ContinuousAssuranceArtifactError,
    ContinuousAssuranceConfigV1,
    ContinuousAssuranceEvaluatorV1,
    ContinuousAssurancePredictionV1,
    ContinuousAssurancePublicV1,
    ContinuousAssuranceReportV1,
    evaluate_continuous_assurance_prediction,
    export_continuous_assurance_benchmark,
    load_evaluator_continuous_assurance_benchmark,
    load_public_continuous_assurance_benchmark,
    perfect_continuous_assurance_prediction,
    reference_continuous_assurance,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseArtifactManifestV1

CONTRACT_ROOT = Path("continuous-assurance-contract")


def _export(root: Path) -> Path:
    benchmark = reference_continuous_assurance()
    export_continuous_assurance_benchmark(
        root,
        public=benchmark.public,
        evaluator=benchmark.evaluator,
    )
    return root


def _replace_bound_artifact(
    root: Path,
    *,
    visibility: Literal["public", "evaluator"],
    name: str,
    model: BaseModel,
) -> None:
    payload = canonical_json_bytes(model)
    artifact = root / visibility / name
    artifact.write_bytes(payload)
    manifest_path = root / visibility / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    descriptor = manifest.artifacts[0].model_copy(
        update={
            "schema_version": str(model.model_dump()["schema_version"]),
            "digest": synthetic_digest(payload),
            "byte_size": len(payload),
        }
    )
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": (descriptor,)}))
    )


def test_artifact_round_trip_is_canonical_split_and_public_only(tmp_path: Path) -> None:
    benchmark = reference_continuous_assurance()
    root = tmp_path / "continuous"
    export_continuous_assurance_benchmark(
        root,
        public=benchmark.public,
        evaluator=benchmark.evaluator,
    )
    assert load_public_continuous_assurance_benchmark(root) == benchmark.public
    assert load_evaluator_continuous_assurance_benchmark(root) == benchmark.evaluator
    assert {
        str(item.relative_to(root)) for item in root.rglob("*") if item.is_file()
    } == {
        PUBLIC_CONTINUOUS_ASSURANCE_PATH,
        "public/manifest.json",
        EVALUATOR_CONTINUOUS_ASSURANCE_PATH,
        "evaluator/manifest.json",
    }
    public_bytes = (root / PUBLIC_CONTINUOUS_ASSURANCE_PATH).read_bytes()
    assert public_bytes == canonical_json_bytes(benchmark.public)
    assert b'"case_kind"' not in public_bytes
    assert b'"finding_required"' not in public_bytes

    (root / EVALUATOR_CONTINUOUS_ASSURANCE_PATH).write_bytes(b"{")
    assert load_public_continuous_assurance_benchmark(root) == benchmark.public
    with pytest.raises(ContinuousAssuranceArtifactError, match="artifact is invalid"):
        load_evaluator_continuous_assurance_benchmark(root)


def test_export_rejects_existing_root_and_invalid_evaluator(tmp_path: Path) -> None:
    benchmark = reference_continuous_assurance()
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ContinuousAssuranceArtifactError, match="root exists"):
        export_continuous_assurance_benchmark(
            existing,
            public=benchmark.public,
            evaluator=benchmark.evaluator,
        )
    invalid = benchmark.evaluator.model_copy(
        update={"public_digest": synthetic_digest(b"wrong public\n")}
    )
    with pytest.raises(ContinuousAssuranceArtifactError, match="artifacts are invalid"):
        export_continuous_assurance_benchmark(
            tmp_path / "invalid",
            public=benchmark.public,
            evaluator=invalid,
        )


def test_loader_rejects_inventory_directory_and_nonregular_entries(
    tmp_path: Path,
) -> None:
    with pytest.raises(ContinuousAssuranceArtifactError, match="unreadable"):
        load_public_continuous_assurance_benchmark(tmp_path / "missing")

    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "public").write_bytes(b"not a directory")
    with pytest.raises(ContinuousAssuranceArtifactError, match="not a real directory"):
        load_public_continuous_assurance_benchmark(fake)

    root = _export(tmp_path / "extra")
    (root / "public" / "unexpected.json").write_bytes(b"{}")
    with pytest.raises(ContinuousAssuranceArtifactError, match="inventory differs"):
        load_public_continuous_assurance_benchmark(root)

    root = _export(tmp_path / "nonregular")
    artifact = root / PUBLIC_CONTINUOUS_ASSURANCE_PATH
    artifact.unlink()
    artifact.mkdir()
    with pytest.raises(ContinuousAssuranceArtifactError, match="non-regular"):
        load_public_continuous_assurance_benchmark(root)


def test_loader_rejects_manifest_visibility_count_and_binding(tmp_path: Path) -> None:
    root = _export(tmp_path / "visibility")
    manifest_path = root / "public" / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"visibility": "evaluator"}))
    )
    with pytest.raises(ContinuousAssuranceArtifactError, match="visibility differs"):
        load_public_continuous_assurance_benchmark(root)

    root = _export(tmp_path / "count")
    manifest_path = root / "public" / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": ()}))
    )
    with pytest.raises(ContinuousAssuranceArtifactError, match="declare one"):
        load_public_continuous_assurance_benchmark(root)

    root = _export(tmp_path / "binding")
    manifest_path = root / "public" / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    descriptor = manifest.artifacts[0].model_copy(update={"byte_size": 0})
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": (descriptor,)}))
    )
    with pytest.raises(ContinuousAssuranceArtifactError, match="binding differs"):
        load_public_continuous_assurance_benchmark(root)


def test_loader_rejects_invalid_noncanonical_and_semantically_invalid_json(
    tmp_path: Path,
) -> None:
    root = _export(tmp_path / "invalid-json")
    (root / PUBLIC_CONTINUOUS_ASSURANCE_PATH).write_bytes(b"{")
    with pytest.raises(ContinuousAssuranceArtifactError, match="artifact is invalid"):
        load_public_continuous_assurance_benchmark(root)

    root = _export(tmp_path / "noncanonical")
    artifact = root / PUBLIC_CONTINUOUS_ASSURANCE_PATH
    artifact.write_bytes(b" " + artifact.read_bytes())
    with pytest.raises(ContinuousAssuranceArtifactError, match="not canonical"):
        load_public_continuous_assurance_benchmark(root)

    benchmark = reference_continuous_assurance()
    root = _export(tmp_path / "bad-public")
    bad_public = benchmark.public.model_copy(
        update={
            "benchmark": benchmark.public.benchmark.model_copy(
                update={"case_inventory_digest": synthetic_digest(b"wrong cases\n")}
            )
        }
    )
    _replace_bound_artifact(
        root,
        visibility="public",
        name="continuous-assurance-input.json",
        model=bad_public,
    )
    with pytest.raises(ContinuousAssuranceArtifactError, match="public bindings"):
        load_public_continuous_assurance_benchmark(root)

    root = _export(tmp_path / "bad-evaluator")
    bad_evaluator = benchmark.evaluator.model_copy(
        update={"public_digest": synthetic_digest(b"wrong public\n")}
    )
    _replace_bound_artifact(
        root,
        visibility="evaluator",
        name="continuous-assurance-evaluator.json",
        model=bad_evaluator,
    )
    with pytest.raises(ContinuousAssuranceArtifactError, match="evaluator bindings"):
        load_evaluator_continuous_assurance_benchmark(root)


def test_generated_schemas_and_examples_match_reference_contracts() -> None:
    benchmark = reference_continuous_assurance()
    prediction = perfect_continuous_assurance_prediction(benchmark.evaluator)
    report = evaluate_continuous_assurance_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        prediction=prediction,
    )
    models: dict[str, BaseModel] = {
        "continuous-assurance-config": benchmark.config,
        "continuous-assurance-public": benchmark.public,
        "continuous-assurance-evaluator": benchmark.evaluator,
        "continuous-assurance-prediction": prediction,
        "continuous-assurance-report": report,
    }
    types: dict[str, type[BaseModel]] = {
        "continuous-assurance-config": ContinuousAssuranceConfigV1,
        "continuous-assurance-public": ContinuousAssurancePublicV1,
        "continuous-assurance-evaluator": ContinuousAssuranceEvaluatorV1,
        "continuous-assurance-prediction": ContinuousAssurancePredictionV1,
        "continuous-assurance-report": ContinuousAssuranceReportV1,
    }
    for stem, model in models.items():
        schema = json.loads(
            (CONTRACT_ROOT / "schemas" / f"{stem}.schema.json").read_text()
        )
        model_type = types[stem]
        assert schema["x-generated-from"] == (
            f"{model_type.__module__}.{model_type.__name__}"
        )
        errors = tuple(
            Draft202012Validator(schema).iter_errors(model.model_dump(mode="json"))
        )
        assert errors == ()
    for stem, model in models.items():
        assert (
            CONTRACT_ROOT / "examples" / f"{stem}.json"
        ).read_bytes() == canonical_json_bytes(model)


def test_cli_generates_and_scores_all_output_modes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "world"
    assert (
        main(
            [
                "generate-continuous-assurance",
                "--seed",
                "20260804",
                "--tier",
                "smoke",
                "--risk-threshold",
                "73",
                "--justification-kind",
                "emergency_access",
                "--output",
                str(root),
            ]
        )
        == 0
    )
    assert "tier=smoke, 8 cases" in capsys.readouterr().out
    evaluator = load_evaluator_continuous_assurance_benchmark(root)
    predictions = tmp_path / "prediction.json"
    predictions.write_text(
        perfect_continuous_assurance_prediction(evaluator).model_dump_json(indent=2)
    )
    for summary in (False, True):
        arguments = [
            "evaluate",
            "continuous-assurance",
            "--benchmark-root",
            str(root),
            "--predictions",
            str(predictions),
        ]
        if summary:
            arguments.append("--summary")
        assert main(arguments) == 0
        output = capsys.readouterr().out
        if summary:
            assert "finding_detection_recall" in output
            assert "n=7" in output
        else:
            assert json.loads(output)["schema_version"] == "1.0.0"

    held_out = tmp_path / "held-out"
    assert (
        main(
            [
                "generate-continuous-assurance",
                "--tier",
                "held_out",
                "--output",
                str(held_out),
            ]
        )
        == 0
    )
    assert "not a secrecy claim" in capsys.readouterr().out


def test_cli_reports_generation_and_evaluation_input_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prediction = tmp_path / "prediction.json"
    prediction.write_text("{}\n")
    assert (
        main(
            [
                "evaluate",
                "continuous-assurance",
                "--predictions",
                str(prediction),
            ]
        )
        == 1
    )
    assert "--benchmark-root is required" in capsys.readouterr().err

    existing = tmp_path / "existing"
    existing.mkdir()
    assert (
        main(
            [
                "generate-continuous-assurance",
                "--output",
                str(existing),
            ]
        )
        == 1
    )
    assert "root exists" in capsys.readouterr().err

    invalid_config = tmp_path / "invalid-config"
    assert (
        main(
            [
                "generate-continuous-assurance",
                "--risk-threshold",
                "101",
                "--output",
                str(invalid_config),
            ]
        )
        == 1
    )
    assert "less than or equal to 100" in capsys.readouterr().err

    root = _export(tmp_path / "valid")
    assert (
        main(
            [
                "evaluate",
                "continuous-assurance",
                "--benchmark-root",
                str(root),
                "--predictions",
                str(prediction),
            ]
        )
        == 1
    )
    assert capsys.readouterr().err
