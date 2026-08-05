"""Frozen authority-governance benchmark transition and integrity gates."""

from __future__ import annotations

import hashlib
import shutil
from importlib.resources import files
from pathlib import Path
from typing import cast

import pytest

from synthworld.authority_governance import (
    EVALUATOR_AUTHORITY_GOVERNANCE_PATH,
    GOLDEN_AUTHORITY_GOVERNANCE_DIRECTORY,
    PUBLIC_AUTHORITY_GOVERNANCE_PATH,
    AuthorityGovernanceArtifactError,
    export_authority_governance_benchmark,
    load_golden_authority_governance_benchmark,
    reference_authority_governance,
)

_FROZEN_DIGESTS = {
    EVALUATOR_AUTHORITY_GOVERNANCE_PATH: (
        "7822846e7d5613741857cceed33df849f04606548a4c0e1ce789646aaae8e5e5"
    ),
    "evaluator/manifest.json": (
        "d9b5e3c19a74344ba9b28bfb58efde98ce8809e4157e8c0fa6b97639a7a36e18"
    ),
    PUBLIC_AUTHORITY_GOVERNANCE_PATH: (
        "340df0ed2b33db6c05805891258dda789f445e300084a0e347ee318044d3191b"
    ),
    "public/manifest.json": (
        "60081ed11ff85b6909e57771f3aeffb8023136ae8b66e91bbaf4473ef7f27d92"
    ),
}
_CHECKSUM_MANIFEST_DIGEST = (
    "a856171b2a328614705340a0d8d8dcf1f6bc0794adf0853c377718f796eb585c"
)


def test_frozen_governance_tree_matches_reviewed_generation_byte_for_byte(
    tmp_path: Path,
) -> None:
    root = _packaged_root()
    frozen = load_golden_authority_governance_benchmark()
    reference = reference_authority_governance()
    assert frozen == reference

    regenerated = tmp_path / "regenerated"
    export_authority_governance_benchmark(
        regenerated,
        public=reference.public,
        evaluator=reference.evaluator,
    )
    for relative_path, expected_digest in _FROZEN_DIGESTS.items():
        frozen_bytes = root.joinpath(*relative_path.split("/")).read_bytes()
        assert regenerated.joinpath(*relative_path.split("/")).read_bytes() == (
            frozen_bytes
        )
        assert hashlib.sha256(frozen_bytes).hexdigest() == expected_digest

    checksum_bytes = (root / "SHA256SUMS").read_bytes()
    assert hashlib.sha256(checksum_bytes).hexdigest() == _CHECKSUM_MANIFEST_DIGEST
    assert checksum_bytes == b"".join(
        f"{digest}  {path}\n".encode("ascii")
        for path, digest in _FROZEN_DIGESTS.items()
    )


def test_golden_loader_rejects_missing_non_directory_and_extra_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synthworld.authority_governance import serialization

    monkeypatch.setattr(serialization, "files", lambda _package: tmp_path)
    with pytest.raises(AuthorityGovernanceArtifactError, match="root is unreadable"):
        serialization.load_golden_authority_governance_benchmark()

    root = tmp_path / GOLDEN_AUTHORITY_GOVERNANCE_DIRECTORY
    root.write_bytes(b"not a directory")
    with pytest.raises(AuthorityGovernanceArtifactError, match="not a real directory"):
        serialization.load_golden_authority_governance_benchmark()

    root.unlink()
    _copy_packaged_tree(root)
    (root / "unexpected.txt").write_bytes(b"unexpected\n")
    with pytest.raises(AuthorityGovernanceArtifactError, match="inventory differs"):
        serialization.load_golden_authority_governance_benchmark()


@pytest.mark.parametrize("entry_name", ("public", "evaluator", "SHA256SUMS"))
def test_golden_loader_rejects_invalid_root_entry_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry_name: str,
) -> None:
    from synthworld.authority_governance import serialization

    root = tmp_path / GOLDEN_AUTHORITY_GOVERNANCE_DIRECTORY
    _copy_packaged_tree(root)
    entry = root / entry_name
    if entry.is_dir():
        shutil.rmtree(entry)
        entry.write_bytes(b"not a directory")
    else:
        entry.unlink()
        entry.mkdir()
    monkeypatch.setattr(serialization, "files", lambda _package: tmp_path)
    with pytest.raises(AuthorityGovernanceArtifactError, match="non-regular entry"):
        serialization.load_golden_authority_governance_benchmark()


@pytest.mark.parametrize(
    "manifest",
    (
        b"\xff\n",
        b"0" * 64 + b"  evaluator/authority-governance-evaluator.json",
        b"not-a-checksum-row\n",
        (
            b"0" * 64
            + b"  evaluator/manifest.json\n"
            + b"0" * 64
            + b"  evaluator/authority-governance-evaluator.json\n"
            + b"0" * 64
            + b"  public/authority-governance-input.json\n"
            + b"0" * 64
            + b"  public/manifest.json\n"
        ),
        (
            b"A" * 64
            + b"  evaluator/authority-governance-evaluator.json\n"
            + b"0" * 64
            + b"  evaluator/manifest.json\n"
            + b"0" * 64
            + b"  public/authority-governance-input.json\n"
            + b"0" * 64
            + b"  public/manifest.json\n"
        ),
    ),
)
def test_golden_loader_rejects_invalid_checksum_manifests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest: bytes,
) -> None:
    from synthworld.authority_governance import serialization

    root = tmp_path / GOLDEN_AUTHORITY_GOVERNANCE_DIRECTORY
    _copy_packaged_tree(root)
    (root / "SHA256SUMS").write_bytes(manifest)
    monkeypatch.setattr(serialization, "files", lambda _package: tmp_path)
    with pytest.raises(
        AuthorityGovernanceArtifactError,
        match=r"manifest is (?:invalid|not canonical)",
    ):
        serialization.load_golden_authority_governance_benchmark()


def test_golden_loader_rejects_nonregular_unreadable_and_changed_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synthworld.authority_governance import serialization

    monkeypatch.setattr(serialization, "files", lambda _package: tmp_path)
    root = tmp_path / GOLDEN_AUTHORITY_GOVERNANCE_DIRECTORY
    _copy_packaged_tree(root)
    public_artifact = root / PUBLIC_AUTHORITY_GOVERNANCE_PATH
    public_artifact.unlink()
    public_artifact.mkdir()
    with pytest.raises(AuthorityGovernanceArtifactError, match="not a regular file"):
        serialization.load_golden_authority_governance_benchmark()

    shutil.rmtree(root)
    _copy_packaged_tree(root)
    public_artifact = root / PUBLIC_AUTHORITY_GOVERNANCE_PATH
    public_artifact.write_bytes(public_artifact.read_bytes() + b"\n")
    with pytest.raises(AuthorityGovernanceArtifactError, match="checksum differs"):
        serialization.load_golden_authority_governance_benchmark()

    shutil.rmtree(root)
    _copy_packaged_tree(root)
    original_read_bytes = Path.read_bytes

    def unreadable_artifact(path: Path) -> bytes:
        if path.name == "authority-governance-input.json":
            raise OSError("injected read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", unreadable_artifact)
    with pytest.raises(
        AuthorityGovernanceArtifactError, match="artifact is unreadable"
    ):
        serialization.load_golden_authority_governance_benchmark()


def _packaged_root() -> Path:
    return cast(
        Path,
        files("synthworld.benchmarks").joinpath(GOLDEN_AUTHORITY_GOVERNANCE_DIRECTORY),
    )


def _copy_packaged_tree(destination: Path) -> None:
    shutil.copytree(_packaged_root(), destination)
