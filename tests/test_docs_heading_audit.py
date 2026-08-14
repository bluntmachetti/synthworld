"""Fail-closed checks for rendered documentation heading structure."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_AUDITOR = Path(__file__).resolve().parents[1] / "tools" / "audit_docs_headings.mjs"


def _node() -> str:
    executable = shutil.which("node")
    if executable is None:
        raise RuntimeError("node is required for documentation heading audit tests")
    return executable


def _audit(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed Node executable and repository script
        [_node(), str(_AUDITOR), str(root)],
        capture_output=True,
        check=False,
        text=True,
    )


def test_single_h1_passes(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<main><h1>Getting Started</h1><h2>Install</h2></main>\n",
        encoding="utf-8",
    )

    result = _audit(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "docs heading audit passed" in result.stdout


def test_multiple_h1_elements_fail(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<main><h1>Getting Started</h1><h1>Getting Started</h1></main>\n",
        encoding="utf-8",
    )

    result = _audit(tmp_path)

    assert result.returncode != 0
    assert "2 H1 elements found in index.html" in result.stderr
