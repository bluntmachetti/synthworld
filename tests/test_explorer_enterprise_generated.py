from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from synthworld.agentic.enterprise import (
    EnterpriseAgenticArtifactError,
    EnterpriseAgenticGenerationConfigV1,
    export_generated_enterprise_agentic_benchmark,
    generate_enterprise_agentic_world,
    generated_enterprise_agentic_artifact_checksums,
    generated_enterprise_agentic_public_artifact_set_sha256,
)
from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticGeneratedBenchmarkV1,
    EnterpriseAgenticGeneratedPublicV1,
)
from synthworld.cli import main
from synthworld.explorer import (
    EVALUATOR_WATERMARK,
    ExplorerEdgeKind,
    ExplorerEnterpriseGeneratedProjectionV1,
    ExplorerEnterpriseGeneratedSourceV1,
    ExplorerNodeKind,
    ExplorerRenderError,
    canonical_json_bytes,
    compute_generated_enterprise_agentic_layout,
    explorer_digest,
    is_supported_generated_projection,
    project_generated_enterprise_agentic_evaluator_v1,
    project_generated_enterprise_agentic_v1,
    render_generated_enterprise_agentic_html,
    render_generated_enterprise_agentic_package,
    validate_generated_layout,
)


@pytest.fixture(scope="module")
def generated_benchmark() -> EnterpriseAgenticGeneratedBenchmarkV1:
    return generate_enterprise_agentic_world(EnterpriseAgenticGenerationConfigV1())


