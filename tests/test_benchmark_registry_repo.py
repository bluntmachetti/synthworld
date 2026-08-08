"""Repository policy tests for the curated benchmark publication registry."""

import json
import pathlib
from typing import Any, cast

from tools.generate_benchmark_registry import discover_generated

ROOT = pathlib.Path(__file__).parents[1]
CURATED = ROOT / "docs/_data/benchmarks.curated.json"
GATES = ROOT / "docs/_data/benchmark-publication-gates.json"

BENCHMARK_FIELDS = {
    "id",
    "title",
    "lifecycle",
    "benchmark_kind",
    "benchmark_version",
    "evaluation_mode",
    "introduced_in",
    "artifact_ids",
    "reproduction",
    "example_command",
    "docs_route_ids",
    "limitations_route_id",
    "publication_gate_id",
    "replacement_id",
}
ARTIFACT_FIELDS = {
    "id",
    "benchmark_id",
    "path",
    "kind",
    "sensitivity",
    "frozen",
    "approved_sha256",
    "integrity_record_ids",
    "present_in",
    "approved_targets",
    "answer_key_label",
}
PUBLICATION_CHECK_IDS = {
    "independent_versions",
    "public_input",
    "evaluator_truth",
    "boundary_validation",
    "checksums",
    "submission_contract",
    "scorer_version",
    "baseline",
    "metric_denominators",
    "limitations",
    "adversarial_review",
    "safety_review",
    "clean_install_reproduction",
    "deterministic_ci_recreation",
    "catalogue_hf_metadata",
}
HUGGING_FACE_TARGETS = {"hugging_face_raw", "hugging_face_viewer"}
PRIVATE_SENSITIVITIES = {
    "private_held_out_truth",
    "operator_private",
    "internal_build_only",
}
PUBLISHED_REPRODUCTION_IDS = {
    "ambiguity-v1",
    "asteria-agentic-v1",
    "authority-governance-v1",
    "connection-v1",
    "core-world-v1",
    "extraction-v1",
    "risk-v1",
}


