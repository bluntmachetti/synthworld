"""Fail-closed checks for the generated Blume documentation distribution."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_AUDITOR = Path(__file__).resolve().parents[1] / "tools" / "audit_docs_dist.mjs"


def _find_node() -> str:
    executable = shutil.which("node")
    if executable is None:
        raise RuntimeError("node is required for documentation distribution tests")
    return executable


_NODE = _find_node()


def _write_minimal_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "changelog" / "CHANGELOG").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<link rel="stylesheet" href="/synthworld/assets/site.css">\n',
        encoding="utf-8",
    )
    (dist / "blume-search.json").write_text("[]\n", encoding="utf-8")
    (dist / "changelog" / "CHANGELOG" / "index.html").write_text(
        '<a href="/synthworld/">SynthWorld</a>\n',
        encoding="utf-8",
    )
    (dist / "assets").mkdir()
    (dist / "assets" / "site.css").write_text(
        "body { background: #fff; }\n",
        encoding="utf-8",
    )
    return dist


def _audit(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed Node executable and repository script
        [_NODE, str(_AUDITOR)],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )


def test_minimal_clean_dist_passes(tmp_path: Path) -> None:
    _write_minimal_dist(tmp_path)

    result = _audit(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "docs output audit passed" in result.stdout


def test_symlink_is_rejected(tmp_path: Path) -> None:
    dist = _write_minimal_dist(tmp_path)
    os.symlink(dist / "index.html", dist / "linked-index.html")

    result = _audit(tmp_path)

    assert result.returncode != 0
    assert "unsupported symbolic link" in result.stderr


def test_source_map_is_rejected(tmp_path: Path) -> None:
    dist = _write_minimal_dist(tmp_path)
    (dist / "assets" / "site.js.map").write_text("{}\n", encoding="utf-8")

    result = _audit(tmp_path)

    assert result.returncode != 0
    assert "source map emitted" in result.stderr


@pytest.mark.parametrize("name", ("opaque.bin", "opaque"))
def test_unknown_or_extensionless_binary_is_rejected(tmp_path: Path, name: str) -> None:
    dist = _write_minimal_dist(tmp_path)
    (dist / "assets" / name).write_bytes(b"\x00\xff\x00\xff")

    result = _audit(tmp_path)

    assert result.returncode != 0
    assert "unsupported file type" in result.stderr
