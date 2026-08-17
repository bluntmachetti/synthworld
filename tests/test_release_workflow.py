"""Regression tests for release artifact provenance."""

from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[1]
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"
UPLOAD_ARTIFACT_V7 = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


def test_release_uploads_the_distribution_verified_by_make_ci() -> None:
    workflow = cast(
        "dict[str, Any]",
        yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8")),
    )
    steps = cast("list[dict[str, Any]]", workflow["jobs"]["build"]["steps"])
    verification_index = next(
        index for index, step in enumerate(steps) if step.get("run") == "make ci"
    )
    upload_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == UPLOAD_ARTIFACT_V7
    )

    assert verification_index < upload_index
    assert upload_index == verification_index + 1
    intervening_source = "\n".join(
        str(step.get("run", ""))
        for step in steps[verification_index + 1 : upload_index]
    )
    assert "uv build" not in intervening_source
    assert "--clear" not in intervening_source
    assert steps[upload_index]["with"] == {"name": "dist", "path": "dist/"}


def test_release_is_complete_before_immutable_publication() -> None:
    workflow = cast(
        "dict[str, Any]",
        yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8")),
    )
    steps = cast("list[dict[str, Any]]", workflow["jobs"]["announce"]["steps"])
    create_index = next(
        index
        for index, step in enumerate(steps)
        if "gh release create" in str(step.get("run", ""))
    )
    publish_index = next(
        index
        for index, step in enumerate(steps)
        if "gh release edit" in str(step.get("run", ""))
    )
    create_source = str(steps[create_index]["run"])
    publish_source = str(steps[publish_index]["run"])

    assert "--draft" in create_source
    assert "dist/*" in create_source
    assert publish_index == create_index + 1
    assert "--draft=false" in publish_source
