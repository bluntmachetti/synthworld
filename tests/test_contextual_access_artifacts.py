"""Artifact, JSONL, schema, metric, and CLI tests for contextual access."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel

import synthworld.contextual_access.serialization as serialization_module
from synthworld.cli import main
from synthworld.contextual_access.metrics import (
    ContextualAccessEvaluationError,
    evaluate_contextual_access_prediction,
    perfect_contextual_access_prediction,
)
from synthworld.contextual_access.models import (
    ContextualAccessEvaluatorV1,
    ContextualAccessMetricsV1,
    ContextualAccessPredictionV1,
    ContextualAccessPublicV1,
    ContextualObjectRegistryV1,
)
from synthworld.contextual_access.projection import ContextualAccessIntegrityError
from synthworld.contextual_access.protocol import (
    ContextualAccessObservationsV1,
    ContextualAccessReportV1,
    ContextualAccessRunPlanV1,
    ContextualAccessRunTruthV1,
)
from synthworld.contextual_access.protocol_reference import (
    reference_contextual_access_run,
)
from synthworld.contextual_access.reference import reference_contextual_access
from synthworld.contextual_access.serialization import (
    ContextualAccessArtifactError,
    export_contextual_access_benchmark,
    load_evaluator_contextual_access_benchmark,
    load_public_contextual_access_benchmark,
)
from synthworld.contextual_access.shared_signals import (
    ContextualSharedSignalsMappingProfileV1,
    ContextualSharedSignalsProjectionV1,
    contextual_shared_signals_mapping_profile_v1,
    project_contextual_shared_signals,
)
from synthworld.contextual_access.trace import (
    contextual_access_trace_from_jsonl,
    contextual_access_trace_to_jsonl,
    validate_contextual_access_trace_jsonl,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseArtifactManifestV1
from synthworld.temporal_schedule import TemporalEventEnvelopeV1, TemporalScheduleV1

CONTRACT_ROOT = Path("contextual-access-contract")


def _rewrite_artifact(
    root: Path,
    *,
    visibility: Literal["public", "evaluator"],
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
    reference = reference_contextual_access()
    root = tmp_path / "contextual-access"
    export_contextual_access_benchmark(
        root, public=reference.public, evaluator=reference.evaluator
    )
    assert load_public_contextual_access_benchmark(root) == reference.public
    assert load_evaluator_contextual_access_benchmark(root) == reference.evaluator
    assert {
        str(item.relative_to(root)) for item in root.rglob("*") if item.is_file()
    } == {
        "public/contextual-access-input.json",
        "public/manifest.json",
        "evaluator/contextual-access-evaluator.json",
        "evaluator/manifest.json",
    }
    public_bytes = (root / "public" / "contextual-access-input.json").read_bytes()
    assert public_bytes == canonical_json_bytes(reference.public)
    assert b'"case_labels"' not in public_bytes
    assert b'"expected_decision"' not in public_bytes

    (root / "evaluator" / "contextual-access-evaluator.json").write_bytes(b"{")
    assert load_public_contextual_access_benchmark(root) == reference.public
    with pytest.raises(ContextualAccessArtifactError, match="invalid"):
        load_evaluator_contextual_access_benchmark(root)


def test_export_rejects_existing_destination(tmp_path: Path) -> None:
    reference = reference_contextual_access()
    root = tmp_path / "existing"
    root.mkdir()
    with pytest.raises(ContextualAccessArtifactError, match="root exists"):
        export_contextual_access_benchmark(
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
        ("invalid_manifest", "artifact is invalid"),
        ("noncanonical", "not canonical JSON"),
    ),
)
def test_public_loader_rejects_each_physical_corruption(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    reference = reference_contextual_access()
    root = tmp_path / corruption
    if corruption == "missing":
        with pytest.raises(ContextualAccessArtifactError, match=message):
            load_public_contextual_access_benchmark(root)
        return
    if corruption == "not_directory":
        root.mkdir()
        (root / "public").write_text("not a directory\n")
        with pytest.raises(ContextualAccessArtifactError, match=message):
            load_public_contextual_access_benchmark(root)
        return
    export_contextual_access_benchmark(
        root, public=reference.public, evaluator=reference.evaluator
    )
    public_root = root / "public"
    manifest_path = public_root / "manifest.json"
    artifact_path = public_root / "contextual-access-input.json"
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
    elif corruption == "invalid_manifest":
        manifest_path.write_bytes(b"{")
    else:
        artifact_path.write_bytes(b" " + artifact_path.read_bytes())
    with pytest.raises(ContextualAccessArtifactError, match=message):
        load_public_contextual_access_benchmark(root)


def test_loaders_wrap_binding_failures_and_detect_recompile_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = reference_contextual_access()
    root = tmp_path / "world"
    export_contextual_access_benchmark(
        root, public=reference.public, evaluator=reference.evaluator
    )

    def fail_public(_: ContextualAccessPublicV1) -> None:
        raise ContextualAccessIntegrityError("broken public")

    monkeypatch.setattr(
        serialization_module, "validate_contextual_access_public", fail_public
    )
    with pytest.raises(ContextualAccessArtifactError, match="public bindings"):
        load_public_contextual_access_benchmark(root)
    monkeypatch.setattr(
        serialization_module,
        "validate_contextual_access_public",
        lambda _: None,
    )

    def fail_compile(**_: object) -> ContextualAccessEvaluatorV1:
        raise ContextualAccessIntegrityError("broken truth")

    monkeypatch.setattr(
        serialization_module, "compile_contextual_access_truth", fail_compile
    )
    with pytest.raises(ContextualAccessArtifactError, match="evaluator/public"):
        load_evaluator_contextual_access_benchmark(root)
    monkeypatch.setattr(
        serialization_module,
        "compile_contextual_access_truth",
        lambda **_: reference.evaluator.model_copy(update={"schema_version": "drift"}),
    )
    with pytest.raises(ContextualAccessArtifactError, match="compiled truth"):
        load_evaluator_contextual_access_benchmark(root)


def test_generated_schemas_and_examples_match_reference_contracts() -> None:
    benchmark = reference_contextual_access()
    prediction = perfect_contextual_access_prediction(
        public=benchmark.public, evaluator=benchmark.evaluator
    )
    metrics = evaluate_contextual_access_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        prediction=prediction,
    )
    run = reference_contextual_access_run()
    profile = contextual_shared_signals_mapping_profile_v1()
    projection = project_contextual_shared_signals(benchmark.public, profile=profile)
    schedule = TemporalScheduleV1(
        event_schedule_version=benchmark.public.benchmark.event_schedule_version,
        events=benchmark.public.schedule,
    )
    models: dict[str, BaseModel] = {
        "temporal-event-envelope-v1": benchmark.public.schedule[0],
        "temporal-schedule-v1": schedule,
        "contextual-access-config": benchmark.config,
        "contextual-object-registry": benchmark.public.registry,
        "contextual-access-public": benchmark.public,
        "contextual-access-evaluator": benchmark.evaluator,
        "contextual-access-prediction": prediction,
        "contextual-access-metrics": metrics,
        "contextual-access-run-plan": run.plan,
        "contextual-access-observations": run.observations,
        "contextual-access-run-truth": run.truth,
        "contextual-access-report": run.report,
        "contextual-shared-signals-mapping-profile": profile,
        "contextual-shared-signals-projection": projection,
    }
    expected_types: dict[str, type[BaseModel]] = {
        "temporal-event-envelope-v1": TemporalEventEnvelopeV1,
        "temporal-schedule-v1": TemporalScheduleV1,
        "contextual-access-public": ContextualAccessPublicV1,
        "contextual-access-evaluator": ContextualAccessEvaluatorV1,
        "contextual-access-prediction": ContextualAccessPredictionV1,
        "contextual-access-metrics": ContextualAccessMetricsV1,
        "contextual-access-run-plan": ContextualAccessRunPlanV1,
        "contextual-access-observations": ContextualAccessObservationsV1,
        "contextual-access-run-truth": ContextualAccessRunTruthV1,
        "contextual-access-report": ContextualAccessReportV1,
        "contextual-shared-signals-mapping-profile": (
            ContextualSharedSignalsMappingProfileV1
        ),
        "contextual-shared-signals-projection": ContextualSharedSignalsProjectionV1,
        "contextual-object-registry": ContextualObjectRegistryV1,
    }
    for stem, model in models.items():
        schema = json.loads(
            (CONTRACT_ROOT / "schemas" / f"{stem}.schema.json").read_text()
        )
        assert schema["x-generated-from"] == (
            f"{expected_types.get(stem, type(model)).__module__}."
            f"{expected_types.get(stem, type(model)).__name__}"
        )
        errors = tuple(
            Draft202012Validator(schema).iter_errors(model.model_dump(mode="json"))
        )
        assert errors == ()
    examples = {
        "contextual-access-config.json": benchmark.config,
        "contextual-access-public.json": benchmark.public,
        "contextual-access-evaluator.json": benchmark.evaluator,
        "contextual-access-prediction.json": prediction,
        "contextual-access-metrics.json": metrics,
        "contextual-access-run-plan.json": run.plan,
        "contextual-access-observations.json": run.observations,
        "contextual-access-run-truth.json": run.truth,
        "contextual-access-report.json": run.report,
        "contextual-shared-signals-mapping-profile.json": profile,
        "contextual-shared-signals-projection.json": projection,
    }
    for name, model in examples.items():
        assert (CONTRACT_ROOT / "examples" / name).read_bytes() == canonical_json_bytes(
            model
        )


def test_jsonl_round_trip_parser_failures_and_public_validation() -> None:
    reference = reference_contextual_access()
    prediction = perfect_contextual_access_prediction(
        public=reference.public, evaluator=reference.evaluator
    )
    serialized = contextual_access_trace_to_jsonl(prediction)
    assert serialized.endswith("\n")
    assert contextual_access_trace_from_jsonl("\n" + serialized) == prediction
    report = validate_contextual_access_trace_jsonl(serialized, public=reference.public)
    assert report.valid
    assert report.row_count == report.expected_request_count == 10
    assert report.issues == ()

    with pytest.raises(ContextualAccessEvaluationError, match="empty"):
        contextual_access_trace_from_jsonl("\n")
    with pytest.raises(ContextualAccessEvaluationError, match="row 1"):
        contextual_access_trace_from_jsonl("{\n")
    wrong = prediction.rows[0].model_copy(
        update={"benchmark_digest": synthetic_digest(b"wrong\n")}
    )
    mixed = f"{wrong.model_dump_json()}\n{prediction.rows[1].model_dump_json()}\n"
    with pytest.raises(ContextualAccessEvaluationError, match="different benchmarks"):
        contextual_access_trace_from_jsonl(mixed)


def test_public_trace_validator_reports_all_recoverable_errors() -> None:
    reference = reference_contextual_access()
    prediction = perfect_contextual_access_prediction(
        public=reference.public, evaluator=reference.evaluator
    )
    first = prediction.rows[0]
    unknown = first.model_copy(update={"request_id": "unknown-request"})
    wrong_digest = prediction.rows[1].model_copy(
        update={"benchmark_digest": synthetic_digest(b"wrong\n")}
    )
    recoverable_invalid = json.dumps(
        {"request_id": prediction.rows[2].request_id, "decision": "invalid"}
    )
    non_string_request = json.dumps({"request_id": 7})
    serialized = "".join(
        (
            "\n",
            "{\n",
            "[]\n",
            f"{non_string_request}\n",
            f"{recoverable_invalid}\n",
            f"{first.model_dump_json()}\n",
            f"{first.model_dump_json()}\n",
            f"{unknown.model_dump_json()}\n",
            f"{wrong_digest.model_dump_json()}\n",
        )
    )
    report = validate_contextual_access_trace_jsonl(serialized, public=reference.public)
    assert not report.valid
    codes = Counter(item.code for item in report.issues)
    assert codes["invalid_row"] == 4
    assert codes["duplicate_request_id"] == 1
    assert codes["unexpected_request_id"] == 1
    assert codes["benchmark_digest_mismatch"] == 1
    assert codes["missing_request_id"] > 0


def test_metrics_reject_unbound_or_incomplete_inventories_and_handle_no_evidence() -> (
    None
):
    reference = reference_contextual_access()
    prediction = perfect_contextual_access_prediction(
        public=reference.public, evaluator=reference.evaluator
    )
    wrong_digest = synthetic_digest(b"wrong\n")
    with pytest.raises(ContextualAccessEvaluationError, match="digest differs"):
        evaluate_contextual_access_prediction(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=prediction.model_copy(update={"benchmark_digest": wrong_digest}),
        )
    wrong_row = prediction.rows[0].model_copy(update={"benchmark_digest": wrong_digest})
    with pytest.raises(ContextualAccessEvaluationError, match="digest differs"):
        evaluate_contextual_access_prediction(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=prediction.model_copy(
                update={"rows": (wrong_row, *prediction.rows[1:])}
            ),
        )
    with pytest.raises(ContextualAccessEvaluationError, match="cover every request"):
        evaluate_contextual_access_prediction(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=prediction.model_copy(update={"rows": prediction.rows[:-1]}),
        )
    with pytest.raises(ContextualAccessEvaluationError, match="inventory differs"):
        evaluate_contextual_access_prediction(
            public=reference.public.model_copy(
                update={"requests": reference.public.requests[:-1]}
            ),
            evaluator=reference.evaluator,
            prediction=prediction,
        )
    changed_truth = reference.evaluator.truth.model_copy(
        update={"case_labels": reference.evaluator.truth.case_labels[:-1]}
    )
    with pytest.raises(ContextualAccessEvaluationError, match="inventory differs"):
        evaluate_contextual_access_prediction(
            public=reference.public,
            evaluator=reference.evaluator.model_copy(update={"truth": changed_truth}),
            prediction=prediction,
        )

    no_evidence = prediction.model_copy(
        update={
            "rows": tuple(
                item.model_copy(update={"evidence_refs": ()})
                for item in prediction.rows
            )
        }
    )
    metrics = evaluate_contextual_access_prediction(
        public=reference.public,
        evaluator=reference.evaluator,
        prediction=no_evidence,
    )
    evidence_precision = next(
        item for item in metrics.metrics if item.name == "evidence_precision"
    )
    assert evidence_precision.denominator == 0
    assert evidence_precision.value is None


def test_cli_generates_validates_scores_and_checks_run_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "world"
    assert (
        main(
            [
                "generate-contextual-access",
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
    assert "10 cases" in capsys.readouterr().out
    public = load_public_contextual_access_benchmark(root)
    evaluator = load_evaluator_contextual_access_benchmark(root)
    prediction = perfect_contextual_access_prediction(
        public=public, evaluator=evaluator
    )
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(contextual_access_trace_to_jsonl(prediction))
    assert (
        main(
            [
                "validate",
                "contextual-access-trace",
                "--benchmark-root",
                str(root),
                "--predictions",
                str(trace_path),
            ]
        )
        == 0
    )
    assert "contextual-access-trace: valid" in capsys.readouterr().out
    assert (
        main(
            [
                "validate",
                "contextual-access-trace",
                "--benchmark-root",
                str(root),
                "--predictions",
                str(trace_path),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["valid"] is True
    for summary in (False, True):
        arguments = [
            "evaluate",
            "contextual-access",
            "--benchmark-root",
            str(root),
            "--predictions",
            str(trace_path),
        ]
        if summary:
            arguments.append("--summary")
        assert main(arguments) == 0
        output = capsys.readouterr().out
        assert (
            "decision_accuracy" in output
            if summary
            else json.loads(output)["schema_version"] == "1.0.0"
        )

    run = reference_contextual_access_run()
    plan_path = tmp_path / "run-plan.json"
    plan_path.write_text(run.plan.model_dump_json(indent=2))
    assert (
        main(
            [
                "validate",
                "contextual-access-run-plan",
                "--input",
                str(plan_path),
            ]
        )
        == 0
    )
    assert "structurally valid" in capsys.readouterr().out


def test_cli_reports_contextual_access_input_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"
    trace = tmp_path / "trace.jsonl"
    trace.write_text("{}\n")
    assert (
        main(
            [
                "validate",
                "contextual-access-trace",
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
                "contextual-access",
                "--predictions",
                str(trace),
            ]
        )
        == 1
    )
    assert "--benchmark-root is required" in capsys.readouterr().err

    existing = tmp_path / "existing"
    existing.mkdir()
    assert main(["generate-contextual-access", "--output", str(existing)]) == 1
    assert "root exists" in capsys.readouterr().err

    bad_plan = tmp_path / "bad-plan.json"
    bad_plan.write_text("{}\n")
    assert (
        main(
            [
                "validate",
                "contextual-access-run-plan",
                "--input",
                str(bad_plan),
            ]
        )
        == 1
    )
    assert capsys.readouterr().err

    reference = reference_contextual_access()
    root = tmp_path / "valid-world"
    export_contextual_access_benchmark(
        root, public=reference.public, evaluator=reference.evaluator
    )
    assert (
        main(
            [
                "validate",
                "contextual-access-trace",
                "--benchmark-root",
                str(root),
                "--predictions",
                str(trace),
            ]
        )
        == 1
    )
    assert "contextual-access-trace: invalid" in capsys.readouterr().out
