from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.agentic.c08_v2 import (
    C08_FROZEN_BENCHMARK_PATH,
    C08_FROZEN_EVALUATOR_MANIFEST,
    C08_FROZEN_EVALUATOR_PAYLOAD,
    C08_FROZEN_MANIFEST,
    C08_FROZEN_PUBLIC_MANIFEST,
    C08_FROZEN_PUBLIC_PAYLOAD,
    C08FrozenArtifactError,
    C08FrozenEvaluatorManifestV2,
    C08FrozenPublicManifestV2,
    C08FrozenRootManifestV2,
    c08_frozen_artifact_set_digest,
    freeze_c08_v2_benchmark,
    load_c08_v2_frozen_tree,
    load_packaged_c08_v2_benchmark,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
)

REPOSITORY_ROOT = Path(__file__).parents[1]
FROZEN_TREE = REPOSITORY_ROOT / C08_FROZEN_BENCHMARK_PATH
EXPECTED_FILES = {
    C08_FROZEN_MANIFEST,
    C08_FROZEN_PUBLIC_PAYLOAD,
    C08_FROZEN_PUBLIC_MANIFEST,
    C08_FROZEN_EVALUATOR_PAYLOAD,
    C08_FROZEN_EVALUATOR_MANIFEST,
}
V1_PUBLIC_FILES = (
    "organisation.json",
    "principals.jsonl",
    "agents.jsonl",
    "runtimes.jsonl",
    "resources.jsonl",
    "public_credentials.jsonl",
    "public_delegations.jsonl",
    "public_events.jsonl",
    "tool_schemas/procurement-tools.json",
    "scenarios/procurement-delegation.json",
)
V1_EVALUATOR_FILES = (
    "canonical_bindings.json",
    "authority_truth.jsonl",
    "cases.jsonl",
    "expected_decisions.jsonl",
    "expected_side_effects.jsonl",
    "expected_provenance.jsonl",
    "evidence_epochs.jsonl",
)
V1_PUBLIC_ROOT_DIGEST = (
    "9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594"
)
V1_EVALUATOR_ROOT_DIGEST = (
    "3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f"
)
V1_PUBLIC_MANIFEST = {
    "artifact_set_digest": V1_PUBLIC_ROOT_DIGEST,
    "artifacts": {
        "agents.jsonl": (
            "3e4884bdcde3ec9e2fbdc958c5fcc587c54e733273afeb4df00e64fac4e20279"
        ),
        "organisation.json": (
            "bc29c6aa8e342e72c76e9ae58ca5e101beeb2e69f7956bf878890f714af29c08"
        ),
        "principals.jsonl": (
            "58163ce487ec8a0e986cac5380706ecac352819a1706d265518fbb515955874c"
        ),
        "public_credentials.jsonl": (
            "59e116652a078eb46b5e3ea1946d3b78a00b3945d2809a4af25c8875a5f42a93"
        ),
        "public_delegations.jsonl": (
            "476df49d66e774c0303370739e9e5bc8011e66985652d14664c581535c743957"
        ),
        "public_events.jsonl": (
            "ab920f3866aaa86deeadbbe4c5882170205c12d8d2c1a0fa638c0415aa0ec6eb"
        ),
        "resources.jsonl": (
            "866a24fdf59e2bbd957717af9c0402a629b341046205d953724a15bddef19266"
        ),
        "runtimes.jsonl": (
            "d1d08d2b060e6b900029bc180a266e41cc3e4da7938fd27fb8c2577f27298704"
        ),
        "scenarios/procurement-delegation.json": (
            "37f09e82146a249cc5a7f02ad3ec5abf95724d2eaf4dbc40da3b969f9ea88ec9"
        ),
        "tool_schemas/procurement-tools.json": (
            "11d22e49cb95b52d294d832d5df145e86c492fd16c3781f21c5e664b4ef6c6c8"
        ),
    },
    "oracle_free": True,
    "schema_version": "1.0.0",
    "seed": 20260719,
    "world_id": "asteria-agentic",
    "world_version": "1.0.0",
}
V1_EVALUATOR_CHECKSUMS = {
    "checksum_scheme": "sha256-artifact-set-v1",
    "evaluator_artifact_set_digest": V1_EVALUATOR_ROOT_DIGEST,
    "evaluator_artifacts": {
        "authority_truth.jsonl": (
            "093efedf08d1db33e04335bd846a50b58bb8222bb2395dca8358d8e2820536b0"
        ),
        "canonical_bindings.json": (
            "9ed29aa54a1c05d9ae2b62797059a85fb96c6710b762568465f98222fc844cdf"
        ),
        "cases.jsonl": (
            "a44d28143128da2051c665e8ae421e1b2d3af0cb2e364d42af099f0ecc8b35a5"
        ),
        "evidence_epochs.jsonl": (
            "e685ee9b0334eb5c2ae5905e930d6302160e525634eb92f0c4334a8a5c9d15a8"
        ),
        "expected_decisions.jsonl": (
            "49e68d770b3a68666d193d1304d0eaebc67eb689c66ff4697ba59db6be41be49"
        ),
        "expected_provenance.jsonl": (
            "05fedec838d2569ebc4ebbe7d9af8ab5757faf6bcfe1858ecae9d06423553fa1"
        ),
        "expected_side_effects.jsonl": (
            "d5b4aeac96bface4331622c6eba307fad8b2cc5044fcdc2cfef8622c3ff61079"
        ),
    },
    "public_artifact_set_digest": V1_PUBLIC_ROOT_DIGEST,
    "schema_version": "1.0.0",
}
V1_TREE_FILES = frozenset(
    {f"public/{path}" for path in (*V1_PUBLIC_FILES, "manifest.json")}
    | {f"evaluator/{path}" for path in (*V1_EVALUATOR_FILES, "checksums.json")}
)


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


