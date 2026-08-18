from __future__ import annotations

import json
import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from synthworld.agentic import generate_asteria_agentic_v1
from synthworld.agentic.models import AgenticBenchmark
from synthworld.agentic.serialization import export_agentic_benchmark
from synthworld.cli import main
from synthworld.explorer import (
    EVALUATOR_WATERMARK,
    PUBLISHED_ASTERIA_PUBLIC_ARTIFACT_SET_DIGEST,
    ExplorerLayoutManifestV2,
    ExplorerPublicProjectionV1,
    ExplorerRenderError,
    load_asteria_agent_authority_layout,
    project_asteria_agent_authority_evaluator_v1,
    project_asteria_agent_authority_v1,
    render_asteria_agent_authority_package,
    render_explorer_html,
    rendering,
    write_asteria_agent_authority_html,
)
from synthworld.explorer.serialization import canonical_json_bytes


@pytest.fixture
def asteria_package(tmp_path: Path) -> tuple[Path, AgenticBenchmark]:
    benchmark = generate_asteria_agentic_v1()
    root = tmp_path / "asteria-agentic-v1"
    export_agentic_benchmark(root, benchmark)
    return root, benchmark


def _published_projection() -> ExplorerPublicProjectionV1:
    benchmark = generate_asteria_agentic_v1()
    return project_asteria_agent_authority_v1(
        benchmark.public,
        public_artifact_set_digest=PUBLISHED_ASTERIA_PUBLIC_ARTIFACT_SET_DIGEST,
    )


def _copied_asset_root(tmp_path: Path) -> Path:
    package_root = tmp_path / "package"
    source = files("synthworld.explorer").joinpath("assets")
    shutil.copytree(Path(str(source)), package_root / "assets")
    return package_root


def test_packaged_explorer_assets_are_bound_and_layout_is_canonical() -> None:
    assets, manifest = rendering._asset_bytes()
    layout = load_asteria_agent_authority_layout()

    assert set(assets) == {
        "THIRD_PARTY_NOTICES.txt",
        "asteria-agent-authority-v1.layout.json",
        "explorer.bundle.js",
        "explorer.css",
    }
    assert manifest["dependencies"] == [
        {"license": "MIT", "name": "cytoscape", "version": "3.34.1"},
        {
            "license": "EPL-2.0 OR GPL-3.0-or-later",
            "name": "elkjs",
            "version": "0.12.0",
        },
    ]
    assert layout.options.engine_version == "0.12.0"
    assert layout.world_seed == _published_projection().source.seed
    assert layout.world_schema_version == "1.0.0"
    assert layout.visualisation_profile == "agent-authority"
    assert layout.visualisation_profile_version == "1.0.0"
    assert (
        canonical_json_bytes(layout) == assets["asteria-agent-authority-v1.layout.json"]
    )


@pytest.mark.parametrize("manifest_payload", [None, b"{", b"\xff"])
def test_asset_loader_rejects_an_unavailable_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_payload: bytes | None,
) -> None:
    package_root = tmp_path / "package"
    asset_root = package_root / "assets"
    asset_root.mkdir(parents=True)
    if manifest_payload is not None:
        (asset_root / "manifest.json").write_bytes(manifest_payload)
    monkeypatch.setattr(rendering, "files", lambda package: package_root)

    with pytest.raises(ExplorerRenderError, match="manifest is unavailable"):
        rendering._asset_bytes()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ([], "manifest is invalid"),
        ({"schema_version": "2.0.0"}, "manifest is invalid"),
        ({"schema_version": "1.0.0", "artifacts": []}, "inventory differs"),
        ({"schema_version": "1.0.0", "artifacts": {}}, "inventory differs"),
    ],
)
def test_asset_loader_rejects_invalid_manifest_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: object,
    message: str,
) -> None:
    package_root = _copied_asset_root(tmp_path)
    (package_root / "assets" / "manifest.json").write_text(
        json.dumps(mutation), encoding="utf-8"
    )
    monkeypatch.setattr(rendering, "files", lambda package: package_root)

    with pytest.raises(ExplorerRenderError, match=message):
        rendering._asset_bytes()


