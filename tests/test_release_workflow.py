"""Regression tests for release artifact provenance."""

import runpy
from pathlib import Path
from typing import Any, cast

import pytest
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


def test_release_documentation_gate_rejects_candidate_and_stale_instructions(
    tmp_path: Path,
) -> None:
    validate = runpy.run_path(str(ROOT / ".github/scripts/validate_release_ready.py"))[
        "validate_release_ready"
    ]
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.18.0"\n')
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [0.18.0] - Unreleased\n")
    with pytest.raises(ValueError, match="date the"):
        validate(tmp_path)
    dated = "## [0.18.0] - 2026-10-02\n"
    changelog.write_text(dated)
    with pytest.raises(ValueError, match="changelog links"):
        validate(tmp_path)
    links = (
        "[0.18.0]: https://github.com/bluntmachetti/synthworld/compare/v0.17.0...v0.18.0\n"
        "[Unreleased]: https://github.com/bluntmachetti/synthworld/compare/v0.18.0...HEAD\n"
    )
    changelog.write_text(dated + links)
    quickstart = tmp_path / "docs/guides/agent-authorisation-quickstart.md"
    quickstart.parent.mkdir(parents=True)
    ready = (
        "pip install idcognito-synthworld==0.18.0\nsynthworld-demo run --output demo\n"
    )
    quickstart.write_text(ready)
    readme = tmp_path / "README.md"
    readme.write_text("unreleased candidate")
    with pytest.raises(ValueError, match="candidate instructions"):
        validate(tmp_path)
    readme.write_text(ready.replace("0.18.0", "0.17.0"))
    with pytest.raises(ValueError, match="stale package pins"):
        validate(tmp_path)
    readme.write_text("pip install idcognito-synthworld")
    with pytest.raises(ValueError, match="installed demo"):
        validate(tmp_path)
    readme.write_text(ready)
    other_docs = (
        "docs/index.md",
        "docs/getting-started.md",
        "docs/guides/identity-worlds.md",
        "examples/enterprise_agentic_identity_pilot/README.md",
    )
    for name in other_docs:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Installation guide")
    validate(tmp_path)
    for name in other_docs:
        path = tmp_path / name
        path.write_text("source preview until publication")
        with pytest.raises(ValueError, match="candidate instructions"):
            validate(tmp_path)
        path.write_text("Installation guide")
    quickstart.write_text("not yet published")
    with pytest.raises(ValueError, match="candidate instructions"):
        validate(tmp_path)
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["build"]["steps"]
    gate = next(
        i
        for i, step in enumerate(steps)
        if "validate_release_ready.py" in step.get("run", "")
    )
    upload = next(
        i for i, step in enumerate(steps) if step.get("uses") == UPLOAD_ARTIFACT_V7
    )
    assert gate < upload
