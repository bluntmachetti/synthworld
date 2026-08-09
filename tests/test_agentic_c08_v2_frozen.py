from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from synthworld.agentic.c08_v2 import (
    C08_FROZEN_BENCHMARK_PATH,
    C08_FROZEN_EVALUATOR_MANIFEST,
    C08_FROZEN_EVALUATOR_PAYLOAD,
    C08_FROZEN_MANIFEST,
    C08_FROZEN_PUBLIC_MANIFEST,
    C08_FROZEN_PUBLIC_PAYLOAD,
    C08FrozenArtifactError,
    c08_frozen_artifact_set_digest,
    freeze_c08_v2_benchmark,
    load_c08_v2_frozen_tree,
    load_packaged_c08_v2_benchmark,
)
from synthworld.enterprise.canonical import canonical_json_value_bytes

REPOSITORY_ROOT = Path(__file__).parents[1]
FROZEN_TREE = REPOSITORY_ROOT / C08_FROZEN_BENCHMARK_PATH
EXPECTED_FILES = {
    C08_FROZEN_MANIFEST,
    C08_FROZEN_PUBLIC_PAYLOAD,
    C08_FROZEN_PUBLIC_MANIFEST,
    C08_FROZEN_EVALUATOR_PAYLOAD,
    C08_FROZEN_EVALUATOR_MANIFEST,
}


def _copy_tree(tmp_path: Path) -> Path:
    destination = tmp_path / "frozen"
    shutil.copytree(FROZEN_TREE, destination, symlinks=True)
    return destination


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _refresh_evaluator_and_root_manifests(root: Path) -> None:
    evaluator_payload_path = root / C08_FROZEN_EVALUATOR_PAYLOAD
    evaluator_payload = evaluator_payload_path.read_bytes()
    evaluator_manifest_path = root / C08_FROZEN_EVALUATOR_MANIFEST
    evaluator_manifest = json.loads(evaluator_manifest_path.read_bytes())
    evaluator_manifest["artifacts"]["c08-asteria-evaluator.json"] = {
        "byte_size": len(evaluator_payload),
        "sha256": hashlib.sha256(evaluator_payload).hexdigest(),
    }
    evaluator_manifest["artifact_set_digest"] = c08_frozen_artifact_set_digest(
        {"c08-asteria-evaluator.json": evaluator_payload}
    )
    evaluator_manifest_path.write_bytes(canonical_json_value_bytes(evaluator_manifest))
    root_manifest_path = root / C08_FROZEN_MANIFEST
    root_manifest = json.loads(root_manifest_path.read_bytes())
    files = {
        relative: (root / relative).read_bytes()
        for relative in EXPECTED_FILES
        if relative != C08_FROZEN_MANIFEST
    }
    for relative, payload in files.items():
        root_manifest["artifacts"][relative] = {
            "byte_size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    root_manifest["artifact_set_digest"] = c08_frozen_artifact_set_digest(files)
    root_manifest_path.write_bytes(canonical_json_value_bytes(root_manifest))


def test_filesystem_and_packaged_loads_have_exact_verified_inventory() -> None:
    filesystem = load_c08_v2_frozen_tree(FROZEN_TREE)
    packaged = load_packaged_c08_v2_benchmark()
    assert filesystem == packaged
    assert set(_tree_bytes(FROZEN_TREE)) == EXPECTED_FILES
    assert filesystem.public_input_digest == hashlib.sha256(
        (FROZEN_TREE / C08_FROZEN_PUBLIC_PAYLOAD).read_bytes()
    ).hexdigest()


def test_regeneration_is_byte_for_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_bundle = freeze_c08_v2_benchmark(first)
    second_bundle = freeze_c08_v2_benchmark(second)
    assert first_bundle == second_bundle
    assert _tree_bytes(first) == _tree_bytes(second)
    assert _tree_bytes(first) == _tree_bytes(FROZEN_TREE)


def test_frozen_format_and_public_tree_have_no_evaluator_leakage() -> None:
    for path in FROZEN_TREE.rglob("*"):
        if path.is_file():
            payload = path.read_bytes()
            assert payload.endswith(b"\n")
            assert not payload.endswith(b"\n\n")
            assert payload.decode("utf-8")
            json.loads(payload)
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (FROZEN_TREE / "public").rglob("*")
        if path.is_file()
    )
    for marker in (
        "required_observation_ids",
        "scenario_kind",
        "public_input_digest",
        "evaluator",
    ):
        assert marker not in public_text
    assert not any(
        "submission" in path.name or "report" in path.name
        for path in FROZEN_TREE.rglob("*")
    )


