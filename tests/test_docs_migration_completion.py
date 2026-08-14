"""Regression checks for the documentation ownership boundary."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
README = ROOT / "README.md"
USER_GUIDE = ROOT / "USER_GUIDE.md"
DOCS_HOME = ROOT / "docs/index.md"
ROADMAP_VIEW = ROOT / "docs/roadmap/index.md"
MIGRATION_INDEX = ROOT / "docs/migration-index.md"

CANONICAL_GUIDES = (
    ROOT / "docs/guides/evaluating-a-system.md",
    ROOT / "docs/guides/identity-worlds.md",
    ROOT / "docs/guides/identity-resolution.md",
    ROOT / "docs/guides/privacy-exposure.md",
    ROOT / "docs/guides/enterprise-access.md",
    ROOT / "docs/guides/enterprise-identity-planning.md",
)


def test_readme_is_a_front_door_not_the_detailed_manual() -> None:
    text = README.read_text(encoding="utf-8")

    assert "https://bluntmachetti.github.io/synthworld/" in text
    assert "## Choose what you want to do" in text
    assert "## Current benchmark families" in text
    assert "## Enterprise identity and access" in text
    assert "https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/" in text
    assert "during migration" not in text.lower()


def test_user_guide_is_a_compatibility_index() -> None:
    text = USER_GUIDE.read_text(encoding="utf-8")

    assert "compatibility index" in text.lower()
    assert "## Use case 1: safe connected identity fixtures" in text
    assert "## Use case 13: enterprise authorization benchmarks" in text
    assert "### Generation cost" in text
    assert "remains the detailed compatibility source" not in text


def test_canonical_guides_do_not_route_back_to_legacy_guide() -> None:
    for path in CANONICAL_GUIDES:
        text = path.read_text(encoding="utf-8")
        assert "USER_GUIDE.md" not in text, path


def test_site_state_no_longer_describes_prerequisites_as_pending() -> None:
    home = DOCS_HOME.read_text(encoding="utf-8")
    roadmap = ROADMAP_VIEW.read_text(encoding="utf-8")

    assert "being integrated by the prerequisite governance work" not in home
    assert "renderer and dark-preview infrastructure only after" not in roadmap
    assert "generated registry catalogue" in home.lower()


def test_migration_tracker_is_now_an_ownership_record() -> None:
    text = MIGRATION_INDEX.read_text(encoding="utf-8")

    assert text.startswith("# Documentation ownership record")
    assert "guide remains intact until" not in text
    assert "compatibility exception" in text.lower()


def test_canonical_docs_describe_the_legacy_guide_as_an_index() -> None:
    getting_started = (ROOT / "docs/getting-started.md").read_text(encoding="utf-8")
    cli_reference = (ROOT / "docs/reference/cli.md").read_text(encoding="utf-8")
    contribution_guide = (
        ROOT / "docs/support/contributing-documentation.md"
    ).read_text(encoding="utf-8")

    assert "compatibility index" in getting_started.lower()
    assert "compatibility index" in cli_reference.lower()
    assert "canonical owner" in contribution_guide.lower()
    assert "while detailed guidance moves" not in getting_started
    assert "detailed user guide" not in cli_reference.lower()
