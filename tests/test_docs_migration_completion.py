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
)


def test_readme_is_a_front_door_not_the_detailed_manual() -> None:
    text = README.read_text(encoding="utf-8")

    assert "https://bluntmachetti.github.io/synthworld/" in text
    assert "## Choose your goal" in text
    assert "## Current benchmark families" not in text
    assert "## Enterprise identity and access" not in text
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
