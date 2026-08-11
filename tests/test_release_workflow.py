"""Regression tests for release artifact provenance."""

from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[1]
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"


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
        if step.get("uses") == "actions/upload-artifact@v7"
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