def _recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(_recursive_keys(item))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_recursive_keys(item))
        return keys
    return set()


def _v1_metadata_bytes(document: Mapping[str, object]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _refresh_evaluator_and_root_manifests(root: Path) -> None:
    evaluator_payload_path = root / C08_FROZEN_EVALUATOR_PAYLOAD
    evaluator_payload = evaluator_payload_path.read_bytes()
    evaluator_manifest_path = root / C08_FROZEN_EVALUATOR_MANIFEST
    evaluator_manifest = json.loads(evaluator_manifest_path.read_bytes())
    evaluator_descriptor = evaluator_manifest["artifacts"][0]
    evaluator_descriptor["byte_size"] = len(evaluator_payload)
    evaluator_descriptor["sha256"] = hashlib.sha256(evaluator_payload).hexdigest()
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
        descriptor = next(
            item for item in root_manifest["artifacts"] if item["path"] == relative
        )
        descriptor["byte_size"] = len(payload)
        descriptor["sha256"] = hashlib.sha256(payload).hexdigest()
    root_manifest["artifact_set_digest"] = c08_frozen_artifact_set_digest(files)
    root_manifest_path.write_bytes(canonical_json_value_bytes(root_manifest))


def test_filesystem_and_packaged_loads_have_exact_verified_inventory() -> None:
    filesystem = load_c08_v2_frozen_tree(FROZEN_TREE)
    packaged = load_packaged_c08_v2_benchmark()
    assert filesystem == packaged
    assert set(_tree_bytes(FROZEN_TREE)) == EXPECTED_FILES
    assert (
        filesystem.public_input_digest
        == hashlib.sha256(
            (FROZEN_TREE / C08_FROZEN_PUBLIC_PAYLOAD).read_bytes()
        ).hexdigest()
    )


def test_regeneration_is_byte_for_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_bundle = freeze_c08_v2_benchmark(first)
    second_bundle = freeze_c08_v2_benchmark(second)
    assert first_bundle == second_bundle
    assert _tree_bytes(first) == _tree_bytes(second)
    assert _tree_bytes(first) == _tree_bytes(FROZEN_TREE)
    with pytest.raises(C08FrozenArtifactError, match="overwrite"):
        freeze_c08_v2_benchmark(first)
    assert freeze_c08_v2_benchmark(first, replace=True) == first_bundle


def test_frozen_format_and_public_tree_have_no_evaluator_leakage() -> None:
    for path in FROZEN_TREE.rglob("*"):
        if path.is_file():
            payload = path.read_bytes()
            assert payload.endswith(b"\n")
            assert not payload.endswith(b"\n\n")
            assert payload.decode("utf-8")
            json.loads(payload)
    public_keys: set[str] = set()
    for path in (FROZEN_TREE / "public").rglob("*"):
        if path.is_file():
            public_keys.update(_recursive_keys(json.loads(path.read_bytes())))
    assert {
        "availability",
        "bindings",
        "evaluator",
        "evaluator_public_input_digest",
        "expected_verdict",
        "outcome",
        "public_input_digest",
        "required_observation_ids",
        "scenario_kind",
    }.isdisjoint(public_keys)
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
    manifest = C08FrozenRootManifestV2.model_validate_json(
        (FROZEN_TREE / C08_FROZEN_MANIFEST).read_bytes()
    )
    assert manifest.artifact_set_digest == c08_frozen_artifact_set_digest(
        files, excluded_paths=(C08_FROZEN_MANIFEST,)
    )


def test_frozen_manifests_use_governed_immutable_models() -> None:
    public_payload = (FROZEN_TREE / C08_FROZEN_PUBLIC_MANIFEST).read_bytes()
    evaluator_payload = (FROZEN_TREE / C08_FROZEN_EVALUATOR_MANIFEST).read_bytes()
    root_payload = (FROZEN_TREE / C08_FROZEN_MANIFEST).read_bytes()
    public = C08FrozenPublicManifestV2.model_validate_json(public_payload)
    evaluator = C08FrozenEvaluatorManifestV2.model_validate_json(evaluator_payload)
    root = C08FrozenRootManifestV2.model_validate_json(root_payload)
    assert canonical_json_bytes(public) == public_payload
    assert canonical_json_bytes(evaluator) == evaluator_payload
    assert canonical_json_bytes(root) == root_payload
    with pytest.raises(ValidationError, match="frozen"):
        public.visibility = "public"


def test_v1_complete_source_tree_bytes_are_preserved() -> None:
    root = REPOSITORY_ROOT / "src/synthworld/benchmarks/asteria-agentic-v1"
    tree = _tree_bytes(root)
    assert set(tree) == V1_TREE_FILES
    public_payloads = {path: tree[f"public/{path}"] for path in V1_PUBLIC_FILES}
    evaluator_payloads = {
        path: tree[f"evaluator/{path}"] for path in V1_EVALUATOR_FILES
    }
    assert c08_frozen_artifact_set_digest(public_payloads) == V1_PUBLIC_ROOT_DIGEST
    assert (
        c08_frozen_artifact_set_digest(evaluator_payloads) == V1_EVALUATOR_ROOT_DIGEST
    )
    assert V1_PUBLIC_MANIFEST["artifacts"] == {
        path: hashlib.sha256(payload).hexdigest()
        for path, payload in public_payloads.items()
    }
    assert V1_EVALUATOR_CHECKSUMS["evaluator_artifacts"] == {
        path: hashlib.sha256(payload).hexdigest()
        for path, payload in evaluator_payloads.items()
    }
    public_manifest = tree["public/manifest.json"]
    evaluator_checksums = tree["evaluator/checksums.json"]
    assert json.loads(public_manifest) == V1_PUBLIC_MANIFEST
    assert json.loads(evaluator_checksums) == V1_EVALUATOR_CHECKSUMS
    assert public_manifest == _v1_metadata_bytes(V1_PUBLIC_MANIFEST)
    assert evaluator_checksums == _v1_metadata_bytes(V1_EVALUATOR_CHECKSUMS)


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
    extra = root / relative / "extra.json" if relative else root / "extra.json"
    extra.write_bytes(b"{}\n")
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
    document["actions"][0]["action_event_id"] = "tampered-action"
    payload.write_bytes(canonical_json_value_bytes(document))
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)