def test_root_digest_excludes_only_root_manifest() -> None:
    files = {
        path.relative_to(FROZEN_TREE).as_posix(): path.read_bytes()
        for path in FROZEN_TREE.rglob("*")
        if path.is_file()
    }
    manifest = json.loads((FROZEN_TREE / C08_FROZEN_MANIFEST).read_bytes())
    assert manifest["artifact_set_digest"] == c08_frozen_artifact_set_digest(
        files, excluded_paths=(C08_FROZEN_MANIFEST,)
    )


def test_v1_checksums_are_preserved() -> None:
    checksums = json.loads(
        (
            REPOSITORY_ROOT
            / "src/synthworld/benchmarks/asteria-agentic-v1/evaluator/checksums.json"
        ).read_bytes()
    )
    assert checksums["public_artifact_set_digest"] == (
        "9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594"
    )
    assert checksums["evaluator_artifact_set_digest"] == (
        "3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f"
    )


@pytest.mark.parametrize(
    "relative",
    (
        C08_FROZEN_MANIFEST,
        C08_FROZEN_PUBLIC_PAYLOAD,
        C08_FROZEN_PUBLIC_MANIFEST,
        C08_FROZEN_EVALUATOR_PAYLOAD,
        C08_FROZEN_EVALUATOR_MANIFEST,
    ),
)
def test_missing_file_is_rejected(tmp_path: Path, relative: str) -> None:
    root = _copy_tree(tmp_path)
    (root / relative).unlink()
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)


@pytest.mark.parametrize("relative", ("", "public", "evaluator"))
def test_extra_file_is_rejected(tmp_path: Path, relative: str) -> None:
    root = _copy_tree(tmp_path)
    (root / relative / "extra.json" if relative else root / "extra.json").write_bytes(b"{}\n")
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)


def test_directory_where_file_is_expected_is_rejected(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    payload = root / C08_FROZEN_PUBLIC_PAYLOAD
    payload.unlink()
    payload.mkdir()
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)


def test_symlinked_directory_and_file_are_rejected(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    public = root / "public"
    real_public = tmp_path / "public-real"
    public.rename(real_public)
    os.symlink(real_public, public, target_is_directory=True)
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)

    root = _copy_tree(tmp_path / "file")
    payload = root / C08_FROZEN_PUBLIC_PAYLOAD
    target = tmp_path / "target.json"
    target.write_bytes(payload.read_bytes())
    payload.unlink()
    os.symlink(target, payload)
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)


def test_noncanonical_json_and_digest_mismatch_are_rejected(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    payload = root / C08_FROZEN_PUBLIC_PAYLOAD
    payload.write_bytes(json.dumps(json.loads(payload.read_bytes()), indent=2).encode())
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)

    root = _copy_tree(tmp_path / "digest")
    payload = root / C08_FROZEN_PUBLIC_PAYLOAD
    document = json.loads(payload.read_bytes())
    document["actions"][0]["action_id"] = "tampered-action"
    payload.write_bytes(canonical_json_value_bytes(document))
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)


def test_evaluator_public_digest_cross_binding_is_rejected(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    evaluator = json.loads((root / C08_FROZEN_EVALUATOR_PAYLOAD).read_bytes())
    evaluator["public_input_digest"] = "0" * 64
    (root / C08_FROZEN_EVALUATOR_PAYLOAD).write_bytes(canonical_json_value_bytes(evaluator))
    _refresh_evaluator_and_root_manifests(root)
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)
