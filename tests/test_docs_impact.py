"""Regression checks for documentation workflow impact detection."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
DEPLOY_WORKFLOW = ROOT / ".github/workflows/docs-deploy.yml"
IMPACT_WORKFLOW = ROOT / ".github/workflows/docs-impact.yml"


def test_catalogue_renderer_changes_trigger_docs_checks() -> None:
    workflow = IMPACT_WORKFLOW.read_text(encoding="utf-8")
    assert "tools/generate_registry_catalogue.mjs" in workflow


def test_heading_tool_changes_trigger_docs_checks_and_deploy() -> None:
    impact = IMPACT_WORKFLOW.read_text(encoding="utf-8")
    deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    for tool in (
        "tools/normalize_blume_headings.mjs",
        "tools/audit_docs_headings.mjs",
    ):
        assert tool in impact
        assert tool in deploy


def test_deployment_workflow_changes_trigger_docs_checks() -> None:
    workflow = IMPACT_WORKFLOW.read_text(encoding="utf-8")
    assert ".github/workflows/docs-deploy.yml" in workflow


def test_docs_deployment_has_audited_main_only_pages_contract() -> None:
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "branches: [main]" in workflow
    assert "pull_request:" not in workflow
    assert "contents: read" in workflow
    assert "pages: write" in workflow
    assert "id-token: write" in workflow
    assert "npm run docs:check" in workflow
    assert "environment:" in workflow
    assert "name: github-pages" in workflow
    assert "cancel-in-progress: false" in workflow

    pinned_actions = (
        "actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d",
        "actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9",
        "actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128",
    )
    for action in pinned_actions:
        assert action in workflow
