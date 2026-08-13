"""Regression checks for PyPI long-description validation."""

from pathlib import Path
import tomllib

import pytest

from tools.validate_pypi_readme import resolve_readme_source

ROOT = Path(__file__).parents[1]
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"
RELEASE_VALIDATOR = ROOT / "tools/validate_pypi_readme.py"
PYPROJECT = ROOT / "pyproject.toml"

RENDERER_PIN = "readme-renderer[md]==45.0"
SOURCE_BINDING = "built long description differs from README.md"
RELEASE_SOURCE_BINDING = "unexpected project.readme configuration"
RENDER_FAILURE = "failed Warehouse Markdown rendering"


def test_pull_requests_validate_the_built_pypi_long_description() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "name: PyPI long description" in workflow
    assert "uv build --clear" in workflow
    assert RENDERER_PIN in workflow
    assert SOURCE_BINDING in workflow
    assert RENDER_FAILURE in workflow


def test_release_refuses_an_invalid_pypi_long_description() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    validator = RELEASE_VALIDATOR.read_text(encoding="utf-8")

    assert RENDERER_PIN in workflow
    assert "python tools/validate_pypi_readme.py" in workflow
    assert RELEASE_SOURCE_BINDING in validator
    assert RENDER_FAILURE in validator
    assert workflow.index(RENDERER_PIN) < workflow.index("Run full gates")
    assert workflow.index(RENDERER_PIN) < workflow.index("Upload distribution")
    assert workflow.index(RENDERER_PIN) < workflow.index("Publish to PyPI")


def test_release_validator_accepts_repository_readme_configuration() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]

    assert project["readme"] == "README.md"
    assert resolve_readme_source(project["readme"]) == Path("README.md")


def test_release_validator_accepts_explicit_table_configuration() -> None:
    assert resolve_readme_source(
        {"file": "README.md", "content-type": "text/markdown"}
    ) == Path("README.md")


def test_release_validator_rejects_noncanonical_readme_source() -> None:
    with pytest.raises(ValueError, match="unexpected project.readme configuration"):
        resolve_readme_source("docs/README.md")