def test_asset_loader_rejects_missing_and_changed_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = _copied_asset_root(tmp_path)
    asset_root = package_root / "assets"
    monkeypatch.setattr(rendering, "files", lambda package: package_root)
    missing = asset_root / "explorer.css"
    missing.unlink()
    with pytest.raises(ExplorerRenderError, match="asset is unavailable"):
        rendering._asset_bytes()

    package_root = _copied_asset_root(tmp_path / "changed")
    asset_root = package_root / "assets"
    monkeypatch.setattr(rendering, "files", lambda package: package_root)
    manifest = json.loads((asset_root / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"]["explorer.css"] = "not-a-descriptor"
    (asset_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ExplorerRenderError, match="asset binding differs"):
        rendering._asset_bytes()

    manifest["artifacts"]["explorer.css"] = {
        "byte_size": -1,
        "sha256": "0" * 64,
    }
    (asset_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ExplorerRenderError, match="asset binding differs"):
        rendering._asset_bytes()

    payload = (asset_root / "explorer.css").read_bytes()
    manifest["artifacts"]["explorer.css"] = {
        "byte_size": len(payload),
        "sha256": "0" * 64,
    }
    (asset_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ExplorerRenderError, match="asset binding differs"):
        rendering._asset_bytes()


def test_layout_loader_rejects_invalid_and_noncanonical_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assets, manifest = rendering._asset_bytes()
    malformed = {**assets, "asteria-agent-authority-v1.layout.json": b"{}"}
    monkeypatch.setattr(rendering, "_asset_bytes", lambda: (malformed, manifest))
    with pytest.raises(ExplorerRenderError, match="layout asset is invalid"):
        load_asteria_agent_authority_layout()

    layout = ExplorerLayoutManifestV2.model_validate_json(
        assets["asteria-agent-authority-v1.layout.json"]
    )
    noncanonical = json.dumps(layout.model_dump(mode="json"), indent=2).encode()
    changed = {
        **assets,
        "asteria-agent-authority-v1.layout.json": noncanonical,
    }
    monkeypatch.setattr(rendering, "_asset_bytes", lambda: (changed, manifest))
    with pytest.raises(ExplorerRenderError, match="not canonical JSON"):
        load_asteria_agent_authority_layout()


def test_public_and_evaluator_html_are_deterministic_offline_and_separate() -> None:
    benchmark = generate_asteria_agentic_v1()
    projection = project_asteria_agent_authority_v1(
        benchmark.public,
        public_artifact_set_digest=PUBLISHED_ASTERIA_PUBLIC_ARTIFACT_SET_DIGEST,
    )
    overlay = project_asteria_agent_authority_evaluator_v1(
        projection,
        benchmark.evaluator,
        evaluator_artifact_set_digest="b" * 64,
    )

    public_html = render_explorer_html(projection)
    evaluator_html = render_explorer_html(projection, overlay=overlay)

    assert public_html == render_explorer_html(projection)
    assert public_html.startswith(b"<!doctype html>\n")
    assert b"connect-src 'none'" in public_html
    assert b'<script src="http' not in public_html
    assert b'<link href="http' not in public_html
    assert b'id="synthworld-evaluator-overlay"' not in public_html
    assert EVALUATOR_WATERMARK.encode() not in public_html
    assert b"public projection only" in public_html
    assert evaluator_html != public_html
    assert b'id="synthworld-evaluator-overlay"' in evaluator_html
    assert EVALUATOR_WATERMARK.encode() in evaluator_html
    assert b"Expected authority decision" in evaluator_html
    assert b"evaluator truth explicitly enabled" in evaluator_html
    assert b"Cytoscape.js 3.34.1" in evaluator_html
    assert b"ELK.js 0.12.0" in evaluator_html


def test_rendering_escapes_embedded_json_and_rejects_wrong_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = _published_projection()
    unsafe_projection = projection.model_copy(
        update={
            "nodes": (
                projection.nodes[0].model_copy(update={"label": "</script>"}),
                *projection.nodes[1:],
            )
        }
    )
    assert "\\u003c" in rendering._safe_json(unsafe_projection)

    for changed in (
        projection.model_copy(update={"profile": "unsupported"}),
        projection.model_copy(
            update={
                "source": projection.source.model_copy(
                    update={"public_artifact_set_digest": "0" * 64}
                )
            }
        ),
    ):
        with pytest.raises(ExplorerRenderError, match="only the published Asteria"):
            render_explorer_html(changed)

    layout = load_asteria_agent_authority_layout()
    monkeypatch.setattr(
        rendering,
        "load_asteria_agent_authority_layout",
        lambda: layout.model_copy(update={"public_projection_digest": "0" * 64}),
    )
    with pytest.raises(ExplorerRenderError, match="does not bind"):
        render_explorer_html(projection)


@pytest.mark.parametrize(
    "asset_name,terminator",
    [("explorer.css", b"</style>"), ("explorer.bundle.js", b"</script>")],
)
def test_rendering_rejects_unsafe_inline_bundle_terminators(
    monkeypatch: pytest.MonkeyPatch,
    asset_name: str,
    terminator: bytes,
) -> None:
    projection = _published_projection()
    assets, manifest = rendering._asset_bytes()
    changed = {**assets, asset_name: terminator}
    monkeypatch.setattr(rendering, "_asset_bytes", lambda: (changed, manifest))

    with pytest.raises(ExplorerRenderError, match="cannot be embedded safely"):
        render_explorer_html(projection)


def test_evaluator_projector_requires_matching_identity_and_action_inventory() -> None:
    benchmark = generate_asteria_agentic_v1()
    projection = project_asteria_agent_authority_v1(
        benchmark.public,
        public_artifact_set_digest=PUBLISHED_ASTERIA_PUBLIC_ARTIFACT_SET_DIGEST,
    )
    with pytest.raises(ValueError, match="identity does not match"):
        project_asteria_agent_authority_evaluator_v1(
            projection,
            benchmark.evaluator.model_copy(update={"world_id": "different-world"}),
            evaluator_artifact_set_digest="b" * 64,
        )
    with pytest.raises(ValueError, match="action inventory differs"):
        project_asteria_agent_authority_evaluator_v1(
            projection,
            benchmark.evaluator.model_copy(
                update={"bindings": benchmark.evaluator.bindings[:-1]}
            ),
            evaluator_artifact_set_digest="b" * 64,
        )


def test_package_renderer_verifies_public_and_optional_evaluator_packages(
    asteria_package: tuple[Path, AgenticBenchmark],
) -> None:
    root, _ = asteria_package
    public_html = render_asteria_agent_authority_package(public_package=root / "public")
    evaluator_html = render_asteria_agent_authority_package(
        public_package=root / "public",
        evaluator_package=root / "evaluator",
    )

    assert b"public projection only" in public_html
    assert b'id="synthworld-evaluator-overlay"' not in public_html
    assert b"evaluator truth explicitly enabled" in evaluator_html
    assert EVALUATOR_WATERMARK.encode() in evaluator_html


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "manifest is unavailable"),
        (b"{", "manifest is unavailable"),
        (b"\xff", "manifest is unavailable"),
        (b"[]", "manifest is invalid"),
        (b'{"artifact_set_digest":"wrong"}', "not the published Asteria"),
    ],
)
def test_package_renderer_rejects_invalid_public_manifests(
    tmp_path: Path,
    payload: bytes | None,
    message: str,
) -> None:
    public = tmp_path / "public"
    public.mkdir()
    if payload is not None:
        (public / "manifest.json").write_bytes(payload)

    with pytest.raises(ExplorerRenderError, match=message):
        render_asteria_agent_authority_package(public_package=public)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "checksums are unavailable"),
        (b"{", "checksums are unavailable"),
        (b"\xff", "checksums are unavailable"),
        (b"[]", "checksums are invalid"),
        (b"{}", "evaluator digest is unavailable"),
    ],
)
def test_package_renderer_rejects_invalid_evaluator_checksums(
    asteria_package: tuple[Path, AgenticBenchmark],
    tmp_path: Path,
    payload: bytes | None,
    message: str,
) -> None:
    root, _ = asteria_package
    evaluator = tmp_path / "evaluator-copy"
    shutil.copytree(root / "evaluator", evaluator)
    (evaluator / "checksums.json").unlink()
    if payload is not None:
        (evaluator / "checksums.json").write_bytes(payload)

    with pytest.raises(ExplorerRenderError, match=message):
        render_asteria_agent_authority_package(
            public_package=root / "public", evaluator_package=evaluator
        )


