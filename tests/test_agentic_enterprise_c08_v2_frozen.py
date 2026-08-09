"""Adversarial coverage for the frozen enterprise C08 v2 benchmark tree."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

import synthworld.agentic.enterprise.c08_v2.frozen as frozen_module
from synthworld.agentic.enterprise.c08_v2 import (
    C08CaseOutcomeV2,
    C08FrozenArtifactV2,
    C08FrozenManifestV2,
    C08ReferenceBundleV2,
    C08SubmissionV2,
    evaluate_c08,
    generate_c08_reference,
    reference_submission_from_public,
)
from synthworld.agentic.enterprise.c08_v2.frozen import (
    FrozenC08BenchmarkError,
    frozen_files,
    load_frozen_benchmark,
    load_packaged_frozen_benchmark,
    write_frozen_benchmark,
)
from synthworld.agentic.enterprise.c08_v2.projection import (
    c08_public_input_digest,
)
from synthworld.agentic.enterprise.c08_v2.serialization import (
    serialize_c08_evaluator,
    serialize_c08_public,
)

_EXPECTED_FILES = {
    "manifest.json",
    "SHA256SUMS",
    "public/public-input.json",
    "evaluator/truth.json",
}
_PACKAGED_ROOT = Path("src/synthworld/benchmarks/enterprise-agentic-c08-v2")
_V1_DIGESTS = {
    "examples/enterprise-agentic-evaluator.json": (
        "9fbf331d8a037e444d3b756007ce1ab2426b3cd39ab46461cb1343bbccbfb723"
    ),
    "examples/enterprise-agentic-metrics.json": (
        "983f5abb9ee17b91dbfec39fd029c8ebce3ed1de738f500a32dc01f4b61864c7"
    ),
    "examples/enterprise-agentic-prediction.json": (
        "c8af6e28c4d7e47f86969cff9a669081414414c498abc9ae1cd46ccb5252a2bd"
    ),
    "examples/enterprise-agentic-public-input.json": (
        "ca581923b57927c9595a6e3f44e783bcdc02bd329f6bd9b79eee11ea034f28a3"
    ),
    "schemas/enterprise-agentic-benchmark.schema.json": (
        "7ca6c5fa4de53ff527b535871663606750c2dce1ddb143e1971cbaad89531f10"
    ),
    "schemas/enterprise-agentic-evaluator.schema.json": (
        "b1d5ee7109c4cf0e151c30ec414976bc7fbd210607bdf2bd50ae07e930c6dbfc"
    ),
    "schemas/enterprise-agentic-metrics.schema.json": (
        "979d31dc1c55e1dd034eb2840e06c3730558e17872d14fd798f520c7f6948862"
    ),
    "schemas/enterprise-agentic-prediction.schema.json": (
        "f3cd117cd476176e79a2fb5264e04fb7f671815a335db6f6976578c4890bccb6"
    ),
    "schemas/enterprise-agentic-public-input.schema.json": (
        "97418f7200ffdbc9665562e0560ce55cdf3ab65f3ee4baa4843a114f8aae9b1b"
    ),
    "schemas/enterprise-agentic-truth.schema.json": (
        "5a3352b538fcac485e3d9d0449760586201207cb91897d113371e2ff4b377a1a"
    ),
}


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _copy_frozen(root: Path, destination: Path) -> None:
    shutil.copytree(root, destination)


def _rewrite_checksum(root: Path, path: str, payload: bytes) -> None:
    checksum_path = root / "SHA256SUMS"
    rows = checksum_path.read_text(encoding="ascii").splitlines()
    checksum_path.write_text(
        "\n".join(
            (
                f"{hashlib.sha256(payload).hexdigest()}  {row.split('  ', 1)[1]}"
                if row.endswith(path)
                else row
            )
            for row in rows
        )
        + "\n",
        encoding="ascii",
    )


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _rewrite_manifest(root: Path, manifest: dict[str, Any]) -> bytes:
    payload = _canonical_json_bytes(manifest)
    (root / "manifest.json").write_bytes(payload)
    _rewrite_checksum(root, "manifest.json", payload)
    return payload


def _replace_bound_artifact(root: Path, relative: str, payload: bytes) -> None:
    (root / relative).write_bytes(payload)
    _rewrite_checksum(root, relative, payload)
    manifest = json.loads((root / "manifest.json").read_bytes())
    inventory_name = (
        "public_inventory" if relative.startswith("public/") else "evaluator_inventory"
    )
    artifact = next(
        item for item in manifest[inventory_name] if item["path"] == relative
    )
    artifact["byte_size"] = len(payload)
    artifact["sha256"] = hashlib.sha256(payload).hexdigest()
    _rewrite_manifest(root, manifest)


def _write_self_consistent_alternate(root: Path) -> None:
    alternate = generate_c08_reference(20260810)
    payloads = frozen_files()
    payloads["public/public-input.json"] = serialize_c08_public(alternate.public)
    payloads["evaluator/truth.json"] = serialize_c08_evaluator(alternate.evaluator)
    manifest = json.loads(payloads["manifest.json"])
    manifest["public_input_digest"] = c08_public_input_digest(alternate.public)
    for inventory_name in ("public_inventory", "evaluator_inventory"):
        for artifact in manifest[inventory_name]:
            payload = payloads[artifact["path"]]
            artifact["byte_size"] = len(payload)
            artifact["sha256"] = hashlib.sha256(payload).hexdigest()
    payloads["manifest.json"] = _canonical_json_bytes(manifest)
    payloads["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(payloads[path]).hexdigest()}  {path}\n"
        for path in sorted(payloads)
        if path != "SHA256SUMS"
    ).encode("ascii")
    for path, payload in payloads.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)


def test_frozen_tree_has_fixed_seed_exact_inventory_and_canonical_bytes() -> None:
    tree = load_packaged_frozen_benchmark()
    assert tree.manifest.benchmark_id == "enterprise-agentic-c08-v2"
    assert tree.manifest.seed == 20260809
    assert tree.manifest.checksum_excludes == ("SHA256SUMS",)
    assert set(_files(_PACKAGED_ROOT)) == _EXPECTED_FILES
    for path, payload in _files(_PACKAGED_ROOT).items():
        assert payload.endswith(b"\n"), path
        assert not payload.endswith(b"\n\n"), path
        assert b"\r" not in payload, path
    checksum_payload = (_PACKAGED_ROOT / "SHA256SUMS").read_bytes()
    assert b"SHA256SUMS" not in checksum_payload
    assert b"submission" not in checksum_payload
    assert b"report" not in checksum_payload
    assert tree.evaluator.public_input_digest == tree.manifest.public_input_digest


def test_frozen_generation_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_frozen_benchmark(first)
    write_frozen_benchmark(second)
    assert _files(first) == _files(second) == frozen_files()


def test_frozen_generation_rejects_internal_digest_disagreement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        frozen_module,
        "c08_public_input_digest",
        lambda _public: "0" * 64,
    )
    with pytest.raises(FrozenC08BenchmarkError, match="generated evaluator/public"):
        frozen_module.frozen_files()


def test_frozen_writer_covers_existing_root_and_replacement_guards(
    tmp_path: Path,
) -> None:
    file_root = tmp_path / "file-root"
    file_root.write_bytes(b"not a directory")
    with pytest.raises(FrozenC08BenchmarkError, match="not a directory"):
        write_frozen_benchmark(file_root)

    symlink_root = tmp_path / "symlink-root"
    symlink_root.symlink_to(file_root)
    with pytest.raises(FrozenC08BenchmarkError, match="not a directory"):
        write_frozen_benchmark(symlink_root)

    empty_root = tmp_path / "empty-root"
    empty_root.mkdir()
    write_frozen_benchmark(empty_root)
    assert set(_files(empty_root)) == _EXPECTED_FILES

    nonempty_root = tmp_path / "nonempty-root"
    nonempty_root.mkdir()
    (nonempty_root / "extra").write_bytes(b"extra")
    with pytest.raises(FrozenC08BenchmarkError, match="not empty"):
        write_frozen_benchmark(nonempty_root)
    with pytest.raises(FrozenC08BenchmarkError, match="exact frozen inventory"):
        write_frozen_benchmark(nonempty_root, replace=True)

    wrong_type = tmp_path / "wrong-type"
    _copy_frozen(_PACKAGED_ROOT, wrong_type)
    (wrong_type / "public/public-input.json").unlink()
    (wrong_type / "public/public-input.json").mkdir()
    with pytest.raises(FrozenC08BenchmarkError, match="exact frozen inventory"):
        write_frozen_benchmark(wrong_type, replace=True)

    replaceable = tmp_path / "replaceable"
    _copy_frozen(_PACKAGED_ROOT, replaceable)
    write_frozen_benchmark(replaceable, replace=True)
    assert _files(replaceable) == frozen_files()


def test_frozen_tree_walk_rejects_root_node_and_read_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_root = tmp_path / "load-file"
    file_root.write_bytes(b"not a directory")
    with pytest.raises(FrozenC08BenchmarkError, match="not a directory"):
        load_frozen_benchmark(file_root)

    symlink_root = tmp_path / "load-symlink"
    symlink_root.symlink_to(_PACKAGED_ROOT.resolve(), target_is_directory=True)
    with pytest.raises(FrozenC08BenchmarkError, match="not a directory"):
        load_frozen_benchmark(symlink_root)

    non_regular = tmp_path / "non-regular"
    _copy_frozen(_PACKAGED_ROOT, non_regular)
    os.mkfifo(non_regular / "fifo")
    with pytest.raises(FrozenC08BenchmarkError, match="non-regular node"):
        load_frozen_benchmark(non_regular)

    unreadable = tmp_path / "unreadable"
    _copy_frozen(_PACKAGED_ROOT, unreadable)
    original_read_bytes = Path.read_bytes

    def fail_truth(path: Path) -> bytes:
        if path.name == "truth.json":
            raise OSError("synthetic read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_truth)
    with pytest.raises(FrozenC08BenchmarkError, match="artifact is unreadable"):
        load_frozen_benchmark(unreadable)


def test_frozen_loader_rejects_manifest_and_checksum_encodings(
    tmp_path: Path,
) -> None:
    invalid_manifest = tmp_path / "invalid-manifest"
    _copy_frozen(_PACKAGED_ROOT, invalid_manifest)
    (invalid_manifest / "manifest.json").write_bytes(b"{}\n")
    with pytest.raises(FrozenC08BenchmarkError, match="manifest is invalid"):
        load_frozen_benchmark(invalid_manifest)

    noncanonical_manifest = tmp_path / "noncanonical-manifest"
    _copy_frozen(_PACKAGED_ROOT, noncanonical_manifest)
    manifest_path = noncanonical_manifest / "manifest.json"
    manifest_path.write_bytes(
        json.dumps(json.loads(manifest_path.read_bytes()), indent=2).encode("utf-8")
        + b"\n"
    )
    with pytest.raises(FrozenC08BenchmarkError, match="manifest is not canonical"):
        load_frozen_benchmark(noncanonical_manifest)

    missing_newline = tmp_path / "checksum-newline"
    _copy_frozen(_PACKAGED_ROOT, missing_newline)
    checksum_path = missing_newline / "SHA256SUMS"
    checksum_path.write_bytes(checksum_path.read_bytes().rstrip(b"\n"))
    with pytest.raises(FrozenC08BenchmarkError, match="SHA256SUMS is not canonical"):
        load_frozen_benchmark(missing_newline)

    carriage_return = tmp_path / "checksum-carriage-return"
    _copy_frozen(_PACKAGED_ROOT, carriage_return)
    checksum_path = carriage_return / "SHA256SUMS"
    checksum_path.write_bytes(checksum_path.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(FrozenC08BenchmarkError, match="SHA256SUMS is not canonical"):
        load_frozen_benchmark(carriage_return)

    non_ascii = tmp_path / "checksum-non-ascii"
    _copy_frozen(_PACKAGED_ROOT, non_ascii)
    checksum_path = non_ascii / "SHA256SUMS"
    checksum_payload = checksum_path.read_bytes()
    checksum_path.write_bytes(b"\xff" + checksum_payload[1:])
    with pytest.raises(FrozenC08BenchmarkError, match="SHA256SUMS is not ASCII"):
        load_frozen_benchmark(non_ascii)

    invalid_row = tmp_path / "checksum-invalid-row"
    _copy_frozen(_PACKAGED_ROOT, invalid_row)
    (invalid_row / "SHA256SUMS").write_bytes(b"invalid row\n")
    with pytest.raises(FrozenC08BenchmarkError, match="invalid row"):
        load_frozen_benchmark(invalid_row)

    wrong_inventory = tmp_path / "checksum-inventory"
    _copy_frozen(_PACKAGED_ROOT, wrong_inventory)
    checksum_path = wrong_inventory / "SHA256SUMS"
    checksum_path.write_bytes(
        b"\n".join(checksum_path.read_bytes().splitlines()[1:]) + b"\n"
    )
    with pytest.raises(FrozenC08BenchmarkError, match="inventory differs"):
        load_frozen_benchmark(wrong_inventory)


def test_frozen_loader_rejects_typed_digest_and_semantic_mismatches(
    tmp_path: Path,
) -> None:
    invalid_public = tmp_path / "invalid-public"
    _copy_frozen(_PACKAGED_ROOT, invalid_public)
    invalid_payload = b"{}\n"
    (invalid_public / "public/public-input.json").write_bytes(invalid_payload)
    _rewrite_checksum(invalid_public, "public/public-input.json", invalid_payload)
    with pytest.raises(FrozenC08BenchmarkError, match="payload is invalid"):
        load_frozen_benchmark(invalid_public)

    public_digest = tmp_path / "public-digest"
    _copy_frozen(_PACKAGED_ROOT, public_digest)
    public_data = json.loads((public_digest / "public/public-input.json").read_bytes())
    action_id = public_data["actions"][0]["action_id"]
    public_data["actions"][0]["resource_id"] = "resource-modified"
    for event in public_data["evidence_events"]:
        if event["action_id"] == action_id:
            event["resource_id"] = "resource-modified"
    _replace_bound_artifact(
        public_digest,
        "public/public-input.json",
        _canonical_json_bytes(public_data),
    )
    with pytest.raises(FrozenC08BenchmarkError, match="manifest/public digest"):
        load_frozen_benchmark(public_digest)

    evaluator_digest = tmp_path / "evaluator-digest"
    _copy_frozen(_PACKAGED_ROOT, evaluator_digest)
    evaluator_data = json.loads(
        (evaluator_digest / "evaluator/truth.json").read_bytes()
    )
    evaluator_data["public_input_digest"] = "0" * 64
    _replace_bound_artifact(
        evaluator_digest,
        "evaluator/truth.json",
        _canonical_json_bytes(evaluator_data),
    )
    with pytest.raises(FrozenC08BenchmarkError, match="evaluator/public digest"):
        load_frozen_benchmark(evaluator_digest)

    evaluator_semantics = tmp_path / "evaluator-semantics"
    _copy_frozen(_PACKAGED_ROOT, evaluator_semantics)
    evaluator_data = json.loads(
        (evaluator_semantics / "evaluator/truth.json").read_bytes()
    )
    evaluator_data["bindings"][0]["tenant_id"] = "tenant-modified"
    _replace_bound_artifact(
        evaluator_semantics,
        "evaluator/truth.json",
        _canonical_json_bytes(evaluator_data),
    )
    with pytest.raises(FrozenC08BenchmarkError, match="semantics differ"):
        load_frozen_benchmark(evaluator_semantics)


@pytest.mark.parametrize(
    ("inventory_name", "expected"),
    (
        ("public_inventory", "manifest public inventory differs"),
        ("evaluator_inventory", "manifest evaluator inventory differs"),
    ),
)
def test_frozen_loader_rejects_manifest_inventory_bindings(
    tmp_path: Path,
    inventory_name: str,
    expected: str,
) -> None:
    root = tmp_path / inventory_name
    _copy_frozen(_PACKAGED_ROOT, root)
    manifest = json.loads((root / "manifest.json").read_bytes())
    manifest[inventory_name][0]["sha256"] = "0" * 64
    _rewrite_manifest(root, manifest)
    with pytest.raises(FrozenC08BenchmarkError, match=expected):
        load_frozen_benchmark(root)


@pytest.mark.parametrize("changed_model", ("public", "evaluator"))
def test_frozen_loader_rejects_canonical_model_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_model: str,
) -> None:
    root = tmp_path / changed_model
    _copy_frozen(_PACKAGED_ROOT, root)
    canonical = generate_c08_reference(20260809)
    public = canonical.public
    evaluator = canonical.evaluator
    if changed_model == "public":
        public = public.model_copy(update={"actions": tuple(reversed(public.actions))})
    else:
        evaluator = evaluator.model_copy(update={"public_input_digest": "0" * 64})
    changed = C08ReferenceBundleV2(
        seed=canonical.seed,
        source=canonical.source,
        public=public,
        evaluator=evaluator,
        reference_submission=canonical.reference_submission,
    )
    generated = iter((canonical, changed))

    def next_bundle(_seed: int) -> C08ReferenceBundleV2:
        return next(generated)

    monkeypatch.setattr(frozen_module, "generate_c08_reference", next_bundle)
    with pytest.raises(FrozenC08BenchmarkError, match="models differ"):
        load_frozen_benchmark(root)


def test_public_tree_has_no_evaluator_fields_or_case_truth() -> None:
    public_bytes = b"".join(
        payload
        for path, payload in _files(_PACKAGED_ROOT).items()
        if path.startswith("public/")
    )
    assert b"required_evidence_ids" not in public_bytes
    assert b"required_observation_ids" not in public_bytes
    assert b"C08CaseOutcomeV2" not in public_bytes
    assert b'"outcome"' not in public_bytes
    assert b"evaluator/truth.json" not in public_bytes
    assert b"submission" not in public_bytes
    assert json.loads(public_bytes.decode("utf-8"))["schema_version"] == "2.0.0"


def test_frozen_evaluation_rejects_cross_tenant_and_wrong_action() -> None:
    tree = load_packaged_frozen_benchmark()
    reference = reference_submission_from_public(tree.public)
    first = reference.observations[0]
    cross_tenant = reference.model_copy(
        update={
            "observations": (
                first.model_copy(update={"tenant_id": "tenant-cross"}),
                *reference.observations[1:],
            )
        }
    )
    report = evaluate_c08(
        public=tree.public,
        evaluator=tree.evaluator,
        submission=cross_tenant,
    )
    assert (
        next(
            item.outcome
            for item in report.outcomes
            if item.action_id == first.action_id
        )
        is C08CaseOutcomeV2.WRONG_ACTION
    )
    report_payload = json.dumps(report.model_dump(mode="json"))
    assert "offline scoring does not prove live evidence retention" in report_payload
    assert "offline scoring does not prove durable logging" in report_payload
    assert "offline scoring does not prove enforcement behavior" in report_payload

    foreign_evidence = next(
        event
        for event in tree.public.evidence_events
        if event.action_id != first.action_id
    )
    wrong_action_payload = reference.model_dump(mode="json")
    wrong_action_payload["observations"][0]["evidence_id"] = (
        foreign_evidence.evidence_id
    )
    wrong_action = C08SubmissionV2.model_validate(wrong_action_payload)
    assert wrong_action.observations[0].action_id == first.action_id
    assert foreign_evidence.action_id != first.action_id
    report = evaluate_c08(
        public=tree.public,
        evaluator=tree.evaluator,
        submission=wrong_action,
    )
    assert (
        next(
            item.outcome
            for item in report.outcomes
            if item.action_id == first.action_id
        )
        is C08CaseOutcomeV2.WRONG_ACTION
    )


def test_frozen_loader_rejects_missing_extra_directory_symlink_and_digest(
    tmp_path: Path,
) -> None:
    source = _PACKAGED_ROOT

    missing = tmp_path / "missing"
    _copy_frozen(source, missing)
    (missing / "public/public-input.json").unlink()
    with pytest.raises(FrozenC08BenchmarkError, match="inventory"):
        load_frozen_benchmark(missing)

    extra = tmp_path / "extra"
    _copy_frozen(source, extra)
    (extra / "extra.json").write_bytes(b"{}\n")
    with pytest.raises(FrozenC08BenchmarkError, match="inventory"):
        load_frozen_benchmark(extra)

    directory = tmp_path / "directory"
    _copy_frozen(source, directory)
    (directory / "public/public-input.json").unlink()
    (directory / "public/public-input.json").mkdir()
    with pytest.raises(FrozenC08BenchmarkError, match="inventory"):
        load_frozen_benchmark(directory)

    symlink = tmp_path / "symlink"
    _copy_frozen(source, symlink)
    (symlink / "evaluator/truth.json").unlink()
    (symlink / "evaluator/truth.json").symlink_to("../public/public-input.json")
    with pytest.raises(FrozenC08BenchmarkError, match="symlink"):
        load_frozen_benchmark(symlink)

    digest = tmp_path / "digest"
    _copy_frozen(source, digest)
    checksum_path = digest / "SHA256SUMS"
    rows = checksum_path.read_text(encoding="ascii").splitlines()
    checksum_path.write_text(
        "\n".join(
            "0" * 64 + row[64:] if row.endswith("public/public-input.json") else row
            for row in rows
        )
        + "\n",
        encoding="ascii",
    )
    with pytest.raises(FrozenC08BenchmarkError, match="digest"):
        load_frozen_benchmark(digest)


def test_frozen_loader_rejects_noncanonical_json(tmp_path: Path) -> None:
    root = tmp_path / "noncanonical"
    _copy_frozen(_PACKAGED_ROOT, root)
    path = root / "public/public-input.json"
    payload = path.read_bytes()
    noncanonical = json.dumps(json.loads(payload), indent=2).encode("utf-8") + b"\n"
    path.write_bytes(noncanonical)
    _rewrite_checksum(root, "public/public-input.json", noncanonical)
    with pytest.raises(FrozenC08BenchmarkError, match="canonical"):
        load_frozen_benchmark(root)


def test_frozen_loader_rejects_self_consistent_replacement(tmp_path: Path) -> None:
    root = tmp_path / "alternate"
    _write_self_consistent_alternate(root)
    with pytest.raises(FrozenC08BenchmarkError, match="root identity"):
        load_frozen_benchmark(root)


def test_complete_enterprise_v1_inventory_remains_byte_identical() -> None:
    root = Path("enterprise-identity-access-contract")
    actual = {
        path.relative_to(root).as_posix()
        for directory in (root / "examples", root / "schemas")
        for path in directory.glob("enterprise-agentic-*")
        if path.is_file()
    }
    assert actual == set(_V1_DIGESTS)
    for path, expected in _V1_DIGESTS.items():
        payload = (root / path).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected


def test_manifest_model_rejects_non_enterprise_or_unsorted_inventory() -> None:
    manifest = load_packaged_frozen_benchmark().manifest
    with pytest.raises(ValueError, match="enterprise-agentic-c08-v2"):
        C08FrozenManifestV2.model_validate(
            {**manifest.model_dump(mode="json"), "benchmark_id": "asteria"}
        )
    with pytest.raises(ValueError, match="checksum self-exclusion is fixed"):
        C08FrozenManifestV2.model_validate(
            {**manifest.model_dump(mode="json"), "checksum_excludes": []}
        )
    artifact = C08FrozenArtifactV2(
        path="public/z.json",
        byte_size=0,
        sha256="0" * 64,
    )
    first = C08FrozenArtifactV2(
        path="public/a.json",
        byte_size=0,
        sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="sorted"):
        C08FrozenManifestV2.model_validate(
            {
                **manifest.model_dump(mode="json"),
                "public_inventory": [
                    artifact.model_dump(mode="json"),
                    first.model_dump(mode="json"),
                ],
            }
        )

    evaluator_z = C08FrozenArtifactV2(
        path="evaluator/z.json",
        byte_size=0,
        sha256="0" * 64,
    )
    evaluator_a = C08FrozenArtifactV2(
        path="evaluator/a.json",
        byte_size=0,
        sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="sorted"):
        C08FrozenManifestV2.model_validate(
            {
                **manifest.model_dump(mode="json"),
                "evaluator_inventory": [
                    evaluator_z.model_dump(mode="json"),
                    evaluator_a.model_dump(mode="json"),
                ],
            }
        )


@pytest.mark.parametrize(
    ("inventory_name", "wrong_path"),
    (
        ("public_inventory", "evaluator/wrong.json"),
        ("evaluator_inventory", "public/wrong.json"),
    ),
)
def test_manifest_model_rejects_cross_visibility_inventory_paths(
    inventory_name: str,
    wrong_path: str,
) -> None:
    manifest = load_packaged_frozen_benchmark().manifest
    wrong = C08FrozenArtifactV2(
        path=wrong_path,
        byte_size=0,
        sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="must stay under"):
        C08FrozenManifestV2.model_validate(
            {
                **manifest.model_dump(mode="json"),
                inventory_name: [wrong.model_dump(mode="json")],
            }
        )