def _load(path: pathlib.Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def test_registry_has_separate_strict_benchmark_and_artifact_axes() -> None:
    registry = _load(CURATED)
    benchmarks = registry["benchmarks"]
    artifacts = registry["artifacts"]
    assert registry["schema_version"] == "1.0.0"
    assert all(set(item) == BENCHMARK_FIELDS for item in benchmarks)
    assert all(set(item) == ARTIFACT_FIELDS for item in artifacts)
    assert {item["lifecycle"] for item in benchmarks} <= {
        "experimental",
        "candidate",
        "published",
        "superseded",
    }
    assert {item["benchmark_kind"] for item in benchmarks} <= {
        "frozen_fixture",
        "conformance_fixture",
        "generated_profile",
        "generated_benchmark",
        "projection",
    }
    assert {item["sensitivity"] for item in artifacts} <= {
        "public_input",
        "public_reference_truth",
        "private_held_out_truth",
        "operator_private",
        "internal_build_only",
    }
    assert "generated_profile" not in {item["lifecycle"] for item in benchmarks}
    assert "held_out_private" not in {item["lifecycle"] for item in benchmarks}


def test_benchmark_kinds_have_the_correct_evaluation_mode() -> None:
    benchmarks = _load(CURATED)["benchmarks"]
    expected_modes = {
        "frozen_fixture": "public_reference",
        "conformance_fixture": "public_conformance",
        "generated_profile": "profile_smoke",
        "generated_benchmark": "generated_evaluation",
        "projection": "public_reference",
    }
    assert len(benchmarks) == 15
    assert all(
        item["evaluation_mode"] == expected_modes[item["benchmark_kind"]]
        for item in benchmarks
    )


def test_reproduction_contract_distinguishes_published_replay_from_examples() -> None:
    benchmarks = _load(CURATED)["benchmarks"]
    published = [item for item in benchmarks if item["lifecycle"] == "published"]
    candidates = [item for item in benchmarks if item["lifecycle"] == "candidate"]

    assert {item["id"] for item in published} == PUBLISHED_REPRODUCTION_IDS
    assert all(item["example_command"] is None for item in published)
    for item in published:
        reproduction = item["reproduction"]
        assert reproduction["mode"] == "regenerate_and_compare"
        assert reproduction["argv"] == [
            "synthworld",
            "reproduce-benchmark",
            "--benchmark",
            item["id"],
            "--output",
            "{output_dir}",
        ]

    assert len(candidates) == 8
    assert all(item["reproduction"] is None for item in candidates)
    assert all(isinstance(item["example_command"], str) for item in candidates)
    assert all(
        "reproduce-benchmark" not in item["example_command"] for item in candidates
    )


def test_registry_assigns_the_exact_generated_benchmark_inventory_once() -> None:
    registry = _load(CURATED)
    artifacts = registry["artifacts"]
    public_artifacts = [
        item for item in artifacts if item["sensitivity"] not in PRIVATE_SENSITIVITIES
    ]
    private_artifacts = [
        item for item in artifacts if item["sensitivity"] in PRIVATE_SENSITIVITIES
    ]
    assert all(item["path"] is not None for item in public_artifacts)
    assert all(item["approved_sha256"] is not None for item in public_artifacts)
    assert all(item["path"] is None for item in private_artifacts)
    assert all(item["approved_sha256"] is None for item in private_artifacts)
    assigned_paths = [cast(str, item["path"]) for item in public_artifacts]
    generated_paths = {
        cast(str, item["path"]) for item in discover_generated(ROOT)["artifacts"]
    }
    assert len(generated_paths) == 46
    assert set(assigned_paths) == generated_paths
    assert len(assigned_paths) == len(set(assigned_paths)) == 46
    artifact_ids = [item["id"] for item in artifacts]
    assert len(artifact_ids) == len(set(artifact_ids))
    benchmark_ids = {item["id"] for item in registry["benchmarks"]}
    assert {item["benchmark_id"] for item in artifacts} <= benchmark_ids
    assert all(item["approved_sha256"] for item in public_artifacts)


def test_evaluator_truth_is_explicitly_public_reference_not_path_inference() -> None:
    artifacts = _load(CURATED)["artifacts"]
    evaluator_artifacts = [
        item
        for item in artifacts
        if isinstance(item["path"], str) and "/evaluator/" in item["path"]
    ]
    assert evaluator_artifacts
    assert all(
        item["sensitivity"] == "public_reference_truth" for item in evaluator_artifacts
    )
    assert all(item["answer_key_label"] for item in evaluator_artifacts)
    assert not {
        item["path"]
        for item in artifacts
        if item["sensitivity"] in PRIVATE_SENSITIVITIES
    }


def test_candidates_have_no_hugging_face_authorization() -> None:
    registry = _load(CURATED)
    benchmarks = {item["id"]: item for item in registry["benchmarks"]}
    artifacts = registry["artifacts"]
    artifact_benchmarks = {item["benchmark_id"] for item in artifacts}
    candidate_ids = {
        "ambiguity-v2",
        "search-projection",
        "temporal-broker-removal",
        "enterprise-identity-fabric",
        "enterprise-agentic",
        "contextual-access",
        "continuous-assurance",
    }
    assert candidate_ids <= set(benchmarks)
    assert all(benchmarks[item]["lifecycle"] == "candidate" for item in candidate_ids)
    assert not candidate_ids & artifact_benchmarks
    assert "households-smoke-v1" in artifact_benchmarks
    assert all(
        not (set(item["approved_targets"]) & HUGGING_FACE_TARGETS) for item in artifacts
    )
    assert all("standards" not in item["id"] for item in benchmarks.values())


def test_published_benchmarks_have_complete_honest_approved_gates() -> None:
    registry = _load(CURATED)
    gates = _load(GATES)["gates"]
    by_gate_id = {item["id"]: item for item in gates}
    published = [
        item for item in registry["benchmarks"] if item["lifecycle"] == "published"
    ]
    assert len(published) == len(gates) == 7
    assert all(item["publication_gate_id"] in by_gate_id for item in published)
    assert all(item["decision"] == "approved" for item in gates)
    assert all(item["release_tag"].startswith("v") for item in gates)
    assert all(
        item["review_route_id"].startswith("route:GOLDEN_REVIEW.md#") for item in gates
    )
    assert all(
        not (set(item["approved_targets"]) & HUGGING_FACE_TARGETS) for item in gates
    )
    for gate in gates:
        checks = gate["checks"]
        assert len(checks) == 15
        assert {item["name"] for item in checks} == PUBLICATION_CHECK_IDS
        assert "pending" not in {item["status"] for item in checks}
        assert all(
            item["status"] != "not_applicable" or item["rationale"] for item in checks
        )


def test_make_ci_and_ownership_require_registry_governance() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    owners = (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
    assert "benchmark-registry:" in makefile
    assert "benchmark-registry-check:" in makefile
    assert "generate_benchmark_registry.py --check" in makefile
    assert "generate_benchmark_registry.py --check-wheel $(WHEEL)" in makefile
    assert "generate_benchmark_registry.py --check-reproduction $(WHEEL)" in makefile
    package = makefile.split("package:", maxsplit=1)[1].split("\ntest:", maxsplit=1)[0]
    assert package.index("--check-wheel $(WHEEL)") < package.index(
        "--check-reproduction $(WHEEL)"
    )
    assert "benchmark-registry-check" in makefile.split("ci:", maxsplit=1)[1]
    assert '"--cov=tools"' in project
    assert "name: Benchmark registry governance" in workflow
    benchmark_job = workflow.split("name: Benchmark registry governance", 1)[1].split(
        "\n  quality:", 1
    )[0]
    assert "fetch-depth: 0" in benchmark_job
    assert "--check --require-tags --base-ref origin/main" in benchmark_job
    owner_patterns = {
        line.split()[0]
        for line in owners.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for pattern in (
        "/src/synthworld/benchmarks/**",
        "/src/synthworld/benchmark_reproduction.py",
        "/GOLDEN_REVIEW.md",
        "/huggingface/**",
        "/docs/_data/**",
        "/docs/_schemas/**",
        "/tools/**",
        "/tests/**",
    ):
        assert pattern in owner_patterns


def test_hugging_face_card_is_current_about_package_scope_and_authorization() -> None:
    card = (ROOT / "huggingface/README.md").read_text(encoding="utf-8")
    semantic_card = " ".join(card.split())
    assert "id" + "cognito-synthworld==0.13.0" in semantic_card
    assert (
        "historical partial publication view, not the publication authorization source"
        in semantic_card
    )
    assert "does not authorize additional Hugging Face artifacts" in semantic_card
