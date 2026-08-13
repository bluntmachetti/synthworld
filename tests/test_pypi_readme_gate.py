"""Regression checks for PyPI long-description validation."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"

RENDERER_PIN = "readme-renderer[md]==45.0"
SOURCE_BINDING = "built long description differs from README.md"
RELEASE_SOURCE_BINDING = "unexpected project.readme configuration"
RENDER_FAILURE = "README.md failed Warehouse Markdown rendering"


def test_pull_requests_validate_the_built_pypi_long_description() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "name: PyPI long description" in workflow
    assert "uv build --clear" in workflow
    assert RENDERER_PIN in workflow
    assert SOURCE_BINDING in workflow
    assert RENDER_FAILURE in workflow


def test_release_refuses_an_invalid_pypi_long_description() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert RENDERER_PIN in workflow
    assert RELEASE_SOURCE_BINDING in workflow
    assert RENDER_FAILURE in workflow
    assert workflow.index(RENDERER_PIN) < workflow.index("Run full gates")
    assert workflow.index(RENDERER_PIN) < workflow.index("Upload distribution")
    assert workflow.index(RENDERER_PIN) < workflow.index("Publish to PyPI")
