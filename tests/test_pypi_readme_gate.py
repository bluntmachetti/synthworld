"""Regression checks for PyPI long-description validation."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"


def test_pull_requests_validate_the_built_pypi_long_description() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "name: PyPI long description" in workflow
    assert "uv build --clear" in workflow
    assert "uvx --from twine==6.2.0 twine check --strict dist/*" in workflow


def test_release_refuses_an_invalid_pypi_long_description() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    check = "uvx --from twine==6.2.0 twine check --strict dist/*"
    assert check in workflow
    assert workflow.index(check) < workflow.index("Upload distribution")
    assert workflow.index(check) < workflow.index("Publish to PyPI")
