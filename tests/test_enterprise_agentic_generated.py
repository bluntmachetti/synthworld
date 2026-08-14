"""Generated enterprise-agentic smoke configuration, graph, and artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.agentic import (
    AgenticBenchmark,
    AgenticBenchmarkIntegrityError,
    build_agentic_benchmark,
    reference_agentic_trace,
)
from synthworld.agentic.enterprise import (
    EnterpriseAgenticGenerationConfigV1,
    EnterpriseAgenticSmokeTopologyV1,
    derive_enterprise_agentic_integrity_metrics,
    evaluate_generated_enterprise_agentic_trace,
    export_generated_enterprise_agentic_benchmark,
    generate_enterprise_agentic_world,
    generated_enterprise_agentic_artifact_checksums,
    generated_enterprise_agentic_evaluator_artifacts,
    generated_enterprise_agentic_public_artifacts,
)
from synthworld.agentic.enterprise.generated_models import (
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


def _benchmark(generated: EnterpriseAgenticGeneratedBenchmarkV1) -> AgenticBenchmark:
    return AgenticBenchmark(public=generated.public, evaluator=generated.evaluator)


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