def test_writer_and_cli_create_new_public_and_evaluator_html(
    asteria_package: tuple[Path, AgenticBenchmark],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, _ = asteria_package
    public_output = tmp_path / "public.html"
    write_asteria_agent_authority_html(public_output, public_package=root / "public")
    assert b"public projection only" in public_output.read_bytes()

    evaluator_output = tmp_path / "evaluator.html"
    exit_code = main(
        [
            "visualize",
            "--public-package",
            str(root / "public"),
            "--evaluator-package",
            str(root / "evaluator"),
            "--view",
            "agent-authority",
            "--output",
            str(evaluator_output),
        ]
    )
    assert exit_code == 0
    assert EVALUATOR_WATERMARK.encode() in evaluator_output.read_bytes()
    assert "agent-authority (evaluator)" in capsys.readouterr().out

    exit_code = main(
        [
            "visualize",
            "--public-package",
            str(root / "public"),
            "--view",
            "agent-authority",
            "--output",
            str(evaluator_output),
        ]
    )
    assert exit_code == 1
    assert "File exists" in capsys.readouterr().err


def test_cli_reports_package_validation_errors(
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
            "--output",
            str(tmp_path / "world.html"),
        ]
    )

    assert exit_code == 1
    assert (
        "visualize: Asteria public manifest is unavailable" in capsys.readouterr().err
    )
