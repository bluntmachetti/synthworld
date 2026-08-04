"""Artifact, JSONL, schema, and CLI tests for enterprise-agentic smoke."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from synthworld.agentic.enterprise.errors import (
    EnterpriseAgenticArtifactError,
    EnterpriseAgenticEvaluationError,
)
from synthworld.agentic.enterprise.metrics import (
    evaluate_enterprise_agentic_prediction,
    perfect_enterprise_agentic_prediction,
)
from synthworld.agentic.enterprise.models import (
    EnterpriseAgenticEvaluatorArtifactsV1,
)
from synthworld.agentic.enterprise.reference import reference_enterprise_agentic
from synthworld.agentic.enterprise.serialization import (
    export_enterprise_agentic_benchmark,
    load_evaluator_enterprise_agentic_benchmark,
    load_public_enterprise_agentic_benchmark,
)
from synthworld.agentic.enterprise.trace import (
    enterprise_agentic_trace_from_jsonl,
    enterprise_agentic_trace_to_jsonl,
    validate_enterprise_agentic_trace_jsonl,
)
from synthworld.cli import main
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseArtifactManifestV1

CONTRACT_ROOT = Path("enterprise-identity-access-contract")


def _rewrite_artifact(
    root: Path,
    *,
    visibility: str,
    name: str,
    model: BaseModel,
) -> None:
    payload = canonical_json_bytes(model)
    (root / visibility / name).write_bytes(payload)
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


def test_artifacts_round_trip_and_public_loader_never_reads_evaluator(
    tmp_path: Path,
) -> None:
    reference = reference_enterprise_agentic()
    root = tmp_path / "enterprise-agentic"
    export_enterprise_agentic_benchmark(
        root, public=reference.public, evaluator=reference.evaluator
    )
    assert load_public_enterprise_agentic_benchmark(root) == reference.public
    assert load_evaluator_enterprise_agentic_benchmark(root) == reference.evaluator
    assert {
        str(item.relative_to(root)) for item in root.rglob("*") if item.is_file()
    } == {
        "public/enterprise-agentic-input.json",
        "public/manifest.json",
        "evaluator/enterprise-agentic-evaluator.json",
        "evaluator/manifest.json",
    }
    public_bytes = (root / "public" / "enterprise-agentic-input.json").read_bytes()
    assert public_bytes == canonical_json_bytes(reference.public)
    assert b'"expected_decision"' not in public_bytes
    assert b'"canonical_binding_truth"' not in public_bytes

    (root / "evaluator" / "enterprise-agentic-evaluator.json").write_bytes(b"{")
    assert load_public_enterprise_agentic_benchmark(root) == reference.public
    with pytest.raises(EnterpriseAgenticArtifactError, match="invalid"):
        load_evaluator_enterprise_agentic_benchmark(root)


def test_export_rejects_existing_destination(tmp_path: Path) -> None:
    reference = reference_enterprise_agentic()
    root = tmp_path / "existing"
    root.mkdir()
    with pytest.raises(EnterpriseAgenticArtifactError, match="already exists"):
        export_enterprise_agentic_benchmark(
            root, public=reference.public, evaluator=reference.evaluator
        )


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("missing", "unreadable"),
        ("not_directory", "not a real directory"),
        ("unexpected", "inventory differs"),
        ("nonregular", "non-regular entry"),
        ("visibility", "visibility differs"),
        ("manifest_count", "exactly one artifact"),
        ("descriptor_path", "manifest binding differs"),
        ("descriptor_schema", "manifest binding differs"),
        ("descriptor_size", "manifest binding differs"),
        ("descriptor_digest", "manifest binding differs"),
        ("invalid_json", "artifact is invalid"),
        ("noncanonical", "not canonical JSON"),
    ),
)
def test_public_loader_rejects_each_physical_corruption(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    reference = reference_enterprise_agentic()
    root = tmp_path / corruption
    if corruption == "missing":
        with pytest.raises(EnterpriseAgenticArtifactError, match=message):
            load_public_enterprise_agentic_benchmark(root)
        return
    if corruption == "not_directory":
        root.mkdir()
        (root / "public").write_text("not a directory\n")
        with pytest.raises(EnterpriseAgenticArtifactError, match=message):
            load_public_enterprise_agentic_benchmark(root)
        return
    export_enterprise_agentic_benchmark(
        root, public=reference.public, evaluator=reference.evaluator
    )
    public_root = root / "public"
    manifest_path = public_root / "manifest.json"
    artifact_path = public_root / "enterprise-agentic-input.json"
    if corruption == "unexpected":
        (public_root / "unexpected.json").write_text("{}\n")
    elif corruption == "nonregular":
        artifact_path.unlink()
        artifact_path.symlink_to(manifest_path)
    elif corruption == "visibility":
        manifest = EnterpriseArtifactManifestV1.model_validate_json(
            manifest_path.read_bytes()
        ).model_copy(update={"visibility": "evaluator"})
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    elif corruption == "manifest_count":
        manifest = EnterpriseArtifactManifestV1.model_validate_json(
            manifest_path.read_bytes()
        ).model_copy(update={"artifacts": ()})
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    elif corruption.startswith("descriptor_"):
        manifest = EnterpriseArtifactManifestV1.model_validate_json(
            manifest_path.read_bytes()
        )
        updates_by_corruption: dict[str, dict[str, object]] = {
            "descriptor_path": {"path": "wrong.json"},
            "descriptor_schema": {"schema_version": "9.9.9"},
            "descriptor_size": {"byte_size": 0},
            "descriptor_digest": {"digest": synthetic_digest(b"wrong\n")},
        }
        descriptor = manifest.artifacts[0].model_copy(
            update=updates_by_corruption[corruption]
        )
        manifest_path.write_bytes(
            canonical_json_bytes(
                manifest.model_copy(update={"artifacts": (descriptor,)})
            )
        )
    elif corruption == "invalid_json":
        artifact_path.write_bytes(b"{")
    else:
        artifact_path.write_bytes(b" " + artifact_path.read_bytes())
    with pytest.raises(EnterpriseAgenticArtifactError, match=message):
        load_public_enterprise_agentic_benchmark(root)


def test_evaluator_loader_recompiles_component_and_agentic_truth(
    tmp_path: Path,
) -> None:
    reference = reference_enterprise_agentic()
    component_root = tmp_path / "component"
    export_enterprise_agentic_benchmark(
        component_root, public=reference.public, evaluator=reference.evaluator
    )
    changed_rbac = reference.evaluator.directory_rbac_truth.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"wrong\n")}
    )
    changed_evaluator = reference.evaluator.model_copy(
        update={"directory_rbac_truth": changed_rbac}
    )
    _rewrite_artifact(
        component_root,
        visibility="evaluator",
        name="enterprise-agentic-evaluator.json",
        model=changed_evaluator,
    )
    with pytest.raises(EnterpriseAgenticArtifactError, match="bindings are invalid"):
        load_evaluator_enterprise_agentic_benchmark(component_root)

    truth_root = tmp_path / "truth"
    export_enterprise_agentic_benchmark(
        truth_root, public=reference.public, evaluator=reference.evaluator
    )
    first_label = reference.evaluator.truth.case_labels[0]
    changed_label = first_label.model_copy(update={"scenario_tags": ("changed",)})
    changed_truth = reference.evaluator.truth.model_copy(
        update={
            "case_labels": (
                changed_label,
                *reference.evaluator.truth.case_labels[1:],
            )
        }
    )
    changed_evaluator = reference.evaluator.model_copy(update={"truth": changed_truth})
    _rewrite_artifact(
        truth_root,
        visibility="evaluator",
        name="enterprise-agentic-evaluator.json",
        model=changed_evaluator,
    )
    with pytest.raises(EnterpriseAgenticArtifactError, match="truth differs"):
        load_evaluator_enterprise_agentic_benchmark(truth_root)


def test_generated_schemas_and_examples_match_reference_contracts() -> None:
    reference = reference_enterprise_agentic()
    prediction = perfect_enterprise_agentic_prediction(reference.evaluator)
    metrics = evaluate_enterprise_agentic_prediction(
        public=reference.public,
        evaluator=reference.evaluator,
        prediction=prediction,
    )
    models = {
        "enterprise-agentic-benchmark": reference.public.benchmark,
        "enterprise-agentic-public-input": reference.public,
        "enterprise-agentic-truth": reference.evaluator.truth,
        "enterprise-agentic-evaluator": reference.evaluator,
        "enterprise-agentic-prediction": prediction,
        "enterprise-agentic-metrics": metrics,
    }
    for stem, model in models.items():
        schema = json.loads(
            (CONTRACT_ROOT / "schemas" / f"{stem}.schema.json").read_text()
        )
        errors = tuple(
            Draft202012Validator(schema).iter_errors(model.model_dump(mode="json"))
        )
        assert errors == ()
    examples = {
        "enterprise-agentic-public-input.json": reference.public,
        "enterprise-agentic-evaluator.json": reference.evaluator,
        "enterprise-agentic-prediction.json": prediction,
        "enterprise-agentic-metrics.json": metrics,
    }
    for name, model in examples.items():
        assert (CONTRACT_ROOT / "examples" / name).read_bytes() == canonical_json_bytes(
            model
        )


def test_jsonl_round_trip_and_public_validation() -> None:
    reference = reference_enterprise_agentic()
    prediction = perfect_enterprise_agentic_prediction(reference.evaluator)
    serialized = enterprise_agentic_trace_to_jsonl(prediction)
    assert serialized.endswith("\n")
    assert enterprise_agentic_trace_from_jsonl(serialized) == prediction
    report = validate_enterprise_agentic_trace_jsonl(
        serialized, public=reference.public
    )
    assert report.valid
    assert report.row_count == report.expected_case_count == 20
    assert report.issues == ()


def test_jsonl_parser_rejects_empty_invalid_and_mixed_benchmark_rows() -> None:
    reference = reference_enterprise_agentic()
    prediction = perfect_enterprise_agentic_prediction(reference.evaluator)
    with pytest.raises(EnterpriseAgenticEvaluationError, match="empty"):
        enterprise_agentic_trace_from_jsonl("\n")
    with pytest.raises(EnterpriseAgenticEvaluationError, match="row 1"):
        enterprise_agentic_trace_from_jsonl("{\n")
    wrong = prediction.rows[0].model_copy(
        update={"benchmark_digest": synthetic_digest(b"wrong\n")}
    )
    mixed = "".join(
        (
            f"{wrong.model_dump_json()}\n",
            f"{prediction.rows[1].model_dump_json()}\n",
        )
    )
    with pytest.raises(EnterpriseAgenticEvaluationError, match="different benchmarks"):
        enterprise_agentic_trace_from_jsonl(mixed)


def test_public_validator_reports_all_cardinality_and_binding_errors() -> None:
    reference = reference_enterprise_agentic()
    prediction = perfect_enterprise_agentic_prediction(reference.evaluator)
    first = prediction.rows[0]
    unknown = first.model_copy(update={"case_id": "unknown-case"})
    wrong_digest = prediction.rows[1].model_copy(
        update={"benchmark_digest": synthetic_digest(b"wrong\n")}
    )
    serialized = "".join(
        (
            "{\n",
            f"{first.model_dump_json()}\n",
            f"{first.model_dump_json()}\n",
            f"{unknown.model_dump_json()}\n",
            f"{wrong_digest.model_dump_json()}\n",
        )
    )
    report = validate_enterprise_agentic_trace_jsonl(
        serialized, public=reference.public
    )
    assert not report.valid
    codes = Counter(item.code for item in report.issues)
    assert codes["invalid_row"] == 1
    assert codes["duplicate_case_id"] == 1
    assert codes["unexpected_case_id"] == 1
    assert codes["benchmark_digest_mismatch"] >= 1
    assert codes["missing_case_id"] >= 1


def test_cli_generates_validates_and_scores_enterprise_agentic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "world"
    assert (
        main(
            [
                "generate-enterprise-agentic",
                "--seed",
                "20260804",
                "--tier",
                "smoke",
                "--output",
                str(root),
            ]
        )
        == 0
    )
    assert "20 cases" in capsys.readouterr().out
    evaluator = load_evaluator_enterprise_agentic_benchmark(root)
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        enterprise_agentic_trace_to_jsonl(
            perfect_enterprise_agentic_prediction(evaluator)
        )
    )
    assert (
        main(
            [
                "validate",
                "enterprise-agentic-trace",
                "--benchmark-root",
                str(root),
                "--predictions",
                str(trace_path),
            ]
        )
        == 0
    )
    assert "enterprise-agentic-trace: valid" in capsys.readouterr().out
    assert (
        main(
            [
                "validate",
                "enterprise-agentic-trace",
                "--benchmark-root",
                str(root),
                "--predictions",
                str(trace_path),
                "--json",
            ]
        )
        == 0
    )
    validation_json = json.loads(capsys.readouterr().out)
    assert validation_json["valid"] is True
    assert (
        main(
            [
                "evaluate",
                "enterprise-agentic",
                "--benchmark-root",
                str(root),
                "--predictions",
                str(trace_path),
                "--summary",
            ]
        )
        == 0
    )
    assert "final_decision_accuracy" in capsys.readouterr().out
    assert (
        main(
            [
                "evaluate",
                "enterprise-agentic",
                "--benchmark-root",
                str(root),
                "--predictions",
                str(trace_path),
            ]
        )
        == 0
    )
    metrics_json = json.loads(capsys.readouterr().out)
    assert metrics_json["schema_version"] == "1.0.0"


def test_cli_reports_enterprise_agentic_input_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"
    trace = tmp_path / "trace.jsonl"
    trace.write_text("{}\n")
    assert (
        main(
            [
                "validate",
                "enterprise-agentic-trace",
                "--benchmark-root",
                str(missing),
                "--predictions",
                str(trace),
            ]
        )
        == 1
    )
    assert capsys.readouterr().err
    assert (
        main(
            [
                "evaluate",
                "enterprise-agentic",
                "--predictions",
                str(trace),
            ]
        )
        == 1
    )
    assert "--benchmark-root is required" in capsys.readouterr().err


def test_evaluator_artifact_model_rejects_its_digest_bindings() -> None:
    reference = reference_enterprise_agentic()
    document = reference.evaluator.model_dump(mode="python")
    document["public_input_digest"] = synthetic_digest(b"wrong public\n")
    with pytest.raises(ValueError, match="truth_public_digest"):
        EnterpriseAgenticEvaluatorArtifactsV1.model_validate(document)
    changed_truth = reference.evaluator.truth.model_copy(
        update={"access_state_digest": synthetic_digest(b"wrong state\n")}
    )
    document = reference.evaluator.model_dump(mode="python")
    document["truth"] = changed_truth
    with pytest.raises(ValueError, match="access_state_digest"):
        EnterpriseAgenticEvaluatorArtifactsV1.model_validate(document)