def test_evaluator_public_digest_cross_binding_is_rejected(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    evaluator = json.loads((root / C08_FROZEN_EVALUATOR_PAYLOAD).read_bytes())
    evaluator["public_input_digest"] = "0" * 64
    (root / C08_FROZEN_EVALUATOR_PAYLOAD).write_bytes(
        canonical_json_value_bytes(evaluator)
    )
    _refresh_evaluator_and_root_manifests(root)
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)


@pytest.mark.parametrize(
    ("relative", "field"),
    (
        (C08_FROZEN_PUBLIC_MANIFEST, "visibility"),
        (C08_FROZEN_EVALUATOR_MANIFEST, "seed"),
        (C08_FROZEN_MANIFEST, "artifacts"),
    ),
)
def test_typed_manifest_contracts_reject_wrong_shapes(
    tmp_path: Path, relative: str, field: str
) -> None:
    root = _copy_tree(tmp_path)
    path = root / relative
    document = json.loads(path.read_bytes())
    if field == "visibility":
        document[field] = "evaluator"
    elif field == "seed":
        document[field] = 1
    else:
        document[field] = document[field][:-1]
    path.write_bytes(canonical_json_value_bytes(document))
    with pytest.raises(C08FrozenArtifactError):
        load_c08_v2_frozen_tree(root)
