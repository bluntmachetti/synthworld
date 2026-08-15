"""Generated enterprise-agentic smoke configuration, graph, and artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.agentic import (
    AgenticBenchmark,
    AgenticBenchmarkIntegrityError,
    AgenticTraceSubmission,
    ObservedActionTrace,
    build_agentic_benchmark,
    reference_agentic_trace,
    trace_submission_to_jsonl,
)
from synthworld.agentic.enterprise import (
    EnterpriseAgenticArtifactError,
    EnterpriseAgenticGenerationConfigV1,
    EnterpriseAgenticSmokeTopologyV1,
    derive_enterprise_agentic_integrity_metrics,
    evaluate_generated_enterprise_agentic_trace,
    export_generated_enterprise_agentic_benchmark,
    generate_enterprise_agentic_world,
    generated_enterprise_agentic_artifact_checksums,
    generated_enterprise_agentic_evaluator_artifacts,
    generated_enterprise_agentic_public_artifacts,
    load_generated_enterprise_agentic_benchmark,
    load_public_generated_enterprise_agentic_benchmark,
)
from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticArtifactDescriptorV1,
    EnterpriseAgenticCountMetricV1,
    EnterpriseAgenticDistributionBinV1,
    EnterpriseAgenticGeneratedBenchmarkV1,
    EnterpriseAgenticGeneratedEvaluatorManifestV1,
    EnterpriseAgenticGeneratedEvaluatorV1,
    EnterpriseAgenticGeneratedPublicManifestV1,
    EnterpriseAgenticGeneratedPublicV1,
)
from synthworld.agentic.enterprise.generated_serialization import (
    generated_enterprise_agentic_artifact_set_sha256,
)
from synthworld.agentic.models import (
    AgenticCaseKind,
    AuthorityFailureReason,
    Decision,
)
from synthworld.cli import main
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
)


def _benchmark(generated: EnterpriseAgenticGeneratedBenchmarkV1) -> AgenticBenchmark:
    return AgenticBenchmark(public=generated.public, evaluator=generated.evaluator)


def _write_artifact_tree(root: Path, artifacts: dict[str, bytes]) -> None:
    for relative_path, payload in artifacts.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _descriptor(path: str, payload: bytes) -> EnterpriseAgenticArtifactDescriptorV1:
    return EnterpriseAgenticArtifactDescriptorV1(
        path=path,
        byte_size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _rebind_public_manifest(artifacts: dict[str, bytes]) -> None:
    base = {
        path: payload for path, payload in artifacts.items() if path != "manifest.json"
    }
    artifacts["manifest.json"] = canonical_json_bytes(
        EnterpriseAgenticGeneratedPublicManifestV1(
            artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(base),
            artifacts=tuple(
                _descriptor(path, payload) for path, payload in sorted(base.items())
            ),
        )
    )


def _rebind_evaluator_manifest(artifacts: dict[str, bytes], public_digest: str) -> None:
    base = {
        path: payload for path, payload in artifacts.items() if path != "manifest.json"
    }
    artifacts["manifest.json"] = canonical_json_bytes(
        EnterpriseAgenticGeneratedEvaluatorManifestV1(
            artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(base),
            public_artifact_set_sha256=public_digest,
            artifacts=tuple(
                _descriptor(path, payload) for path, payload in sorted(base.items())
            ),
        )
    )


def test_default_smoke_world_is_deterministic_and_seed_bound() -> None:
    first = generate_enterprise_agentic_world()
    second = generate_enterprise_agentic_world(EnterpriseAgenticGenerationConfigV1())
    alternate = generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=20_260_815)
    )

    assert first == second
    assert generated_enterprise_agentic_public_artifacts(first) == (
        generated_enterprise_agentic_public_artifacts(second)
    )
    assert (
        first.identity.configuration_sha256 != alternate.identity.configuration_sha256
    )
    assert first.identity.world_id != alternate.identity.world_id
    assert first.public.snapshot.principals != alternate.public.snapshot.principals
    assert generated_enterprise_agentic_artifact_checksums(first) != (
        generated_enterprise_agentic_artifact_checksums(alternate)
    )


def test_smallest_supported_smoke_topology_preserves_case_invariants() -> None:
    config = EnterpriseAgenticGenerationConfigV1(
        seed=7,
        topology=EnterpriseAgenticSmokeTopologyV1(
            department_count=2,
            human_principal_count=4,
            logical_agent_count=3,
            runtime_count=3,
            resource_count=3,
        ),
    )
    generated = generate_enterprise_agentic_world(config)

    assert len(generated.public.snapshot.organisations) == 1
    assert len(generated.public.snapshot.departments) == 2
    assert len(generated.public.snapshot.agents) == 3
    assert len(generated.public.snapshot.resources) == 3
    assert [item.kind for item in generated.evaluator.cases] == [
        AgenticCaseKind.AUTHORISED_ACTION,
        AgenticCaseKind.OUTSIDE_CAPABILITY,
        AgenticCaseKind.WRONG_RUNTIME,
        AgenticCaseKind.CREDENTIAL_INVALID,
        AgenticCaseKind.VALID_THEN_REVOKED,
        AgenticCaseKind.INCORRECT_ATTRIBUTION,
        AgenticCaseKind.POST_REVOCATION_ACTION,
    ]
    truth = generated.evaluator.authority_truth
    assert tuple(item.decision_at_action for item in truth) == (
        Decision.ALLOW,
        Decision.DENY,
        Decision.DENY,
        Decision.DENY,
        Decision.ALLOW,
        Decision.ALLOW,
        Decision.DENY,
    )
    assert truth[4].decision_at_audit is Decision.DENY
    assert truth[4].reconstructable_at_audit is False
    assert truth[2].failure_reasons_at_action == (AuthorityFailureReason.WRONG_RUNTIME,)
    assert truth[3].failure_reasons_at_action == (
        AuthorityFailureReason.CREDENTIAL_INVALID,
    )
    assert truth[6].failure_reasons_at_action == (
        AuthorityFailureReason.DELEGATION_REVOKED,
    )


def test_topology_rejects_unrepresentable_and_non_strict_counts() -> None:
    with pytest.raises(
        ValidationError, match="logical agents cannot outnumber accountable humans"
    ):
        EnterpriseAgenticSmokeTopologyV1(
            human_principal_count=4,
            logical_agent_count=5,
            runtime_count=5,
        )
    with pytest.raises(ValidationError, match="every logical agent requires"):
        EnterpriseAgenticSmokeTopologyV1(
            human_principal_count=5,
            logical_agent_count=5,
            runtime_count=4,
        )
    with pytest.raises(ValidationError, match="valid integer"):
        EnterpriseAgenticSmokeTopologyV1(human_principal_count=True)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EnterpriseAgenticGenerationConfigV1(host_platform="linux")  # type: ignore[call-arg]


def test_generated_identity_and_metric_support_are_schema_enforced() -> None:
    generated = generate_enterprise_agentic_world()
    mismatched_config_identity = generated.identity.model_copy(
        update={"configuration_sha256": "0" * 64}
    )
    with pytest.raises(ValidationError, match="configuration identity differs"):
        EnterpriseAgenticGeneratedPublicV1(
            config=generated.config,
            identity=mismatched_config_identity,
            benchmark=generated.public,
        )

    mismatched_world_identity = generated.identity.model_copy(
        update={"world_id": "different-world"}
    )
    with pytest.raises(ValidationError, match="world identity differs"):
        EnterpriseAgenticGeneratedPublicV1(
            config=generated.config,
            identity=mismatched_world_identity,
            benchmark=generated.public,
        )

    with pytest.raises(ValidationError, match="count cannot exceed"):
        EnterpriseAgenticCountMetricV1(
            name="invalid", count=2, denominator=1, denominator_meaning="records"
        )
    with pytest.raises(ValidationError, match="meaning must be nonblank"):
        EnterpriseAgenticCountMetricV1(
            name="invalid", count=1, denominator=1, denominator_meaning=" "
        )
    with pytest.raises(ValidationError, match="count cannot exceed"):
        EnterpriseAgenticDistributionBinV1(
            value="invalid", count=2, denominator=1, denominator_meaning="records"
        )
    with pytest.raises(ValidationError, match="meaning must be nonblank"):
        EnterpriseAgenticDistributionBinV1(
            value="invalid", count=1, denominator=1, denominator_meaning=" "
        )


def test_metrics_are_derived_and_every_distribution_states_support() -> None:
    generated = generate_enterprise_agentic_world()
    metrics = generated.metrics
    counts = {item.name: item for item in metrics.counts}

    assert metrics == derive_enterprise_agentic_integrity_metrics(_benchmark(generated))
    expected_counts = {
        "organisation_count": 1,
        "department_count": 4,
        "human_principal_count": 25,
        "logical_agent_count": 5,
        "runtime_count": 8,
        "credential_count": 10,
        "resource_count": 6,
        "delegation_count": 5,
        "action_event_count": 7,
        "allowed_action_count": 3,
        "denied_action_count": 4,
        "revoked_delegation_count": 1,
        "evidence_loss_event_count": 1,
    }
    assert {name: counts[name].count for name in expected_counts} == expected_counts
    assert all(item.denominator_meaning for item in metrics.counts)
    for distribution in (
        metrics.owner_chain_depth_distribution,
        metrics.runtimes_per_agent_distribution,
        metrics.credential_runtime_binding_distribution,
        metrics.delegation_depth_distribution,
        metrics.case_kind_distribution,
    ):
        assert sum(item.count for item in distribution) == distribution[0].denominator
        assert len({item.denominator for item in distribution}) == 1
        assert all(item.denominator_meaning for item in distribution)
    assert {
        (item.value, item.count) for item in metrics.delegation_depth_distribution
    } == {
        ("1", 4),
        ("2", 1),
    }
    assert metrics.principal_graph_component_count == 1
    assert metrics.referential_integrity is True
    assert metrics.canonical_binding_integrity is True


def test_generated_world_scores_without_asteria_identifiers_or_paths() -> None:
    generated = generate_enterprise_agentic_world()
    benchmark = _benchmark(generated)
    report = evaluate_generated_enterprise_agentic_trace(
        reference_agentic_trace(benchmark), generated
    )

    assert generated.public.snapshot.world_id != "asteria-agentic"
    assert all(
        "procurement" not in path
        for path in generated.public.scenario.tool_schema_paths
    )
    assert report.checksum_scheme == "sha256-generated-enterprise-agentic-v1"
    assert report.artifact_checksums == (
        generated_enterprise_agentic_artifact_checksums(generated)
    )
    values = {item.name: item.value for item in report.metrics}
    assert values["excess_authority_rate"] == 0.0
    assert all(
        value == 1.0
        for name, value in values.items()
        if name != "excess_authority_rate" and value is not None
    )


def test_generated_world_routes_through_hardened_binding_validation() -> None:
    generated = generate_enterprise_agentic_world()
    public = generated.public
    first = generated.evaluator.bindings[0]
    broken = first.model_copy(update={"accountable_owner_chain": ("unknown",)})

    with pytest.raises(
        AgenticBenchmarkIntegrityError,
        match="canonical accountable owner chain differs",
    ):
        build_agentic_benchmark(
            public.snapshot,
            public.events,
            public.scenario,
            (broken, *generated.evaluator.bindings[1:]),
            generated.evaluator.cases,
        )


def test_artifacts_are_oracle_free_separate_canonical_and_cross_bound(
    tmp_path: Path,
) -> None:
    generated = generate_enterprise_agentic_world()
    public = generated_enterprise_agentic_public_artifacts(generated)
    evaluator = generated_enterprise_agentic_evaluator_artifacts(generated)

    assert set(public) == {
        "manifest.json",
        "public-input.json",
        "scenarios/enterprise-agentic-smoke-v1.json",
        "tool_schemas/enterprise-agentic-actions-v1.json",
    }
    assert set(evaluator) == {"manifest.json", "truth.json"}
    public_text = b"".join(public.values()).decode("utf-8")
    for forbidden in (
        "authority_truth",
        "canonical_bindings",
        "decision_at_action",
        "failure_reasons_at_action",
    ):
        assert forbidden not in public_text

    public_manifest = EnterpriseAgenticGeneratedPublicManifestV1.model_validate_json(
        public["manifest.json"]
    )
    evaluator_manifest = (
        EnterpriseAgenticGeneratedEvaluatorManifestV1.model_validate_json(
            evaluator["manifest.json"]
        )
    )
    evaluator_truth = EnterpriseAgenticGeneratedEvaluatorV1.model_validate_json(
        evaluator["truth.json"]
    )
    public_base = {
        name: value for name, value in public.items() if name != "manifest.json"
    }
    evaluator_base = {
        name: value for name, value in evaluator.items() if name != "manifest.json"
    }
    public_base_digest = generated_enterprise_agentic_artifact_set_sha256(public_base)
    public_tree_digest = generated_enterprise_agentic_artifact_set_sha256(public)
    assert public_manifest.artifact_set_sha256 == public_base_digest
    assert evaluator_manifest.public_artifact_set_sha256 == public_tree_digest
    assert evaluator_truth.public_artifact_set_sha256 == public_tree_digest
    assert evaluator_manifest.artifact_set_sha256 == (
        generated_enterprise_agentic_artifact_set_sha256(evaluator_base)
    )
    for payload in (*public.values(), *evaluator.values()):
        assert payload.endswith(b"\n")
        assert b"\r\n" not in payload
        json.loads(payload)

    output = tmp_path / "generated"
    export_generated_enterprise_agentic_benchmark(output, generated)
    assert {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    } == {
        *(f"public/{name}" for name in public),
        *(f"evaluator/{name}" for name in evaluator),
    }
    with pytest.raises(FileExistsError, match="output already exists"):
        export_generated_enterprise_agentic_benchmark(output, generated)


def test_artifact_set_digest_binds_paths_as_well_as_bytes() -> None:
    payload = b"{}\n"
    assert generated_enterprise_agentic_artifact_set_sha256({"a.json": payload}) != (
        generated_enterprise_agentic_artifact_set_sha256({"b.json": payload})
    )


def test_generated_smoke_cli_exports_the_bounded_profile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "generated-smoke"
    arguments = [
        "generate-enterprise-agentic",
        "--profile",
        "generated",
        "--tier",
        "smoke",
        "--seed",
        "17",
        "--output",
        str(output),
    ]

    assert main(arguments) == 0
    assert "39 principals, 7 actions" in capsys.readouterr().out
    assert (output / "public" / "public-input.json").is_file()
    assert (output / "evaluator" / "truth.json").is_file()
    assert main(arguments) == 1
    assert "output already exists" in capsys.readouterr().err


def test_generated_loaders_round_trip_and_public_loading_is_isolated(
    tmp_path: Path,
) -> None:
    generated = generate_enterprise_agentic_world()
    root = tmp_path / "complete"
    export_generated_enterprise_agentic_benchmark(root, generated)

    public = load_public_generated_enterprise_agentic_benchmark(root)
    assert public.config == generated.config
    assert public.identity == generated.identity
    assert public.benchmark == generated.public
    assert load_generated_enterprise_agentic_benchmark(root) == generated

    public_only = tmp_path / "public-only"
    _write_artifact_tree(
        public_only / "public",
        generated_enterprise_agentic_public_artifacts(generated),
    )
    (public_only / "evaluator").symlink_to(
        tmp_path / "missing-evaluator", target_is_directory=True
    )
    assert (
        load_public_generated_enterprise_agentic_benchmark(public_only).benchmark
        == generated.public
    )


def test_complete_loader_rejects_coherently_resigned_generated_drift(
    tmp_path: Path,
) -> None:
    generated = generate_enterprise_agentic_world()
    public_artifacts = generated_enterprise_agentic_public_artifacts(generated)
    evaluator_artifacts = generated_enterprise_agentic_evaluator_artifacts(generated)

    public = EnterpriseAgenticGeneratedPublicV1.model_validate_json(
        public_artifacts["public-input.json"]
    )
    organisation = public.benchmark.snapshot.organisations[0].model_copy(
        update={"display_name": "Coherently Altered Example Organisation"}
    )
    snapshot = public.benchmark.snapshot.model_copy(
        update={"organisations": (organisation,)}
    )
    changed_public = public.model_copy(
        update={"benchmark": public.benchmark.model_copy(update={"snapshot": snapshot})}
    )
    public_artifacts["public-input.json"] = canonical_json_bytes(changed_public)
    _rebind_public_manifest(public_artifacts)
    public_digest = generated_enterprise_agentic_artifact_set_sha256(public_artifacts)

    evaluator = EnterpriseAgenticGeneratedEvaluatorV1.model_validate_json(
        evaluator_artifacts["truth.json"]
    ).model_copy(update={"public_artifact_set_sha256": public_digest})
    evaluator_artifacts["truth.json"] = canonical_json_bytes(evaluator)
    _rebind_evaluator_manifest(evaluator_artifacts, public_digest)

    root = tmp_path / "resigned"
    _write_artifact_tree(root / "public", public_artifacts)
    _write_artifact_tree(root / "evaluator", evaluator_artifacts)
    assert (
        load_public_generated_enterprise_agentic_benchmark(root).benchmark.snapshot
        == snapshot
    )
    with pytest.raises(
        EnterpriseAgenticArtifactError,
        match="artifacts differ from declared generation",
    ):
        load_generated_enterprise_agentic_benchmark(root)


def test_complete_loader_rejects_rebound_metric_drift(tmp_path: Path) -> None:
    generated = generate_enterprise_agentic_world()
    public_artifacts = generated_enterprise_agentic_public_artifacts(generated)
    evaluator_artifacts = generated_enterprise_agentic_evaluator_artifacts(generated)
    evaluator = EnterpriseAgenticGeneratedEvaluatorV1.model_validate_json(
        evaluator_artifacts["truth.json"]
    )
    first_count = evaluator.metrics.counts[0]
    changed_count = first_count.model_copy(update={"count": first_count.count - 1})
    changed_metrics = evaluator.metrics.model_copy(
        update={"counts": (changed_count, *evaluator.metrics.counts[1:])}
    )
    changed_evaluator = evaluator.model_copy(update={"metrics": changed_metrics})
    evaluator_artifacts["truth.json"] = canonical_json_bytes(changed_evaluator)
    public_digest = generated_enterprise_agentic_artifact_set_sha256(public_artifacts)
    _rebind_evaluator_manifest(evaluator_artifacts, public_digest)
    root = tmp_path / "metric-drift"
    _write_artifact_tree(root / "public", public_artifacts)
    _write_artifact_tree(root / "evaluator", evaluator_artifacts)

    with pytest.raises(
        EnterpriseAgenticArtifactError,
        match="integrity metrics differ",
    ):
        load_generated_enterprise_agentic_benchmark(root)


def test_generated_loaders_reject_cross_binding_and_inventory_attacks(
    tmp_path: Path,
) -> None:
    first = generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=1)
    )
    second = generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=2)
    )
    swapped = tmp_path / "swapped"
    _write_artifact_tree(
        swapped / "public", generated_enterprise_agentic_public_artifacts(first)
    )
    _write_artifact_tree(
        swapped / "evaluator",
        generated_enterprise_agentic_evaluator_artifacts(second),
    )
    with pytest.raises(
        EnterpriseAgenticArtifactError,
        match="evaluator manifest differs",
    ):
        load_generated_enterprise_agentic_benchmark(swapped)

    complete = tmp_path / "extra-root-entry"
    export_generated_enterprise_agentic_benchmark(complete, first)
    (complete / "receipt.json").write_text("{}\n", encoding="utf-8")
    assert load_public_generated_enterprise_agentic_benchmark(complete)
    with pytest.raises(
        EnterpriseAgenticArtifactError,
        match="root inventory differs",
    ):
        load_generated_enterprise_agentic_benchmark(complete)


def test_complete_loader_rejects_evaluator_binding_and_semantic_drift(
    tmp_path: Path,
) -> None:
    first = generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=1)
    )
    second = generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=2)
    )
    public_artifacts = generated_enterprise_agentic_public_artifacts(first)
    public_digest = generated_enterprise_agentic_artifact_set_sha256(public_artifacts)

    bad_public_binding = generated_enterprise_agentic_evaluator_artifacts(first)
    evaluator = EnterpriseAgenticGeneratedEvaluatorV1.model_validate_json(
        bad_public_binding["truth.json"]
    ).model_copy(update={"public_artifact_set_sha256": "0" * 64})
    bad_public_binding["truth.json"] = canonical_json_bytes(evaluator)
    _rebind_evaluator_manifest(bad_public_binding, public_digest)
    binding_root = tmp_path / "public-binding"
    _write_artifact_tree(binding_root / "public", public_artifacts)
    _write_artifact_tree(binding_root / "evaluator", bad_public_binding)
    with pytest.raises(
        EnterpriseAgenticArtifactError,
        match="evaluator public binding differs",
    ):
        load_generated_enterprise_agentic_benchmark(binding_root)

    identity_drift = generated_enterprise_agentic_evaluator_artifacts(second)
    second_evaluator = EnterpriseAgenticGeneratedEvaluatorV1.model_validate_json(
        identity_drift["truth.json"]
    ).model_copy(update={"public_artifact_set_sha256": public_digest})
    identity_drift["truth.json"] = canonical_json_bytes(second_evaluator)
    _rebind_evaluator_manifest(identity_drift, public_digest)
    identity_root = tmp_path / "identity"
    _write_artifact_tree(identity_root / "public", public_artifacts)
    _write_artifact_tree(identity_root / "evaluator", identity_drift)
    with pytest.raises(
        EnterpriseAgenticArtifactError,
        match="public/evaluator identity differs",
    ):
        load_generated_enterprise_agentic_benchmark(identity_root)

    semantic_drift = generated_enterprise_agentic_evaluator_artifacts(first)
    first_evaluator = EnterpriseAgenticGeneratedEvaluatorV1.model_validate_json(
        semantic_drift["truth.json"]
    )
    binding = first_evaluator.benchmark.bindings[0].model_copy(
        update={"accountable_owner_chain": ("unknown-principal",)}
    )
    evaluator_bundle = first_evaluator.benchmark.model_copy(
        update={"bindings": (binding, *first_evaluator.benchmark.bindings[1:])}
    )
    changed_evaluator = first_evaluator.model_copy(
        update={"benchmark": evaluator_bundle}
    )
    semantic_drift["truth.json"] = canonical_json_bytes(changed_evaluator)
    _rebind_evaluator_manifest(semantic_drift, public_digest)
    semantic_root = tmp_path / "semantic"
    _write_artifact_tree(semantic_root / "public", public_artifacts)
    _write_artifact_tree(semantic_root / "evaluator", semantic_drift)
    with pytest.raises(
        EnterpriseAgenticArtifactError,
        match="public/evaluator bindings are invalid",
    ):
        load_generated_enterprise_agentic_benchmark(semantic_root)

    derived_truth_drift = generated_enterprise_agentic_evaluator_artifacts(first)
    first_evaluator = EnterpriseAgenticGeneratedEvaluatorV1.model_validate_json(
        derived_truth_drift["truth.json"]
    )
    truth = first_evaluator.benchmark.authority_truth[0].model_copy(
        update={"required_evidence_refs": ()}
    )
    evaluator_bundle = first_evaluator.benchmark.model_copy(
        update={
            "authority_truth": (
                truth,
                *first_evaluator.benchmark.authority_truth[1:],
            )
        }
    )
    changed_evaluator = first_evaluator.model_copy(
        update={"benchmark": evaluator_bundle}
    )
    derived_truth_drift["truth.json"] = canonical_json_bytes(changed_evaluator)
    _rebind_evaluator_manifest(derived_truth_drift, public_digest)
    derived_root = tmp_path / "derived-truth"
    _write_artifact_tree(derived_root / "public", public_artifacts)
    _write_artifact_tree(derived_root / "evaluator", derived_truth_drift)
    with pytest.raises(
        EnterpriseAgenticArtifactError,
        match="public/evaluator bindings differ",
    ):
        load_generated_enterprise_agentic_benchmark(derived_root)


def test_public_loader_rejects_file_and_path_type_attacks(tmp_path: Path) -> None:
    generated = generate_enterprise_agentic_world()

    extra = tmp_path / "extra"
    _write_artifact_tree(
        extra / "public", generated_enterprise_agentic_public_artifacts(generated)
    )
    (extra / "public" / "extra.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(EnterpriseAgenticArtifactError, match="inventory differs"):
        load_public_generated_enterprise_agentic_benchmark(extra)

    missing = tmp_path / "missing"
    public_artifacts = generated_enterprise_agentic_public_artifacts(generated)
    public_artifacts.pop("tool_schemas/enterprise-agentic-actions-v1.json")
    _write_artifact_tree(missing / "public", public_artifacts)
    with pytest.raises(EnterpriseAgenticArtifactError, match="inventory differs"):
        load_public_generated_enterprise_agentic_benchmark(missing)

    linked = tmp_path / "linked"
    linked_artifacts = generated_enterprise_agentic_public_artifacts(generated)
    scenario = linked_artifacts.pop("scenarios/enterprise-agentic-smoke-v1.json")
    _write_artifact_tree(linked / "public", linked_artifacts)
    outside = tmp_path / "outside.json"
    outside.write_bytes(scenario)
    (linked / "public" / "scenarios").mkdir()
    (linked / "public" / "scenarios" / "enterprise-agentic-smoke-v1.json").symlink_to(
        outside
    )
    with pytest.raises(EnterpriseAgenticArtifactError, match="non-regular entry"):
        load_public_generated_enterprise_agentic_benchmark(linked)

    fifo = tmp_path / "fifo"
    _write_artifact_tree(
        fifo / "public", generated_enterprise_agentic_public_artifacts(generated)
    )
    os.mkfifo(fifo / "public" / "unexpected-pipe")
    with pytest.raises(EnterpriseAgenticArtifactError, match="non-regular entry"):
        load_public_generated_enterprise_agentic_benchmark(fifo)

    public_is_file = tmp_path / "public-is-file"
    public_is_file.mkdir()
    (public_is_file / "public").write_text("not a directory", encoding="utf-8")
    with pytest.raises(EnterpriseAgenticArtifactError, match="directory is not real"):
        load_public_generated_enterprise_agentic_benchmark(public_is_file)


def test_complete_loader_rejects_root_path_type_attacks(tmp_path: Path) -> None:
    root_is_file = tmp_path / "root-is-file"
    root_is_file.write_text("not a directory", encoding="utf-8")
    with pytest.raises(EnterpriseAgenticArtifactError, match="not a real directory"):
        load_generated_enterprise_agentic_benchmark(root_is_file)

    with pytest.raises(EnterpriseAgenticArtifactError, match="root is unreadable"):
        load_generated_enterprise_agentic_benchmark(tmp_path / "missing-root")

    fifo_root = tmp_path / "fifo-root"
    export_generated_enterprise_agentic_benchmark(
        fifo_root, generate_enterprise_agentic_world()
    )
    os.mkfifo(fifo_root / "unexpected-pipe")
    with pytest.raises(EnterpriseAgenticArtifactError, match="non-regular entry"):
        load_generated_enterprise_agentic_benchmark(fifo_root)


def test_public_loader_rejects_canonical_and_duplicate_artifact_drift(
    tmp_path: Path,
) -> None:
    generated = generate_enterprise_agentic_world()

    noncanonical = tmp_path / "noncanonical"
    artifacts = generated_enterprise_agentic_public_artifacts(generated)
    artifacts["public-input.json"] = artifacts["public-input.json"].replace(
        b"\n", b" \n"
    )
    _rebind_public_manifest(artifacts)
    _write_artifact_tree(noncanonical / "public", artifacts)
    with pytest.raises(EnterpriseAgenticArtifactError, match="not canonical JSON"):
        load_public_generated_enterprise_agentic_benchmark(noncanonical)

    changed_scenario = tmp_path / "changed-scenario"
    artifacts = generated_enterprise_agentic_public_artifacts(generated)
    scenario = generated.public.scenario.model_copy(update={"title": "Changed title"})
    artifacts["scenarios/enterprise-agentic-smoke-v1.json"] = canonical_json_bytes(
        scenario
    )
    _rebind_public_manifest(artifacts)
    _write_artifact_tree(changed_scenario / "public", artifacts)
    with pytest.raises(EnterpriseAgenticArtifactError, match="scenario differs"):
        load_public_generated_enterprise_agentic_benchmark(changed_scenario)

    changed_tool = tmp_path / "changed-tool"
    artifacts = generated_enterprise_agentic_public_artifacts(generated)
    tool = json.loads(artifacts["tool_schemas/enterprise-agentic-actions-v1.json"])
    tool["title"] = "Changed tool"
    artifacts["tool_schemas/enterprise-agentic-actions-v1.json"] = (
        canonical_json_value_bytes(tool)
    )
    _rebind_public_manifest(artifacts)
    _write_artifact_tree(changed_tool / "public", artifacts)
    with pytest.raises(EnterpriseAgenticArtifactError, match="tool schema differs"):
        load_public_generated_enterprise_agentic_benchmark(changed_tool)


def test_public_loader_rejects_manifest_and_tool_encoding_drift(
    tmp_path: Path,
) -> None:
    generated = generate_enterprise_agentic_world()

    changed_manifest = tmp_path / "changed-manifest"
    artifacts = generated_enterprise_agentic_public_artifacts(generated)
    manifest = EnterpriseAgenticGeneratedPublicManifestV1.model_validate_json(
        artifacts["manifest.json"]
    ).model_copy(update={"artifact_set_sha256": "0" * 64})
    artifacts["manifest.json"] = canonical_json_bytes(manifest)
    _write_artifact_tree(changed_manifest / "public", artifacts)
    with pytest.raises(EnterpriseAgenticArtifactError, match="manifest differs"):
        load_public_generated_enterprise_agentic_benchmark(changed_manifest)

    invalid_model = tmp_path / "invalid-model"
    artifacts = generated_enterprise_agentic_public_artifacts(generated)
    artifacts["public-input.json"] = b"{\n"
    _rebind_public_manifest(artifacts)
    _write_artifact_tree(invalid_model / "public", artifacts)
    with pytest.raises(EnterpriseAgenticArtifactError, match="artifact is invalid"):
        load_public_generated_enterprise_agentic_benchmark(invalid_model)

    invalid_tool = tmp_path / "invalid-tool"
    artifacts = generated_enterprise_agentic_public_artifacts(generated)
    artifacts["tool_schemas/enterprise-agentic-actions-v1.json"] = b"{\n"
    _rebind_public_manifest(artifacts)
    _write_artifact_tree(invalid_tool / "public", artifacts)
    with pytest.raises(EnterpriseAgenticArtifactError, match="artifact is invalid"):
        load_public_generated_enterprise_agentic_benchmark(invalid_tool)

    noncanonical_tool = tmp_path / "noncanonical-tool"
    artifacts = generated_enterprise_agentic_public_artifacts(generated)
    artifacts["tool_schemas/enterprise-agentic-actions-v1.json"] = artifacts[
        "tool_schemas/enterprise-agentic-actions-v1.json"
    ].replace(b"\n", b" \n")
    _rebind_public_manifest(artifacts)
    _write_artifact_tree(noncanonical_tool / "public", artifacts)
    with pytest.raises(EnterpriseAgenticArtifactError, match="not canonical JSON"):
        load_public_generated_enterprise_agentic_benchmark(noncanonical_tool)


def test_public_loader_reports_read_failure_after_inventory_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = generate_enterprise_agentic_world()
    root = tmp_path / "read-failure"
    _write_artifact_tree(
        root / "public", generated_enterprise_agentic_public_artifacts(generated)
    )
    blocked = root / "public" / "public-input.json"
    original_read_bytes = Path.read_bytes

    def fail_selected_path(path: Path) -> bytes:
        if path == blocked:
            raise PermissionError("simulated read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_selected_path)
    with pytest.raises(EnterpriseAgenticArtifactError, match="tree is unreadable"):
        load_public_generated_enterprise_agentic_benchmark(root)


def test_generated_cli_validates_and_evaluates_reloaded_public_only_trace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generated = generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=17)
    )
    root = tmp_path / "generated"
    export_generated_enterprise_agentic_benchmark(root, generated)
    public = load_public_generated_enterprise_agentic_benchmark(root)
    submission = AgenticTraceSubmission(
        rows=tuple(
            ObservedActionTrace(event_id=event_id, decision=Decision.DENY)
            for event_id in public.benchmark.scenario.action_event_ids
        )
    )
    trace = tmp_path / "trace.jsonl"
    trace.write_text(trace_submission_to_jsonl(submission), encoding="utf-8")

    validation_args = [
        "validate",
        "generated-enterprise-agentic-trace",
        "--benchmark-root",
        str(root),
        "--predictions",
        str(trace),
    ]
    assert main(validation_args) == 0
    assert "generated-enterprise-agentic-trace: valid" in capsys.readouterr().out
    assert main([*validation_args, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True

    evaluation_args = [
        "evaluate",
        "generated-enterprise-agentic",
        "--benchmark-root",
        str(root),
        "--predictions",
        str(trace),
    ]
    assert main(evaluation_args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checksum_scheme"] == "sha256-generated-enterprise-agentic-v1"
    assert main([*evaluation_args, "--summary"]) == 0
    assert "authorization_decision_accuracy" in capsys.readouterr().out


def test_generated_cli_reports_public_and_evaluator_failures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text("{}\n", encoding="utf-8")
    assert (
        main(
            [
                "validate",
                "generated-enterprise-agentic-trace",
                "--benchmark-root",
                str(tmp_path / "missing"),
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
                "generated-enterprise-agentic",
                "--predictions",
                str(trace),
            ]
        )
        == 1
    )
    assert "--benchmark-root is required" in capsys.readouterr().err
