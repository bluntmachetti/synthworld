"""Regression checks for staged Blume page-title normalization."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_NORMALIZER = (
    Path(__file__).resolve().parents[1] / "tools" / "normalize_blume_headings.mjs"
)


def _node() -> str:
    executable = shutil.which("node")
    if executable is None:
        raise RuntimeError("node is required for Blume heading normalization tests")
    return executable


def _normalize(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed Node executable and repository script
        [_node(), str(_NORMALIZER), str(root)],
        capture_output=True,
        check=False,
        text=True,
    )


def test_leading_h1_is_promoted_to_frontmatter_title(tmp_path: Path) -> None:
    page = tmp_path / "getting-started.md"
    page.write_text("# Getting Started\n\nInstall the package.\n", encoding="utf-8")

    result = _normalize(tmp_path)

    assert result.returncode == 0, result.stderr
    assert page.read_text(encoding="utf-8") == (
        '---\ntitle: "Getting Started"\n---\n\nInstall the package.\n'
    )


def test_matching_frontmatter_title_removes_body_h1(tmp_path: Path) -> None:
    page = tmp_path / "benchmarks.md"
    page.write_text(
        "---\ntitle: Benchmarks\ndescription: Published benchmark families.\n---\n\n"
        "# Benchmarks\n\nChoose a benchmark.\n",
        encoding="utf-8",
    )

    result = _normalize(tmp_path)

    assert result.returncode == 0, result.stderr
    content = page.read_text(encoding="utf-8")
    assert "title: Benchmarks" in content
    assert "# Benchmarks" not in content
    assert content.endswith("Choose a benchmark.\n")


def test_mismatched_frontmatter_title_is_left_for_render_audit(tmp_path: Path) -> None:
    page = tmp_path / "intentional.md"
    original = "---\ntitle: Page title\n---\n\n# Different heading\n"
    page.write_text(original, encoding="utf-8")

    result = _normalize(tmp_path)

    assert result.returncode == 0, result.stderr
    assert page.read_text(encoding="utf-8") == original
