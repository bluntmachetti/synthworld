"""Focused checks for the experiment-owned enterprise agentic identity pilot."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from examples.enterprise_agentic_identity_pilot import policies as pilot_policies
from examples.enterprise_agentic_identity_pilot.__main__ import main as pilot_main
from examples.enterprise_agentic_identity_pilot.policies import build_policy_traces
from examples.enterprise_agentic_identity_pilot.rendering import EVALUATOR_WATERMARK
from synthworld.agentic import trace_submission_from_jsonl
from synthworld.agentic.enterprise import (
    EnterpriseAgenticGenerationConfigV1,
    evaluate_generated_enterprise_agentic_trace,
    export_generated_enterprise_agentic_benchmark,
    generate_enterprise_agentic_world,
    generated_enterprise_agentic_artifact_checksums,
    generated_enterprise_agentic_public_artifact_set_sha256,
    generated_enterprise_agentic_public_artifacts,
)
from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticGeneratedBenchmarkV1,
    EnterpriseAgenticGeneratedPublicV1,
)
from synthworld.agentic.models import ActionAttempted, Decision
from synthworld.agentic.replay import materialize_agentic_world


@pytest.fixture(scope="module")
def pilot_benchmark() -> EnterpriseAgenticGeneratedBenchmarkV1:
    return generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=20_260_821)
    )


def test_rbac_requires_an_explicit_assignment_and_permission(
    pilot_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    public = pilot_benchmark.public
    event = next(
        item for item in public.events if item.id == public.scenario.action_event_ids[0]
    )
    assert isinstance(event.payload, ActionAttempted)
    state = materialize_agentic_world(
        public.snapshot,
        public.events,
        at_event_index=event.event_index - 1,
    )
    rbac = pilot_policies._compile_directory_rbac_overlay(public.snapshot)
    context = pilot_policies._PolicyContext(
        attempt=event.payload.attempt,
        state=state,
        decision_time=event.occurred_at,
        rbac=rbac,
    )

    assert pilot_policies._rbac_allows(context)
    assert not pilot_policies._rbac_allows(
        replace(context, rbac=replace(rbac, assignments=frozenset()))
    )
    assert not pilot_policies._rbac_allows(
        replace(context, rbac=replace(rbac, permissions=frozenset()))
    )


def test_policy_traces_are_deterministic_decision_only_and_discriminating(
    pilot_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    first = build_policy_traces(pilot_benchmark.public)
    repeated = build_policy_traces(pilot_benchmark.public)

    assert first == repeated
    assert tuple(name for name, _submission in first) == (
        "rbac",
        "abac",
        "rebac",
        "combined",
    )

    allow = Decision.ALLOW
    deny = Decision.DENY
    expected_action_decisions = {
        "rbac": (allow, deny, allow, allow, allow, allow, allow),
        "abac": (allow, deny, deny, deny, allow, allow, allow),
        "rebac": (allow, deny, allow, allow, allow, allow, deny),
        "combined": (allow, deny, deny, deny, allow, allow, deny),
    }
    expected_audit_decisions = {
        "rbac": (allow, deny, allow, allow, allow, allow, allow),
        "abac": (allow, deny, deny, deny, allow, allow, allow),
        "rebac": (allow, deny, allow, allow, deny, allow, deny),
        "combined": (allow, deny, deny, deny, deny, allow, deny),
    }
    oracle_bearing_fields = (
        "originating_principal_id",
        "logical_agent_id",
        "runtime_principal_id",
        "credential_subject_id",
        "attributed_actor_id",
        "side_effect",
        "delegation_chain_ids",
        "accountable_owner_chain",
        "evidence_refs",
        "reconstructable_from_retained_evidence",
    )
    for name, submission in first:
        assert (
            tuple(row.decision for row in submission.rows)
            == (expected_action_decisions[name])
        )
        assert (
            tuple(row.decision_at_audit for row in submission.rows)
            == (expected_audit_decisions[name])
        )
        for row in submission.rows:
            assert row.model_fields_set == {
                "decision",
                "decision_at_audit",
                "event_id",
            }
            assert set(row.model_dump(exclude_none=True)) == {
                "decision",
                "decision_at_audit",
                "event_id",
                "schema_version",
                "synthetic",
            }
            assert all(getattr(row, field) is None for field in oracle_bearing_fields)


def test_policy_scores_retain_exact_independent_denominators(
    pilot_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    expected = {
        "rbac": ((4 / 7, 7), (1 / 4, 4), (0.0, 2)),
        "abac": ((6 / 7, 7), (3 / 4, 4), (0.0, 2)),
        "rebac": ((5 / 7, 7), (2 / 4, 4), (1.0, 2)),
        "combined": ((1.0, 7), (1.0, 4), (1.0, 2)),
    }

    actual: dict[str, tuple[tuple[float | None, int], ...]] = {}
    for name, submission in build_policy_traces(pilot_benchmark.public):
        report = evaluate_generated_enterprise_agentic_trace(
            submission, pilot_benchmark
        )
        metrics = {metric.name: metric for metric in report.metrics}
        actual[name] = tuple(
            (metrics[metric_name].value, metrics[metric_name].support)
            for metric_name in (
                "authorization_decision_accuracy",
                "least_privilege_accuracy",
                "temporal_validity_accuracy",
            )
        )

    assert actual == expected


def test_public_only_cli_writes_deterministic_new_outputs(
    tmp_path: Path,
    pilot_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    complete_root = tmp_path / "complete-benchmark"
    export_generated_enterprise_agentic_benchmark(complete_root, pilot_benchmark)
    isolated_root = tmp_path / "isolated-product"
    public_tree = isolated_root / "public"
    shutil.copytree(complete_root / "public", public_tree)
    assert not (isolated_root / "evaluator").exists()

    first_output = tmp_path / "first-submissions"
    assert (
        pilot_main(
            [
                "run-policies",
                "--public-package",
                str(public_tree),
                "--output",
                str(first_output),
            ]
        )
        == 0
    )
    assert {item.name for item in first_output.iterdir()} == {
        "abac.jsonl",
        "combined.jsonl",
        "manifest.json",
        "rbac.jsonl",
        "rebac.jsonl",
    }
    manifest = json.loads((first_output / "manifest.json").read_bytes())
    assert manifest["derived_from_public_only"] is True
    public_model = EnterpriseAgenticGeneratedPublicV1(
        config=pilot_benchmark.config,
        identity=pilot_benchmark.identity,
        benchmark=pilot_benchmark.public,
    )
    assert manifest["benchmark_identity"] == pilot_benchmark.identity.model_dump(
        mode="json"
    )
    assert manifest["public_artifact_set_sha256"] == (
        generated_enterprise_agentic_public_artifact_set_sha256(public_model)
    )
    assert set(manifest["policy_sources"]) == {
        "implementation_sha256",
        "overlay_sha256",
    }
    assert [item["name"] for item in manifest["strategies"]] == [
        "rbac",
        "abac",
        "rebac",
        "combined",
    ]
    for name in ("rbac", "abac", "rebac", "combined"):
        submission = trace_submission_from_jsonl(
            (first_output / f"{name}.jsonl").read_text(encoding="utf-8")
        )
        assert len(submission.rows) == 7
        assert all(row.decision is not None for row in submission.rows)
        assert all(row.decision_at_audit is not None for row in submission.rows)
        assert all(row.accountable_owner_chain is None for row in submission.rows)
        assert all(row.evidence_refs is None for row in submission.rows)

    first_bytes = {
        path.relative_to(first_output): path.read_bytes()
        for path in sorted(first_output.rglob("*"))
        if path.is_file()
    }
    with pytest.raises(FileExistsError, match="submission output already exists"):
        pilot_main(
            [
                "run-policies",
                "--public-package",
                str(public_tree),
                "--output",
                str(first_output),
            ]
        )
    assert {
        path.relative_to(first_output): path.read_bytes()
        for path in sorted(first_output.rglob("*"))
        if path.is_file()
    } == first_bytes

    repeated_output = tmp_path / "repeated-submissions"
    assert (
        pilot_main(
            [
                "run-policies",
                "--public-package",
                str(public_tree),
                "--output",
                str(repeated_output),
            ]
        )
        == 0
    )
    assert {
        path.relative_to(repeated_output): path.read_bytes()
        for path in sorted(repeated_output.rglob("*"))
        if path.is_file()
    } == first_bytes


def test_full_cli_keeps_reference_truth_in_deterministic_evaluator_outputs(
    tmp_path: Path,
    pilot_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    world_root = tmp_path / "world"
    assert (
        pilot_main(
            [
                "generate",
                "--seed",
                "20260821",
                "--output",
                str(world_root),
            ]
        )
        == 0
    )
    public_html = world_root / "visuals" / "world-public.html"
    assert public_html.is_file()
    assert EVALUATOR_WATERMARK not in public_html.read_text(encoding="utf-8")
    assert (world_root / "benchmark" / "public" / "public-input.json").is_file()
    assert (world_root / "benchmark" / "evaluator" / "truth.json").is_file()

    submissions = tmp_path / "submissions"
    assert (
        pilot_main(
            [
                "run-policies",
                "--public-package",
                str(world_root / "benchmark" / "public"),
                "--output",
                str(submissions),
            ]
        )
        == 0
    )

    first_results = tmp_path / "first-results"
    assert (
        pilot_main(
            [
                "score",
                "--benchmark-root",
                str(world_root / "benchmark"),
                "--submissions",
                str(submissions),
                "--output",
                str(first_results),
            ]
        )
        == 0
    )
    comparison = (first_results / "policy-comparison.html").read_text(encoding="utf-8")
    evaluator_world = (first_results / "world-evaluator.html").read_text(
        encoding="utf-8"
    )
    assert EVALUATOR_WATERMARK in comparison
    assert EVALUATOR_WATERMARK in evaluator_world
    assert "authorization_decision_accuracy" in comparison
    assert "least_privilege_accuracy" in comparison
    assert "temporal_validity_accuracy" in comparison
    assert "https://" not in comparison
    assert "http://" not in comparison
    manifest = json.loads((first_results / "manifest.json").read_bytes())
    assert manifest["contains_reference_truth"] is True
    assert [item["name"] for item in manifest["reports"]] == [
        "rbac",
        "abac",
        "rebac",
        "combined",
    ]
    assert [item["name"] for item in manifest["submissions"]] == [
        "rbac",
        "abac",
        "rebac",
        "combined",
    ]
    assert [item["name"] for item in manifest["html"]] == [
        "policy-comparison.html",
        "world-evaluator.html",
    ]
    benchmark_checksums = dict(
        generated_enterprise_agentic_artifact_checksums(pilot_benchmark)
    )
    assert (
        manifest["source"]["benchmark_identity"]
        == (
            json.loads(
                (world_root / "benchmark" / "public" / "public-input.json").read_bytes()
            )["identity"]
        )
    )
    assert (
        manifest["source"]["public_artifact_set_sha256"]
        == (benchmark_checksums["public"])
    )
    assert (
        manifest["source"]["evaluator_artifact_set_sha256"]
        == benchmark_checksums["evaluator"]
    )
    assert (
        manifest["source"]["submission_manifest_sha256"]
        == hashlib.sha256((submissions / "manifest.json").read_bytes()).hexdigest()
    )

    first_bytes = {
        path.relative_to(first_results): path.read_bytes()
        for path in sorted(first_results.rglob("*"))
        if path.is_file()
    }
    with pytest.raises(FileExistsError, match="evaluator output already exists"):
        pilot_main(
            [
                "score",
                "--benchmark-root",
                str(world_root / "benchmark"),
                "--submissions",
                str(submissions),
                "--output",
                str(first_results),
            ]
        )
    assert {
        path.relative_to(first_results): path.read_bytes()
        for path in sorted(first_results.rglob("*"))
        if path.is_file()
    } == first_bytes

    repeated_results = tmp_path / "repeated-results"
    assert (
        pilot_main(
            [
                "score",
                "--benchmark-root",
                str(world_root / "benchmark"),
                "--submissions",
                str(submissions),
                "--output",
                str(repeated_results),
            ]
        )
        == 0
    )
    assert {
        path.relative_to(repeated_results): path.read_bytes()
        for path in sorted(repeated_results.rglob("*"))
        if path.is_file()
    } == first_bytes

    tampered_submissions = tmp_path / "tampered-submissions"
    shutil.copytree(submissions, tampered_submissions)
    tampered_rbac = tampered_submissions / "rbac.jsonl"
    tampered_rbac.write_bytes(tampered_rbac.read_bytes() + b"\n")
    tampered_results = tmp_path / "tampered-results"
    with pytest.raises(ValueError, match="submission digest mismatch for rbac"):
        pilot_main(
            [
                "score",
                "--benchmark-root",
                str(world_root / "benchmark"),
                "--submissions",
                str(tampered_submissions),
                "--output",
                str(tampered_results),
            ]
        )
    assert not tampered_results.exists()


def test_score_rejects_submissions_from_a_different_self_consistent_public_tree(
    tmp_path: Path,
    pilot_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    events = list(pilot_benchmark.public.events)
    event_index = next(
        index
        for index, event in enumerate(events)
        if isinstance(event.payload, ActionAttempted)
    )
    event = events[event_index]
    assert isinstance(event.payload, ActionAttempted)
    attempt = event.payload.attempt.model_copy(
        update={"purpose": "modified-public-purpose"}
    )
    payload = event.payload.model_copy(update={"attempt": attempt})
    events[event_index] = event.model_copy(update={"payload": payload})
    modified_public = pilot_benchmark.public.model_copy(
        update={"events": tuple(events)}
    )
    modified_generated = pilot_benchmark.model_copy(update={"public": modified_public})
    modified_tree = tmp_path / "modified-product" / "public"
    for relative_path, artifact in generated_enterprise_agentic_public_artifacts(
        modified_generated
    ).items():
        target = modified_tree / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact)

    modified_submissions = tmp_path / "modified-submissions"
    assert (
        pilot_main(
            [
                "run-policies",
                "--public-package",
                str(modified_tree),
                "--output",
                str(modified_submissions),
            ]
        )
        == 0
    )

    canonical_root = tmp_path / "canonical-benchmark"
    export_generated_enterprise_agentic_benchmark(canonical_root, pilot_benchmark)
    rejected_results = tmp_path / "rejected-results"
    with pytest.raises(
        ValueError, match="public artifact set does not match benchmark"
    ):
        pilot_main(
            [
                "score",
                "--benchmark-root",
                str(canonical_root),
                "--submissions",
                str(modified_submissions),
                "--output",
                str(rejected_results),
            ]
        )
    assert not rejected_results.exists()
