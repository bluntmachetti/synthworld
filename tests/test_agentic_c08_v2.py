from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Protocol, cast

import pytest
from pydantic import ValidationError

from synthworld.agentic.c08_v2 import (
    C08ArtifactError,
    C08AsteriaBenchmarkV2,
    C08AsteriaSubmissionV2,
    C08EvaluationError,
    C08MetricV2,
    C08MetricsReportV2,
    C08SubmissionRowV2,
    build_c08_evaluator_artifacts,
    build_c08_public_artifacts,
    build_c08_submission_artifacts,
    evaluate_c08_submission,
    generate_c08_asteria_v2,
    load_c08_bundle,
    load_c08_evaluator_artifacts,
    load_c08_public_artifacts,
    load_c08_submission_artifacts,
    reference_c08_submission,
    semantic_c08_submission,
)
from synthworld.enterprise.canonical import canonical_json_bytes


def _benchmark() -> C08AsteriaBenchmarkV2:
    return generate_c08_asteria_v2(7)


class _SchemaTool(Protocol):
    def schema_documents(self) -> dict[str, bytes]: ...

    def check_schema_directory(self, directory: Path) -> None: ...


def _schema_tool() -> _SchemaTool:
    path = (
        Path(__file__).parents[1]
        / "agent-authority-contract/tools/generate_c08_v2_schemas.py"
    )
    spec = importlib.util.spec_from_file_location("generate_c08_v2_schemas", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_SchemaTool, module)


def _metric(report: C08MetricsReportV2, name: str) -> C08MetricV2:
    return next(item for item in report.metrics if item.name == name)


def _changed_submission(
    benchmark: C08AsteriaBenchmarkV2,
    action_index: int,
    additions: tuple[str, ...],
) -> C08AsteriaSubmissionV2:
    reference = reference_c08_submission(benchmark)
    rows = list(reference.rows)
    row = rows[action_index]
    rows[action_index] = row.model_copy(
        update={
            "retained_observation_ids": (
                *row.retained_observation_ids,
                *additions,
            )
        }
    )
    return reference.model_copy(update={"rows": tuple(rows)})


def test_generation_is_deterministic_and_scope_is_honest() -> None:
    first = _benchmark()
    second = _benchmark()
    assert first == second
    assert first.public.measurement_scope.offline_artifacts_only is True
    assert (
        "production logging behavior"
        in first.public.measurement_scope.does_not_prove
    )
    public_json = first.public.model_dump_json()
    assert "required_observation_ids" not in public_json
    assert "scenario_kind" not in public_json
    assert "availability" not in public_json
    assert first.evaluator.bindings


def test_models_are_immutable_and_forbid_extra_fields() -> None:
    benchmark = _benchmark()
    with pytest.raises(ValidationError, match="frozen"):
        benchmark.public.actions[0].action = "write"
    with pytest.raises(ValidationError, match="extra"):
        benchmark.public.model_validate(
            {**benchmark.public.model_dump(mode="json"), "expected_labels": []}
        )
    with pytest.raises(ValidationError, match="extra"):
        benchmark.evaluator.model_validate(
            {**benchmark.evaluator.model_dump(mode="json"), "public_labels": []}
        )
    with pytest.raises(ValidationError, match="extra"):
        C08AsteriaSubmissionV2.model_validate(
            {
                "benchmark_id": "asteria-agentic-c08-v2",
                "public_input_digest": "0" * 64,
                "rows": [],
                "unexpected": True,
            }
        )