@pytest.fixture(scope="module")
def generated_package(
    tmp_path_factory: pytest.TempPathFactory,
    generated_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> Path:
    root = tmp_path_factory.mktemp("generated") / "enterprise-agentic-generated"
    export_generated_enterprise_agentic_benchmark(root, generated_benchmark)
    return root


def _public_model(
    generated: EnterpriseAgenticGeneratedBenchmarkV1,
) -> EnterpriseAgenticGeneratedPublicV1:
    return EnterpriseAgenticGeneratedPublicV1(
        config=generated.config,
        identity=generated.identity,
        benchmark=generated.public,
    )


def _empty_projection() -> ExplorerEnterpriseGeneratedProjectionV1:
    return ExplorerEnterpriseGeneratedProjectionV1(
        source=ExplorerEnterpriseGeneratedSourceV1(
            profile_version="enterprise-agentic-generated-1.0.0",
            generator_version="1.0.0",
            canonical_serialization_version="1.0.0",
            event_schedule_version="smoke-1.0.0",
            tier="smoke",
            seed=1,
            configuration_sha256="a" * 64,
            world_id="synthetic-world",
            world_version="enterprise-agentic-generated-1.0.0",
            world_schema_version="1.0.0",
            public_artifact_set_sha256="b" * 64,
        ),
        nodes=(),
        edges=(),
        timeline=(),
    )


def test_generated_projection_is_deterministic_and_answer_independent(
    generated_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    public = _public_model(generated_benchmark)
    projection = project_generated_enterprise_agentic_v1(public)
    repeated = project_generated_enterprise_agentic_v1(public)

    assert projection == repeated
    assert explorer_digest(projection) == explorer_digest(repeated)
    assert projection.profile == "enterprise-agentic-generated-v1"
    assert projection.visibility == "public"
    assert is_supported_generated_projection(projection)
    assert projection.source.benchmark_id == "enterprise-agentic-generated"
    assert projection.source.lifecycle == "generated"
    assert projection.source.tier == "smoke"
    assert projection.source.seed == generated_benchmark.identity.seed
    assert projection.source.world_id == generated_benchmark.identity.world_id
    assert projection.source.configuration_sha256 == (
        generated_benchmark.identity.configuration_sha256
    )
    assert projection.source.public_artifact_set_sha256 == (
        generated_enterprise_agentic_public_artifact_set_sha256(public)
    )

    serialized = canonical_json_bytes(projection)
    for forbidden in (
        b"authority_truth",
        b"canonical_binding",
        b"case_kind",
        b"expected_decision",
        b"failure_reason",
    ):
        assert forbidden not in serialized


def test_generated_projection_covers_required_entities_and_relationships(
    generated_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    projection = project_generated_enterprise_agentic_v1(
        _public_model(generated_benchmark)
    )

    node_kinds = {node.kind for node in projection.nodes}
    assert {
        ExplorerNodeKind.ORGANISATION,
        ExplorerNodeKind.DEPARTMENT,
        ExplorerNodeKind.PRINCIPAL,
        ExplorerNodeKind.LOGICAL_AGENT,
        ExplorerNodeKind.RUNTIME,
        ExplorerNodeKind.CREDENTIAL,
        ExplorerNodeKind.DELEGATION,
        ExplorerNodeKind.RESOURCE,
        ExplorerNodeKind.ACTION_ATTEMPT,
    } <= node_kinds
    edge_kinds = {edge.kind for edge in projection.edges}
    assert {
        ExplorerEdgeKind.CONTAINS,
        ExplorerEdgeKind.OWNS,
        ExplorerEdgeKind.DELEGATES,
        ExplorerEdgeKind.GRANTS_TO,
        ExplorerEdgeKind.ISSUES,
        ExplorerEdgeKind.EXECUTES_ON,
        ExplorerEdgeKind.RUNS_AS,
        ExplorerEdgeKind.PRESENTS,
        ExplorerEdgeKind.ATTEMPTS,
    } <= edge_kinds
    assert projection.timeline


def test_generated_projector_rejects_unsupported_package_identities(
    generated_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    public = _public_model(generated_benchmark)
    unsupported = public.model_copy(
        update={
            "identity": public.identity.model_copy(
                update={"profile_version": "enterprise-agentic-generated-2.0.0"}
            )
        }
    )

    with pytest.raises(ValueError, match="smoke profile"):
        project_generated_enterprise_agentic_v1(unsupported)


def test_generated_layout_is_deterministic_bound_and_complete(
    generated_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    projection = project_generated_enterprise_agentic_v1(
        _public_model(generated_benchmark)
    )
    layout = compute_generated_enterprise_agentic_layout(projection)

    assert layout == compute_generated_enterprise_agentic_layout(projection)
    assert layout.public_projection_digest == explorer_digest(projection)
    assert layout.world_id == projection.source.world_id
    assert layout.world_seed == projection.source.seed
    assert layout.options.engine == "synthworld-grid"
    validate_generated_layout(projection, layout)

    with pytest.raises(ValueError, match="does not bind"):
        validate_generated_layout(
            projection,
            layout.model_copy(update={"public_projection_digest": "0" * 64}),
        )
    with pytest.raises(ValueError, match="identity does not match"):
        validate_generated_layout(
            projection,
            layout.model_copy(update={"world_seed": projection.source.seed + 1}),
        )
    with pytest.raises(ValueError, match="at least one node"):
        compute_generated_enterprise_agentic_layout(_empty_projection())


def test_generated_evaluator_overlay_requires_matching_identity(
    generated_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    projection = project_generated_enterprise_agentic_v1(
        _public_model(generated_benchmark)
    )
    overlay = project_generated_enterprise_agentic_evaluator_v1(
        projection,
        generated_benchmark.evaluator,
        evaluator_artifact_set_digest="b" * 64,
    )

    assert overlay.public_projection_digest == explorer_digest(projection)
    assert overlay.evaluator_artifact_set_digest == "b" * 64
    assert overlay.watermark == EVALUATOR_WATERMARK
    assert overlay.annotations

    with pytest.raises(ValueError, match="identity does not match"):
        project_generated_enterprise_agentic_evaluator_v1(
            projection,
            generated_benchmark.evaluator.model_copy(
                update={"world_id": "different-world"}
            ),
            evaluator_artifact_set_digest="b" * 64,
        )
    with pytest.raises(ValueError, match="action inventory differs"):
        project_generated_enterprise_agentic_evaluator_v1(
            projection,
            generated_benchmark.evaluator.model_copy(
                update={"bindings": generated_benchmark.evaluator.bindings[:-1]}
            ),
            evaluator_artifact_set_digest="b" * 64,
        )


def test_generated_html_is_deterministic_offline_and_separate(
    generated_package: Path,
) -> None:
    public_html = render_generated_enterprise_agentic_package(
        public_package=generated_package / "public"
    )
    evaluator_html = render_generated_enterprise_agentic_package(
        public_package=generated_package / "public",
        evaluator_package=generated_package / "evaluator",
    )

    assert public_html == render_generated_enterprise_agentic_package(
        public_package=generated_package / "public"
    )
    assert public_html.startswith(b"<!doctype html>\n")
    assert b"connect-src 'none'" in public_html
    assert b'<script src="http' not in public_html
    assert b'<link href="http' not in public_html
    assert b"Generated enterprise agent authority" in public_html
    assert b'id="synthworld-evaluator-overlay"' not in public_html
    assert EVALUATOR_WATERMARK.encode() not in public_html
    assert b"public projection only" in public_html
    for forbidden in (
        b"authority_truth",
        b"expected_decision",
        b"Expected authority decision",
        b"Canonical identity binding",
        b"Evaluator case",
        b"Expected failure reasons",
    ):
        assert forbidden not in public_html
    assert evaluator_html != public_html
    assert b'id="synthworld-evaluator-overlay"' in evaluator_html
    assert EVALUATOR_WATERMARK.encode() in evaluator_html
    assert b"Expected authority decision" in evaluator_html
    assert b"evaluator truth explicitly enabled" in evaluator_html


def test_generated_evaluator_overlay_binds_package_digests(
    generated_package: Path,
    generated_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    evaluator_html = render_generated_enterprise_agentic_package(
        public_package=generated_package / "public",
        evaluator_package=generated_package / "evaluator",
    )
    checksums = dict(
        generated_enterprise_agentic_artifact_checksums(generated_benchmark)
    )
    evaluator_manifest = json.loads(
        (generated_package / "evaluator" / "manifest.json").read_text(encoding="utf-8")
    )

    assert checksums["evaluator"].encode() in evaluator_html
    assert evaluator_manifest["artifact_set_sha256"] == checksums["evaluator"]

    projection = project_generated_enterprise_agentic_v1(
        _public_model(generated_benchmark)
    )
    assert projection.source.public_artifact_set_sha256 == checksums["public"]
    assert (
        evaluator_manifest["public_artifact_set_sha256"]
        == projection.source.public_artifact_set_sha256
    )


def test_generated_renderer_rejects_unsupported_or_unbound_inputs(
    generated_benchmark: EnterpriseAgenticGeneratedBenchmarkV1,
) -> None:
    projection = project_generated_enterprise_agentic_v1(
        _public_model(generated_benchmark)
    )
    unsupported = projection.model_copy(
        update={"source": projection.source.model_copy(update={"tier": "standard"})}
    )
    with pytest.raises(ExplorerRenderError, match="smoke profile"):
        render_generated_enterprise_agentic_html(unsupported)

    overlay = project_generated_enterprise_agentic_evaluator_v1(
        projection,
        generated_benchmark.evaluator,
        evaluator_artifact_set_digest="b" * 64,
    )
    unbound = overlay.model_copy(update={"public_projection_digest": "0" * 64})
    with pytest.raises(ExplorerRenderError, match="does not bind"):
        render_generated_enterprise_agentic_html(projection, overlay=unbound)


def test_generated_package_renderer_rejects_missing_and_tampered_trees(
    generated_package: Path,
    tmp_path: Path,
) -> None:
    with pytest.raises(
        EnterpriseAgenticArtifactError, match=r"unreadable|inventory differs"
    ):
        render_generated_enterprise_agentic_package(public_package=tmp_path / "missing")

    tampered = tmp_path / "tampered"
    shutil.copytree(generated_package, tampered)
    (tampered / "evaluator" / "truth.json").write_bytes(b"{}")
    with pytest.raises(EnterpriseAgenticArtifactError, match="manifest differs"):
        render_generated_enterprise_agentic_package(
            public_package=tampered / "public",
            evaluator_package=tampered / "evaluator",
        )


def test_cli_renders_generated_public_and_evaluator_html(
    generated_package: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "generated.html"
    exit_code = main(
        [
            "visualize",
            "--public-package",
            str(generated_package / "public"),
            "--evaluator-package",
            str(generated_package / "evaluator"),
            "--view",
            "agent-authority",
            "--package-profile",
            "generated-enterprise-agentic",
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    assert EVALUATOR_WATERMARK.encode() in output.read_bytes()
    assert "agent-authority (evaluator)" in capsys.readouterr().out

    exit_code = main(
        [
            "visualize",
            "--public-package",
            str(generated_package / "public"),
            "--view",
            "agent-authority",
            "--package-profile",
            "generated-enterprise-agentic",
            "--output",
            str(output),
        ]
    )
    assert exit_code == 1
    assert "File exists" in capsys.readouterr().err

    public_output = tmp_path / "generated-public.html"
    exit_code = main(
        [
            "visualize",
            "--public-package",
            str(generated_package / "public"),
            "--view",
            "agent-authority",
            "--package-profile",
            "generated-enterprise-agentic",
            "--output",
            str(public_output),
        ]
    )
    assert exit_code == 0
    payload = public_output.read_bytes()
    assert b"public projection only" in payload
    assert EVALUATOR_WATERMARK.encode() not in payload
    assert "agent-authority (public)" in capsys.readouterr().out


def test_cli_reports_generated_package_validation_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "visualize",
            "--public-package",
            str(tmp_path / "missing"),
            "--view",
            "agent-authority",
            "--package-profile",
            "generated-enterprise-agentic",
            "--output",
            str(tmp_path / "world.html"),
        ]
    )

    assert exit_code == 1
    assert "visualize:" in capsys.readouterr().err
