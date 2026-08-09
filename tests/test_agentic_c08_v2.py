from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

import pytest
from pydantic import ValidationError

import synthworld.agentic.c08_v2.metrics as c08_metrics
from synthworld.agentic.c08_v2 import (
    C08ArtifactError,
    C08ArtifactManifestV2,
    C08AsteriaBenchmarkV2,
    C08AsteriaEvaluatorV2,
    C08AsteriaPublicInputV2,
    C08AsteriaSubmissionV2,
    C08EvaluationError,
    C08MetricsReportV2,
    C08MetricV2,
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
from synthworld.agentic.c08_v2.models import C08ScenarioKind
from synthworld.enterprise.canonical import canonical_json_bytes, canonical_json_value_bytes


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


def _recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(_recursive_keys(item))
        return keys
    if isinstance(value, list):
        list_keys: set[str] = set()
        for item in value:
            list_keys.update(_recursive_keys(item))
        return list_keys
    return set()


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


def _row_index_for_scenario(
    benchmark: C08AsteriaBenchmarkV2, scenario: C08ScenarioKind
) -> int:
    action_id = next(
        item.action_event_id
        for item in benchmark.evaluator.bindings
        if item.scenario_kind is scenario
    )
    reference = reference_c08_submission(benchmark)
    return next(
        index
        for index, row in enumerate(reference.rows)
        if row.action_event_id == action_id
    )


def test_generation_is_deterministic_and_scope_is_honest() -> None:
    first = _benchmark()
    second = _benchmark()
    assert first == second
    assert first.public.measurement_scope.offline_artifacts_only is True
    assert (
        "live enforcement or production logging behavior"
        in first.public.measurement_scope.does_not_prove
    )
    public_keys = _recursive_keys(first.public.model_dump(mode="json"))
    assert {
        "availability",
        "bindings",
        "evaluator",
        "expected_verdict",
        "outcome",
        "required_observation_ids",
        "scenario_kind",
    }.isdisjoint(public_keys)
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
    public_keys = _recursive_keys(
        json.loads(public_artifacts["c08-asteria-public.json"])
    )
    assert {
        "availability",
        "bindings",
        "evaluator",
        "expected_verdict",
        "outcome",
        "required_observation_ids",
        "scenario_kind",
    }.isdisjoint(public_keys)
    assert all(payload.endswith(b"\n") for payload in public_artifacts.values())
    assert (
        load_c08_bundle(public_artifacts, evaluator_artifacts, submission_artifacts)
        == benchmark
    )
    assert load_c08_public_artifacts(public_artifacts) == benchmark.public
    assert load_c08_evaluator_artifacts(evaluator_artifacts) == benchmark.evaluator
    assert load_c08_submission_artifacts(
        submission_artifacts, public=benchmark.public
    ) == reference_c08_submission(benchmark)


def test_public_requirement_semantics_construct_a_reference_without_exact_truth() -> (
    None
):
    benchmark = _benchmark()
    semantic_submission = semantic_c08_submission(benchmark.public)
    assert semantic_submission == reference_c08_submission(benchmark)
    assert all(action.required_evidence for action in benchmark.public.actions)
    assert all(
        "required_observation_ids" not in action.model_dump(mode="json")
        and "scenario_kind" not in action.model_dump(mode="json")
        for action in benchmark.public.actions
    )
    for action in benchmark.public.actions:
        action_observations = tuple(
            item
            for item in benchmark.public.evidence_observations
            if item.action_event_id == action.action_event_id
        )
        for requirement in action.required_evidence:
            candidates = tuple(
                item
                for item in action_observations
                if item.evidence_kind is requirement.evidence_kind
            )
            assert len(candidates) >= 2
            assert len({item.binding_handle for item in candidates}) == len(candidates)
            matching = tuple(
                item
                for item in candidates
                if item.binding_handle == requirement.binding_handle
            )
            assert len(matching) == 1


def test_public_solver_is_order_independent_and_unsolvable_inputs_fail() -> None:
    benchmark = _benchmark()
    reordered_observations = tuple(
        observation.model_copy(update={"observation_order": index})
        for index, observation in enumerate(
            reversed(benchmark.public.evidence_observations), start=1
        )
    )
    reordered_public = C08AsteriaPublicInputV2.model_validate(
        {
            **benchmark.public.model_dump(mode="json"),
            "evidence_observations": [
                item.model_dump(mode="json") for item in reordered_observations
            ],
        }
    )
    assert semantic_c08_submission(reordered_public).rows == (
        reference_c08_submission(benchmark).rows
    )

    action = benchmark.public.actions[0]
    requirement = action.required_evidence[0]
    without_distractor = tuple(
        item
        for item in benchmark.public.evidence_observations
        if not (
            item.action_event_id == action.action_event_id
            and item.evidence_kind is requirement.evidence_kind
            and item.binding_handle != requirement.binding_handle
        )
    )
    reindexed = tuple(
        item.model_copy(update={"observation_order": index})
        for index, item in enumerate(without_distractor, start=1)
    )
    with pytest.raises(ValidationError, match="distractor"):
        C08AsteriaPublicInputV2.model_validate(
            {
                **benchmark.public.model_dump(mode="json"),
                "evidence_observations": [
                    item.model_dump(mode="json") for item in reindexed
                ],
            }
        )


def test_public_candidate_identities_and_evaluator_order_are_canonical() -> None:
    benchmark = _benchmark()
    observation = benchmark.public.evidence_observations[0]
    duplicate_binding = observation.model_copy(
        update={
            "observation_id": "duplicate-binding-observation",
            "observation_order": len(benchmark.public.evidence_observations) + 1,
        }
    )
    with pytest.raises(ValidationError, match="action/kind/binding-handle"):
        C08AsteriaPublicInputV2.model_validate(
            {
                **benchmark.public.model_dump(mode="json"),
                "evidence_observations": [
                    *(
                        item.model_dump(mode="json")
                        for item in benchmark.public.evidence_observations
                    ),
                    duplicate_binding.model_dump(mode="json"),
                ],
            }
        )
    duplicate_id = benchmark.public.evidence_observations[1].model_copy(
        update={
            "observation_id": observation.observation_id,
            "observation_order": len(benchmark.public.evidence_observations) + 1,
        }
    )
    with pytest.raises(ValidationError, match="observation ids"):
        C08AsteriaPublicInputV2.model_validate(
            {
                **benchmark.public.model_dump(mode="json"),
                "evidence_observations": [
                    *(
                        item.model_dump(mode="json")
                        for item in benchmark.public.evidence_observations
                    ),
                    duplicate_id.model_dump(mode="json"),
                ],
            }
        )
    with pytest.raises(ValidationError, match="canonical order"):
        C08AsteriaEvaluatorV2.model_validate(
            {
                **benchmark.evaluator.model_dump(mode="json"),
                "bindings": [
                    item.model_dump(mode="json")
                    for item in reversed(benchmark.evaluator.bindings)
                ],
            }
        )


def test_public_ordinals_and_opaque_ids_do_not_recover_scenario_labels() -> None:
    benchmark = _benchmark()
    bindings = {
        item.action_event_id: item.scenario_kind
        for item in benchmark.evaluator.bindings
    }
    label_order = tuple(
        bindings[action.action_event_id] for action in benchmark.public.actions
    )
    ordinal_guess = tuple(C08ScenarioKind)
    assert any(
        label is not ordinal_guess[action.event_order - 1]
        for action, label in zip(benchmark.public.actions, label_order, strict=True)
    )
    for action in benchmark.public.actions:
        UUID(action.action_event_id)
        UUID(action.resource_id)
        assert all(
            label.value not in action.action_event_id
            and label.value not in action.resource_id
            for label in C08ScenarioKind
        )
    for observation in benchmark.public.evidence_observations:
        UUID(observation.observation_id)
        assert all(
            label.value not in observation.observation_id for label in C08ScenarioKind
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
    with pytest.raises(ValidationError, match="evidence handles"):
        C08AsteriaBenchmarkV2(
            schema_version=benchmark.schema_version,
            benchmark_id=benchmark.benchmark_id,
            public=benchmark.public,
            evaluator=incomplete_evaluator,
        )

    action = next(
        item
        for item in benchmark.public.actions
        if item.action_event_id == binding.action_event_id
    )
    requirement = action.required_evidence[0]
    required_observation = next(
        item
        for item in benchmark.public.evidence_observations
        if item.observation_id in binding.required_observation_ids
        and item.evidence_kind is requirement.evidence_kind
        and item.binding_handle == requirement.binding_handle
    )
    distractor = next(
        item
        for item in benchmark.public.evidence_observations
        if item.action_event_id == binding.action_event_id
        and item.evidence_kind is requirement.evidence_kind
        and item.binding_handle != requirement.binding_handle
    )
    wrong_handle_binding = binding.model_copy(
        update={
            "required_observation_ids": tuple(
                distractor.observation_id
                if item == required_observation.observation_id
                else item
                for item in binding.required_observation_ids
            )
        }
    )
    wrong_handle_evaluator = benchmark.evaluator.model_copy(
        update={
            "bindings": tuple(
                wrong_handle_binding if item == binding else item
                for item in benchmark.evaluator.bindings
            )
        }
    )
    with pytest.raises(ValidationError, match="evidence handles"):
        C08AsteriaBenchmarkV2(
            public=benchmark.public,
            evaluator=wrong_handle_evaluator,
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
    ("scenario", "metric_name"),
    [
        (C08ScenarioKind.MISSING, "exact_evidence_match"),
        (C08ScenarioKind.FABRICATED, "fabricated_evidence_free"),
        (C08ScenarioKind.WRONG_ACTION, "wrong_action_evidence_free"),
        (C08ScenarioKind.EXTRA, "extra_evidence_free"),
    ],
)
def test_missing_fabricated_wrong_action_and_extra_are_distinguished(
    scenario: C08ScenarioKind,
    metric_name: str,
) -> None:
    benchmark = _benchmark()
    reference = reference_c08_submission(benchmark)
    action_index = _row_index_for_scenario(benchmark, scenario)
    if scenario is C08ScenarioKind.MISSING:
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
    elif scenario is C08ScenarioKind.WRONG_ACTION:
        other = reference.rows[0].retained_observation_ids[0]
        if (
            reference.rows[0].action_event_id
            == reference.rows[action_index].action_event_id
        ):
            other = reference.rows[1].retained_observation_ids[0]
        changed = _changed_submission(benchmark, action_index, (other,))
    elif scenario is C08ScenarioKind.EXTRA:
        required_ids = set(reference.rows[action_index].retained_observation_ids)
        observations = [
            item
            for item in benchmark.public.evidence_observations
            if item.action_event_id == reference.rows[action_index].action_event_id
            and item.observation_id not in required_ids
        ]
        changed = _changed_submission(
            benchmark, action_index, (observations[0].observation_id,)
        )
    else:
        changed = _changed_submission(
            benchmark, action_index, ("fabricated-observation",)
        )
    report = evaluate_c08_submission(benchmark, changed)
    metric = _metric(report, metric_name)
    assert metric.value is not None
    assert metric.value < 1.0


def test_discarded_scenario_is_not_distinguishable_from_missing_submission() -> None:
    benchmark = _benchmark()
    binding = next(
        item
        for item in benchmark.evaluator.bindings
        if item.scenario_kind is C08ScenarioKind.DISCARDED
    )
    reference = reference_c08_submission(benchmark)
    row_index = next(
        index
        for index, row in enumerate(reference.rows)
        if row.action_event_id == binding.action_event_id
    )
    row = reference.rows[row_index]
    changed = reference.model_copy(
        update={
            "rows": (
                *reference.rows[:row_index],
                row.model_copy(update={"retained_observation_ids": ()}),
                *reference.rows[row_index + 1 :],
            )
        }
    )
    report = evaluate_c08_submission(benchmark, changed)
    assert _metric(report, "missing_or_discarded_free").value == 5 / 6
    assert binding.scenario_kind.value == "discarded"
    assert row.retained_observation_ids


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
            for action in sorted(
                benchmark.public.actions,
                key=lambda item: item.action_event_id,
            )
        ),
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
    with pytest.raises(ValidationError, match="canonical order"):
        C08AsteriaSubmissionV2.model_validate(
            {
                **reference.model_dump(mode="json"),
                "rows": [
                    row.model_dump(mode="json") for row in reversed(reference.rows)
                ],
            }
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


def test_submission_digest_rejects_cross_public_replay_in_evaluation_and_loading() -> (
    None
):
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
        evaluate_c08_submission(tampered_benchmark, reference_c08_submission(source))


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
        "c08-asteria-frozen-public-manifest-v2.schema.json",
        "c08-asteria-frozen-evaluator-manifest-v2.schema.json",
        "c08-asteria-frozen-root-manifest-v2.schema.json",
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


@pytest.mark.parametrize(
    ("values", "message"),
    (
        (("",), "nonblank"),
        (("duplicate", "duplicate"), "unique"),
        (("z-last", "a-first"), "canonical order"),
    ),
)
def test_measurement_scope_strings_are_nonblank_unique_and_canonical(
    values: tuple[str, ...], message: str
) -> None:
    scope = _benchmark().public.measurement_scope
    with pytest.raises(ValidationError, match=message):
        type(scope).model_validate(
            {**scope.model_dump(mode="json"), "proves": values}
        )


def test_public_action_and_stream_canonical_contracts_fail_closed() -> None:
    benchmark = _benchmark()
    action = next(
        item for item in benchmark.public.actions if len(item.required_evidence) > 1
    )
    action_document = action.model_dump(mode="json")
    requirements = action_document["required_evidence"]
    with pytest.raises(ValidationError, match="unique"):
        type(action).model_validate(
            {**action_document, "required_evidence": (requirements[0], requirements[0])}
        )
    with pytest.raises(ValidationError, match="canonical order"):
        type(action).model_validate(
            {**action_document, "required_evidence": tuple(reversed(requirements))}
        )

    public_document = benchmark.public.model_dump(mode="json")
    duplicate_actions = [dict(item) for item in public_document["actions"]]
    duplicate_actions[1] = dict(duplicate_actions[0])
    with pytest.raises(ValidationError, match="action ids"):
        C08AsteriaPublicInputV2.model_validate(
            {**public_document, "actions": duplicate_actions}
        )

    noncontiguous_actions = [dict(item) for item in public_document["actions"]]
    noncontiguous_actions[0]["event_order"] = len(noncontiguous_actions) + 1
    with pytest.raises(ValidationError, match="contiguous event order"):
        C08AsteriaPublicInputV2.model_validate(
            {**public_document, "actions": noncontiguous_actions}
        )

    unordered_observations = [
        dict(item) for item in public_document["evidence_observations"]
    ]
    unordered_observations[0]["observation_order"] = len(unordered_observations) + 1
    with pytest.raises(ValidationError, match="preserve order"):
        C08AsteriaPublicInputV2.model_validate(
            {**public_document, "evidence_observations": unordered_observations}
        )

    unsolvable_actions = [dict(item) for item in public_document["actions"]]
    unsolvable_requirements = [
        dict(item) for item in unsolvable_actions[0]["required_evidence"]
    ]
    unsolvable_requirements[0]["binding_handle"] = (
        "00000000-0000-0000-0000-000000000000"
    )
    unsolvable_requirements.sort(
        key=lambda item: (item["evidence_kind"], item["binding_handle"])
    )
    unsolvable_actions[0]["required_evidence"] = unsolvable_requirements
    with pytest.raises(ValidationError, match="exactly one binding handle"):
        C08AsteriaPublicInputV2.model_validate(
            {**public_document, "actions": unsolvable_actions}
        )


def test_evaluator_submission_and_benchmark_identities_fail_closed() -> None:
    benchmark = _benchmark()
    evaluator_document = benchmark.evaluator.model_dump(mode="json")
    bindings = evaluator_document["bindings"]
    with pytest.raises(ValidationError, match="binding action ids"):
        C08AsteriaEvaluatorV2.model_validate(
            {**evaluator_document, "bindings": (bindings[0], *bindings)}
        )

    with pytest.raises(ValidationError, match="nonblank"):
        C08SubmissionRowV2(action_event_id="action", retained_observation_ids=("",))

    reference = reference_c08_submission(benchmark)
    reference_document = reference.model_dump(mode="json")
    rows = reference_document["rows"]
    with pytest.raises(ValidationError, match="submission action ids"):
        C08AsteriaSubmissionV2.model_validate(
            {**reference_document, "rows": (rows[0], rows[0], *rows[1:])}
        )

    incomplete_evaluator = C08AsteriaEvaluatorV2.model_validate(
        {**evaluator_document, "bindings": bindings[:-1]}
    )
    with pytest.raises(ValidationError, match="actions and evaluator bindings"):
        C08AsteriaBenchmarkV2(
            public=benchmark.public,
            evaluator=incomplete_evaluator,
        )

    binding = benchmark.evaluator.bindings[0]
    unknown_binding = binding.model_copy(
        update={"required_observation_ids": ("unknown-observation",)}
    )
    unknown_evaluator = benchmark.evaluator.model_copy(
        update={
            "bindings": tuple(
                unknown_binding if item == binding else item
                for item in benchmark.evaluator.bindings
            )
        }
    )
    with pytest.raises(ValidationError, match="unknown observation"):
        C08AsteriaBenchmarkV2(
            public=benchmark.public,
            evaluator=unknown_evaluator,
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        ({"numerator": 2, "denominator": 1, "value": 2.0}, "cannot exceed"),
        (
            {"denominator": 1, "value": None, "undefined_reason": "unsupported"},
            "zero support",
        ),
        (
            {"denominator": 0, "value": None, "undefined_reason": None},
            "zero support",
        ),
        ({"denominator": 0, "value": 0.0}, "must have support"),
        (
            {"denominator": 1, "value": 1.0, "undefined_reason": "unexpected"},
            "must have support",
        ),
        ({"numerator": 1, "denominator": 2, "value": 0.75}, "must equal"),
        ({"numerator": 1, "denominator": 1, "value": float("inf")}, "must equal"),
    ),
)
def test_metric_value_contract_rejects_incoherent_states(
    updates: dict[str, object], message: str
) -> None:
    document: dict[str, object] = {
        "name": "exact_evidence_match",
        "numerator": 0,
        "denominator": 1,
        "value": 0.0,
        "denominator_meaning": "test actions",
        "undefined_reason": None,
    }
    with pytest.raises(ValidationError, match=message):
        C08MetricV2.model_validate({**document, **updates})


def test_report_and_manifest_collections_require_fixed_canonical_order() -> None:
    benchmark = _benchmark()
    report = evaluate_c08_submission(benchmark, reference_c08_submission(benchmark))
    with pytest.raises(ValidationError, match="fixed independent order"):
        C08MetricsReportV2.model_validate(
            {
                **report.model_dump(mode="json"),
                "metrics": tuple(
                    item.model_dump(mode="json") for item in reversed(report.metrics)
                ),
            }
        )

    manifest_document = json.loads(
        build_c08_public_artifacts(benchmark.public)["manifest.json"]
    )
    descriptor = manifest_document["artifacts"][0]
    with pytest.raises(ValidationError, match="paths must be unique"):
        C08ArtifactManifestV2.model_validate(
            {**manifest_document, "artifacts": (descriptor, descriptor)}
        )
    with pytest.raises(ValidationError, match="canonical order"):
        C08ArtifactManifestV2.model_validate(
            {
                **manifest_document,
                "artifacts": (
                    {**descriptor, "path": "z-last.json"},
                    {**descriptor, "path": "a-first.json"},
                ),
            }
        )


def test_serialization_rejects_invalid_payload_and_manifest_bindings() -> None:
    benchmark = _benchmark()
    public_artifacts = build_c08_public_artifacts(benchmark.public)
    invalid_payload = dict(public_artifacts)
    invalid_payload["c08-asteria-public.json"] = b"not-json\n"
    with pytest.raises(C08ArtifactError, match="invalid"):
        load_c08_public_artifacts(invalid_payload)

    mismatched_manifest = dict(public_artifacts)
    manifest_document = json.loads(mismatched_manifest["manifest.json"])
    manifest_document["visibility"] = "evaluator"
    mismatched_manifest["manifest.json"] = canonical_json_value_bytes(
        manifest_document
    )
    with pytest.raises(C08ArtifactError, match="manifest binding"):
        load_c08_public_artifacts(mismatched_manifest)

    reference = reference_c08_submission(benchmark)
    submission_artifacts = build_c08_submission_artifacts(reference)
    assert load_c08_submission_artifacts(submission_artifacts) == reference
    assert (
        load_c08_bundle(
            public_artifacts,
            build_c08_evaluator_artifacts(benchmark.evaluator),
        )
        == benchmark
    )


def test_solver_and_evaluator_defensive_invariants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = _benchmark()
    action = benchmark.public.actions[0]
    requirement = action.required_evidence[0].model_copy(
        update={"binding_handle": "00000000-0000-0000-0000-000000000000"}
    )
    corrupted_action = action.model_copy(
        update={
            "required_evidence": (requirement, *action.required_evidence[1:]),
        }
    )
    corrupted_public = benchmark.public.model_copy(
        update={"actions": (corrupted_action, *benchmark.public.actions[1:])}
    )
    with pytest.raises(ValueError, match="not uniquely solvable"):
        semantic_c08_submission(corrupted_public)

    reference = reference_c08_submission(benchmark)
    with pytest.raises(C08EvaluationError, match="benchmark id"):
        evaluate_c08_submission(
            benchmark,
            reference.model_copy(update={"benchmark_id": "wrong-benchmark"}),
        )

    monkeypatch.setattr(
        c08_metrics,
        "C08_METRIC_NAMES",
        tuple(reversed(c08_metrics.C08_METRIC_NAMES)),
    )
    with pytest.raises(AssertionError, match="construction order"):
        evaluate_c08_submission(benchmark, reference)
