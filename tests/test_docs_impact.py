"""Regression checks for documentation workflow impact detection."""

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_catalogue_renderer_changes_trigger_docs_checks() -> None:
    workflow = (ROOT / ".github/workflows/docs-impact.yml").read_text(encoding="utf-8")
    assert "tools/generate_registry_catalogue.mjs" in workflow