def test_public_evaluator_submission_artifacts_are_separate_and_bound() -> None:
    benchmark = _benchmark()
    public_artifacts = build_c08_public_artifacts(benchmark.public)
    evaluator_artifacts = build_c08_evaluator_artifacts(benchmark.evaluator)
    submission_artifacts = build_c08_submission_artifacts(
        reference_c08_submission(benchmark)
    )
    assert set(public_artifacts) == {
        "c08-asteria-public.json",
        "manifest.json",
    }
    assert set(evaluator_artifacts) == {
        "c08-asteria-evaluator.json",
        "manifest.json",
    }
    assert set(submission_artifacts) == {
        "c08-asteria-submission.json",
        "manifest.json",
    }
    assert b"required_observation_ids" not in public_artifacts[
        "c08-asteria-public.json"
    ]
    assert all(payload.endswith(b"\n") for payload in public_artifacts.values())
    assert load_c08_bundle(
        public_artifacts, evaluator_artifacts, submission_artifacts
    ) == benchmark
    assert load_c08_public_artifacts(public_artifacts) == benchmark.public
    assert load_c08_evaluator_artifacts(evaluator_artifacts) == benchmark.evaluator
    assert load_c08_submission_artifacts(
        submission_artifacts, public=benchmark.public
    ) == reference_c08_submission(benchmark)


def test_public_requirement_semantics_construct_a_reference_without_exact_truth(
) -> None:
    benchmark = _benchmark()
    semantic_submission = semantic_c08_submission(benchmark.public)
    assert semantic_submission == reference_c08_submission(benchmark)
    assert all(action.required_evidence_kinds for action in benchmark.public.actions)
    assert all(
        "required_observation_ids" not in action.model_dump(mode="json")
        and "scenario_kind" not in action.model_dump(mode="json")
        for action in benchmark.public.actions
    )
    extra_action = next(
        action
        for action in benchmark.public.actions
        if action.resource_id == "resource-005"
    )
    extra_observations = tuple(
        item
        for item in benchmark.public.evidence_observations
        if item.action_event_id == extra_action.action_event_id
    )
    assert tuple(item.evidence_kind.value for item in extra_observations) == (
        "authority_record",
        "policy_record",
    )


def test_evaluator_bindings_match_public_action_and_required_kinds() -> None:
    benchmark = _benchmark()
    binding = benchmark.evaluator.bindings[0]
    other_observation = next(
        item
        for item in benchmark.public.evidence_observations
        if item.action_event_id != binding.action_event_id
    )
    crossed_binding = binding.model_copy(
        update={"required_observation_ids": (other_observation.observation_id,)}
    )
    crossed_evaluator = benchmark.evaluator.model_copy(
        update={
            "bindings": (crossed_binding, *benchmark.evaluator.bindings[1:]),
        }
    )
    with pytest.raises(ValidationError, match="crosses public actions"):
        C08AsteriaBenchmarkV2(
            schema_version=benchmark.schema_version,
            benchmark_id=benchmark.benchmark_id,
            public=benchmark.public,
            evaluator=crossed_evaluator,
        )

    incomplete_binding = binding.model_copy(
        update={"required_observation_ids": (binding.required_observation_ids[0],)}
    )
    incomplete_evaluator = benchmark.evaluator.model_copy(
        update={
            "bindings": (incomplete_binding, *benchmark.evaluator.bindings[1:]),
        }
    )
    with pytest.raises(ValidationError, match="evidence kinds"):
        C08AsteriaBenchmarkV2(
            schema_version=benchmark.schema_version,
            benchmark_id=benchmark.benchmark_id,
            public=benchmark.public,
            evaluator=incomplete_evaluator,
        )


def test_manifest_and_cross_tree_digest_fail_closed() -> None:
    benchmark = _benchmark()
    public = build_c08_public_artifacts(benchmark.public)
    tampered_public = dict(public)
    tampered_public["c08-asteria-public.json"] += b" "
    with pytest.raises(C08ArtifactError, match=r"noncanonical|manifest"):
        load_c08_public_artifacts(tampered_public)
    changed_digest = "0" * 64
    if changed_digest == benchmark.evaluator.public_input_digest:
        changed_digest = "1" * 64
    tampered_evaluator = build_c08_evaluator_artifacts(
        benchmark.evaluator.model_copy(update={"public_input_digest": changed_digest})
    )
    with pytest.raises(C08ArtifactError):
        load_c08_bundle(public, tampered_evaluator)
    with pytest.raises(C08ArtifactError, match="inventory"):
        load_c08_public_artifacts({**public, "unexpected.json": b"{}\n"})


