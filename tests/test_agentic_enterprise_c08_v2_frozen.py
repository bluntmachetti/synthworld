"""Adversarial coverage for the frozen enterprise C08 v2 benchmark tree."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from synthworld.agentic.enterprise.c08_v2 import (
    C08CaseOutcomeV2,
    C08FrozenArtifactV2,
    C08FrozenManifestV2,
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


def test_public_tree_has_no_evaluator_fields_or_case_truth() -> None:
    tree = load_packaged_frozen_benchmark()
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
    assert next(
        item.outcome
        for item in report.outcomes
        if item.action_id == first.action_id
    ) is C08CaseOutcomeV2.WRONG_ACTION
    report_payload = json.dumps(report.model_dump(mode="json"))
    assert "offline scoring does not prove live evidence retention" in report_payload
    assert "offline scoring does not prove durable logging" in report_payload
    assert "offline scoring does not prove enforcement behavior" in report_payload

    wrong_action_id = tree.public.actions[1].action_id
    wrong_action = reference.model_copy(
        update={
            "observations": (
                first.model_copy(update={"action_id": wrong_action_id}),
                *reference.observations[1:],
            )
        }
    )
    report = evaluate_c08(
        public=tree.public,
        evaluator=tree.evaluator,
        submission=wrong_action,
    )
    assert next(
        item.outcome
        for item in report.outcomes
        if item.action_id == first.action_id
    ) is C08CaseOutcomeV2.WRONG_ACTION


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
