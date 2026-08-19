from __future__ import annotations

import hashlib
import html
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticGeneratedPublicV1,
)
from synthworld.agentic.enterprise.generated_serialization import (
    generated_enterprise_agentic_artifact_checksums,
    load_generated_enterprise_agentic_public_tree,
    load_generated_enterprise_agentic_trees,
)
from synthworld.agentic.serialization import (
    load_agentic_benchmark,
    load_public_agentic_bundle,
)
from synthworld.explorer.asteria import (
    project_asteria_agent_authority_evaluator_v1,
    project_asteria_agent_authority_v1,
)
from synthworld.explorer.enterprise_generated import (
    compute_generated_enterprise_agentic_layout,
    is_supported_generated_projection,
    project_generated_enterprise_agentic_evaluator_v1,
    project_generated_enterprise_agentic_v1,
)
from synthworld.explorer.models import (
    ExplorerEnterpriseGeneratedLayoutV1,
    ExplorerEnterpriseGeneratedProjectionV1,
    ExplorerEvaluatorOverlayV1,
    ExplorerLayoutManifestV2,
    ExplorerPublicProjectionV1,
)
from synthworld.explorer.serialization import canonical_json_bytes
from synthworld.explorer.validation import (
    validate_evaluator_overlay,
    validate_generated_layout,
    validate_layout_manifest,
)

PUBLISHED_ASTERIA_PUBLIC_ARTIFACT_SET_DIGEST = (
    "9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594"
)
_ASSET_NAMES = {
    "asteria-agent-authority-v1.layout.json",
    "explorer.bundle.js",
    "explorer.css",
    "THIRD_PARTY_NOTICES.txt",
}


class ExplorerRenderError(ValueError):
    """An Explorer package, asset, or render binding is invalid."""