def test_reference_submission_scores_each_dimension_independently() -> None:
    benchmark = _benchmark()
    report = evaluate_c08_submission(benchmark, reference_c08_submission(benchmark))
    assert all(item.value == 1.0 for item in report.metrics)
    assert {item.denominator for item in report.metrics} == {6}
    assert report.measurement_scope.offline_artifacts_only is True


@pytest.mark.parametrize(
    ("action_index", "addition", "metric_name"),
    [
        (1, (), "exact_evidence_match"),
        (2, ("fabricated-observation",), "fabricated_evidence_free"),
        (3, (), "wrong_action_evidence_free"),
        (4, (), "extra_evidence_free"),
    ],
)
def test_missing_fabricated_wrong_action_and_extra_are_distinguished(
    action_index: int,
    addition: tuple[str, ...],
    metric_name: str,
) -> None:
    benchmark = _benchmark()
    reference = reference_c08_submission(benchmark)
    if action_index == 1:
        row = reference.rows[action_index]
        changed = reference.model_copy(
            update={
                "rows": (
                    *reference.rows[:action_index],
                    row.model_copy(
                        update={
                            "retained_observation_ids": (
                                row.retained_observation_ids[:-1]
                            )
                        }
                    ),
                    *reference.rows[action_index + 1 :],
                )
            }
        )
    elif action_index == 3:
        other = reference.rows[0].retained_observation_ids[0]
        changed = _changed_submission(benchmark, action_index, (other,))
    elif action_index == 4:
        observations = [
            item
            for item in benchmark.public.evidence_observations
            if item.action_event_id == reference.rows[action_index].action_event_id
        ]
        changed = _changed_submission(
            benchmark, action_index, (observations[-1].observation_id,)
        )
    else:
        changed = _changed_submission(benchmark, action_index, addition)
    report = evaluate_c08_submission(benchmark, changed)
    assert _metric(report, metric_name).value is not None
    assert _metric(report, metric_name).value < 1.0


def test_discarded_scenario_is_not_distinguishable_from_missing_submission() -> None:
    benchmark = _benchmark()
    binding = benchmark.evaluator.bindings[-1]
    reference = reference_c08_submission(benchmark)
    changed = reference.model_copy(
        update={
            "rows": (
                *reference.rows[:-1],
                reference.rows[-1].model_copy(
                    update={"retained_observation_ids": ()}
                ),
            )
        }
    )
    report = evaluate_c08_submission(benchmark, changed)
    assert _metric(report, "missing_or_discarded_free").value == 5 / 6
    assert binding.scenario_kind.value == "discarded"
    assert reference.rows[-1].retained_observation_ids


def test_empty_evidence_has_explicit_undefined_support() -> None:
    benchmark = _benchmark()
    empty = C08AsteriaSubmissionV2(
        public_input_digest=hashlib.sha256(
            canonical_json_bytes(benchmark.public)
        ).hexdigest(),
        rows=tuple(
            C08SubmissionRowV2(
                action_event_id=action.action_event_id,
                retained_observation_ids=(),
            )
            for action in benchmark.public.actions
        )
    )
    report = evaluate_c08_submission(benchmark, empty)
    assert _metric(report, "exact_evidence_match").value == 0.0
    for name in (
        "fabricated_evidence_free",
        "wrong_action_evidence_free",
        "extra_evidence_free",
    ):
        metric = _metric(report, name)
        assert metric.value is None
        assert metric.denominator == 0
        assert metric.undefined_reason


def test_submission_alignment_and_model_ordering_are_fail_closed() -> None:
    benchmark = _benchmark()
    reference = reference_c08_submission(benchmark)
    reversed_rows = reference.model_copy(
        update={"rows": tuple(reversed(reference.rows))}
    )
    assert reversed_rows.rows == tuple(
        sorted(reference.rows, key=lambda item: item.action_event_id)
    )
    with pytest.raises(C08EvaluationError, match="missing"):
        evaluate_c08_submission(
            benchmark, reference.model_copy(update={"rows": reference.rows[:-1]})
        )
    unknown = C08SubmissionRowV2(action_event_id="unknown", retained_observation_ids=())
    with pytest.raises(C08EvaluationError, match="unknown"):
        evaluate_c08_submission(
            benchmark,
            reference.model_copy(update={"rows": (*reference.rows[:-1], unknown)}),
        )
    with pytest.raises(ValidationError, match="unique"):
        C08SubmissionRowV2(retained_observation_ids=("a", "a"), action_event_id="x")


def test_deterministic_digest_and_input_validation() -> None:
    benchmark = _benchmark()
    public_bytes = build_c08_public_artifacts(benchmark.public)[
        "c08-asteria-public.json"
    ]
    assert hashlib.sha256(public_bytes).hexdigest() == (
        benchmark.evaluator.public_input_digest
    )
    assert generate_c08_asteria_v2(8) != benchmark
    with pytest.raises(TypeError, match="integer"):
        generate_c08_asteria_v2(True)
    with pytest.raises(ValueError, match="nonnegative"):
        generate_c08_asteria_v2(-1)


def test_submission_digest_rejects_cross_public_replay_in_evaluation_and_loading(
) -> None:
    source = _benchmark()
    target = generate_c08_asteria_v2(8)
    submission = reference_c08_submission(source)
    with pytest.raises(C08EvaluationError, match="public digest"):
        evaluate_c08_submission(target, submission)
    with pytest.raises(C08ArtifactError, match="public digest"):
        load_c08_bundle(
            build_c08_public_artifacts(target.public),
            build_c08_evaluator_artifacts(target.evaluator),
            build_c08_submission_artifacts(submission),
        )
    wrong_digest = "0" * 64
    if wrong_digest == source.evaluator.public_input_digest:
        wrong_digest = "1" * 64
    tampered_benchmark = source.model_copy(
        update={
            "evaluator": source.evaluator.model_copy(
                update={"public_input_digest": wrong_digest}
            )
        }
    )
    with pytest.raises(C08EvaluationError, match="evaluator/public digest"):
        evaluate_c08_submission(
            tampered_benchmark, reference_c08_submission(source)
        )


def test_schema_tool_is_deterministic_and_check_detects_drift_and_missing(
    tmp_path: Path,
) -> None:
    tool = _schema_tool()
    first = tool.schema_documents()
    assert first == tool.schema_documents()
    assert set(first) == {
        "c08-asteria-public-v2.schema.json",
        "c08-asteria-evaluator-v2.schema.json",
        "c08-asteria-submission-v2.schema.json",
        "c08-asteria-manifest-v2.schema.json",
        "c08-asteria-report-v2.schema.json",
    }
    for filename, payload in first.items():
        assert payload.endswith(b"\n")
        assert not payload.endswith(b"\n\n")
        assert b"\r" not in payload
        assert json.loads(payload)["$schema"] == (
            "https://json-schema.org/draft/2020-12/schema"
        )
        (tmp_path / filename).write_bytes(payload)
    tool.check_schema_directory(tmp_path)
    (tmp_path / "c08-asteria-unexpected-v2.schema.json").write_bytes(b"{}\n")
    with pytest.raises(RuntimeError, match="unexpected"):
        tool.check_schema_directory(tmp_path)
    (tmp_path / "c08-asteria-unexpected-v2.schema.json").unlink()
    report = tmp_path / "c08-asteria-report-v2.schema.json"
    report.write_bytes(b"{}\n")
    with pytest.raises(RuntimeError, match="drift"):
        tool.check_schema_directory(tmp_path)
    report.unlink()
    with pytest.raises(RuntimeError, match="missing"):
        tool.check_schema_directory(tmp_path)