def _asset_bytes() -> tuple[dict[str, bytes], dict[str, Any]]:
    asset_root = files("synthworld.explorer").joinpath("assets")
    try:
        manifest_bytes = asset_root.joinpath("manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExplorerRenderError("Explorer asset manifest is unavailable") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0.0":
        raise ExplorerRenderError("Explorer asset manifest is invalid")
    descriptors = manifest.get("artifacts")
    if not isinstance(descriptors, dict) or set(descriptors) != _ASSET_NAMES:
        raise ExplorerRenderError("Explorer asset manifest inventory differs")
    loaded: dict[str, bytes] = {}
    for name in sorted(_ASSET_NAMES):
        descriptor = descriptors[name]
        try:
            payload = asset_root.joinpath(name).read_bytes()
        except OSError as error:
            raise ExplorerRenderError(
                f"Explorer asset is unavailable: {name}"
            ) from error
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("byte_size") != len(payload)
            or descriptor.get("sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise ExplorerRenderError(f"Explorer asset binding differs: {name}")
        loaded[name] = payload
    return loaded, manifest


def load_asteria_agent_authority_layout() -> ExplorerLayoutManifestV2:
    """Load and verify the pinned ELK layout for published Asteria v1."""

    assets, _ = _asset_bytes()
    payload = assets["asteria-agent-authority-v1.layout.json"]
    try:
        layout = ExplorerLayoutManifestV2.model_validate_json(payload)
    except ValueError as error:
        raise ExplorerRenderError("Explorer layout asset is invalid") from error
    if canonical_json_bytes(layout) != payload:
        raise ExplorerRenderError("Explorer layout asset is not canonical JSON")
    return layout


def _safe_json(
    artifact: (
        ExplorerPublicProjectionV1
        | ExplorerEnterpriseGeneratedProjectionV1
        | ExplorerEvaluatorOverlayV1
        | ExplorerLayoutManifestV2
        | ExplorerEnterpriseGeneratedLayoutV1
    ),
) -> str:
    serialized = canonical_json_bytes(artifact).decode("utf-8").strip()
    return serialized.replace("<", "\\u003c")


def _render_html(
    projection: ExplorerPublicProjectionV1 | ExplorerEnterpriseGeneratedProjectionV1,
    layout: ExplorerLayoutManifestV2 | ExplorerEnterpriseGeneratedLayoutV1,
    overlay: ExplorerEvaluatorOverlayV1 | None,
    *,
    title: str,
    heading: str,
    graph_label: str,
    status: str,
    coordinate_note: str,
) -> bytes:
    assets, asset_manifest = _asset_bytes()
    css = assets["explorer.css"].decode("utf-8")
    script = assets["explorer.bundle.js"].decode("utf-8")
    if "</style" in css.lower() or "</script" in script.lower():
        raise ExplorerRenderError("Explorer bundle cannot be embedded safely")
    notices = html.escape(assets["THIRD_PARTY_NOTICES.txt"].decode("utf-8"))
    evaluator = overlay is not None
    watermark = (
        f'<div class="watermark">{html.escape(overlay.watermark)}</div>'
        if overlay is not None
        else ""
    )
    overlay_data = (
        '<script id="synthworld-evaluator-overlay" type="application/json">'
        f"{_safe_json(overlay)}</script>"
        if overlay is not None
        else ""
    )
    dependencies = ", ".join(
        f"{item['name']} {item['version']}" for item in asset_manifest["dependencies"]
    )
    visibility_label = "evaluator overlay" if evaluator else "public projection"
    visibility = "evaluator" if evaluator else "public"
    footer_label = (
        "evaluator truth explicitly enabled" if evaluator else "public projection only"
    )
    event_count = len(projection.timeline)
    csp = (
        "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline'; connect-src 'none'; font-src 'none'"
    )
    rendered = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta
  name="synthworld-public-projection-sha256"
  content="{layout.public_projection_digest}">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<main class="shell">
{watermark}
<header class="masthead">
  <section>
    <div class="eyebrow">SynthWorld Explorer / {visibility_label}</div>
    <h1>{heading}</h1>
    <div class="facts">
      <span><strong>{len(projection.nodes)}</strong> nodes</span>
      <span><strong>{len(projection.edges)}</strong> relations</span>
      <span><strong>{event_count}</strong> events</span>
      <span><strong>{visibility}</strong> visibility</span>
    </div>
  </section>
  <aside class="status">
    {status}
  </aside>
</header>
<section class="workspace">
  <div class="graph-wrap">
    <div class="graph-controls">
      <button id="synthworld-fit" type="button">fit</button>
      <button id="synthworld-reset" type="button">latest event</button>
    </div>
    <div
      id="synthworld-graph"
      role="img"
      aria-label="{graph_label}"></div>
  </div>
  <aside class="inspector">
    <div class="eyebrow">Inspect the chain</div>
    <h2 id="synthworld-inspector-title">Select a node</h2>
    <div id="synthworld-inspector-kind" class="kind">public structure</div>
    <dl id="synthworld-inspector-properties"></dl>
    <section id="synthworld-inspector-truth" class="truth"></section>
  </aside>
</section>
<section class="timeline">
  <div class="timeline-head">
    <h2>Authority replay</h2>
    <div id="synthworld-timeline-label" class="timeline-label"></div>
  </div>
  <input
    id="synthworld-timeline-slider"
    type="range"
    min="0"
    value="{event_count}"
    step="1"
    aria-label="Authority event tick">
  <div id="synthworld-event-buttons" class="event-buttons"></div>
</section>
<footer>
  <span>{footer_label}</span>
  <span>{coordinate_note}</span>
</footer>
<details>
  <summary>Third-party notices ({html.escape(dependencies)})</summary>
  <pre class="notices">{notices}</pre>
</details>
</main>
<script id="synthworld-projection" type="application/json">
{_safe_json(projection)}</script>
<script id="synthworld-layout" type="application/json">{_safe_json(layout)}</script>
{overlay_data}
<script>{script}</script>
</body>
</html>
"""
    return rendered.encode("utf-8")


def render_explorer_html(
    projection: ExplorerPublicProjectionV1,
    *,
    overlay: ExplorerEvaluatorOverlayV1 | None = None,
) -> bytes:
    """Render deterministic, self-contained Explorer HTML from verified contracts."""

    if (
        projection.profile != "agent-authority-v1"
        or projection.source.public_artifact_set_digest
        != PUBLISHED_ASTERIA_PUBLIC_ARTIFACT_SET_DIGEST
    ):
        raise ExplorerRenderError(
            "Explorer v0.1 renders only the published Asteria Agentic v1 package"
        )
    layout = load_asteria_agent_authority_layout()
    try:
        validate_layout_manifest(projection, layout)
        if overlay is not None:
            validate_evaluator_overlay(projection, overlay)
    except ValueError as error:
        raise ExplorerRenderError(str(error)) from error
    return _render_html(
        projection,
        layout,
        overlay,
        title="Asteria agent authority - SynthWorld Explorer",
        heading="Asteria <em>authority map</em>",
        graph_label="Interactive graph of Asteria agent authority",
        status="published world<br>agent authority v1<br>deterministic preset",
        coordinate_note="stable UUID5 identities / pinned ELK coordinates",
    )


def render_generated_enterprise_agentic_html(
    projection: ExplorerEnterpriseGeneratedProjectionV1,
    *,
    overlay: ExplorerEvaluatorOverlayV1 | None = None,
) -> bytes:
    """Render one generated enterprise-agentic projection with the shared shell."""

    if not is_supported_generated_projection(projection):
        raise ExplorerRenderError(
            "Explorer renders only the released generated enterprise-agentic "
            "smoke profile"
        )
    layout = compute_generated_enterprise_agentic_layout(projection)
    try:
        validate_generated_layout(projection, layout)
        if overlay is not None:
            validate_evaluator_overlay(projection, overlay)
    except ValueError as error:
        raise ExplorerRenderError(str(error)) from error
    return _render_html(
        projection,
        layout,
        overlay,
        title="Generated enterprise agent authority - SynthWorld Explorer",
        heading="Generated enterprise <em>authority map</em>",
        graph_label="Interactive graph of generated enterprise agent authority",
        status=(
            "generated world<br>enterprise-agentic-generated v1<br>deterministic preset"
        ),
        coordinate_note="stable UUID5 identities / deterministic grid coordinates",
    )


def render_asteria_agent_authority_package(
    *,
    public_package: Path,
    evaluator_package: Path | None = None,
) -> bytes:
    """Verify package directories and render the supported Asteria view."""

    try:
        public_manifest = json.loads(
            (public_package / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExplorerRenderError("Asteria public manifest is unavailable") from error
    if not isinstance(public_manifest, dict):
        raise ExplorerRenderError("Asteria public manifest is invalid")
    public_digest = public_manifest.get("artifact_set_digest")
    if public_digest != PUBLISHED_ASTERIA_PUBLIC_ARTIFACT_SET_DIGEST:
        raise ExplorerRenderError(
            "public package is not the published Asteria Agentic v1 artifact set"
        )

    if evaluator_package is None:
        public = load_public_agentic_bundle(public_package)
        evaluator = None
        evaluator_digest = None
    else:
        try:
            checksums = json.loads(
                (evaluator_package / "checksums.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExplorerRenderError(
                "Asteria evaluator checksums are unavailable"
            ) from error
        if not isinstance(checksums, dict):
            raise ExplorerRenderError("Asteria evaluator checksums are invalid")
        evaluator_digest = checksums.get("evaluator_artifact_set_digest")
        if not isinstance(evaluator_digest, str):
            raise ExplorerRenderError("Asteria evaluator digest is unavailable")
        benchmark = load_agentic_benchmark(
            public_root=public_package,
            evaluator_root=evaluator_package,
        )
        public = benchmark.public
        evaluator = benchmark.evaluator

    projection = project_asteria_agent_authority_v1(
        public,
        public_artifact_set_digest=public_digest,
    )
    overlay = (
        project_asteria_agent_authority_evaluator_v1(
            projection,
            evaluator,
            evaluator_artifact_set_digest=evaluator_digest,
        )
        if evaluator is not None and evaluator_digest is not None
        else None
    )
    return render_explorer_html(projection, overlay=overlay)


def render_generated_enterprise_agentic_package(
    *,
    public_package: Path,
    evaluator_package: Path | None = None,
) -> bytes:
    """Verify generated package trees and render the supported generated view."""

    if evaluator_package is None:
        public = load_generated_enterprise_agentic_public_tree(public_package)
        projection = project_generated_enterprise_agentic_v1(public)
        return render_generated_enterprise_agentic_html(projection)
    generated = load_generated_enterprise_agentic_trees(
        public_tree=public_package,
        evaluator_tree=evaluator_package,
    )
    public = EnterpriseAgenticGeneratedPublicV1(
        config=generated.config,
        identity=generated.identity,
        benchmark=generated.public,
    )
    projection = project_generated_enterprise_agentic_v1(public)
    checksums = dict(generated_enterprise_agentic_artifact_checksums(generated))
    overlay = project_generated_enterprise_agentic_evaluator_v1(
        projection,
        generated.evaluator,
        evaluator_artifact_set_digest=checksums["evaluator"],
    )
    return render_generated_enterprise_agentic_html(projection, overlay=overlay)


def write_asteria_agent_authority_html(
    output: Path,
    *,
    public_package: Path,
    evaluator_package: Path | None = None,
) -> None:
    """Write one new self-contained HTML file without overwriting existing data."""

    payload = render_asteria_agent_authority_package(
        public_package=public_package,
        evaluator_package=evaluator_package,
    )
    with output.open("xb") as destination:
        destination.write(payload)


def write_generated_enterprise_agentic_html(
    output: Path,
    *,
    public_package: Path,
    evaluator_package: Path | None = None,
) -> None:
    """Write one new self-contained HTML file without overwriting existing data."""

    payload = render_generated_enterprise_agentic_package(
        public_package=public_package,
        evaluator_package=evaluator_package,
    )
    with output.open("xb") as destination:
        destination.write(payload)
