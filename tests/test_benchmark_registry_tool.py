"""Discriminating tests for deterministic benchmark-registry governance."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import pytest

from tools import generate_benchmark_registry as registry

PROJECT_ROOT = Path(__file__).parents[1]
JsonObject = registry.JsonObject
Mutation = Callable[[JsonObject, JsonObject, JsonObject], None]
SCHEMAS = (
    registry.GENERATED_SCHEMA,
    registry.CURATED_SCHEMA,
    registry.RESOLVED_SCHEMA,
    registry.GATES_SCHEMA,
    registry.TRANSITIONS_SCHEMA,
)


def _git(root: Path, *args: str) -> None:
    registry._git(root, args)


def _write_json(path: Path, value: object, *, canonical: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if canonical:
        path.write_bytes(registry.canonical_json(value))
    else:
        path.write_text(json.dumps(value), encoding="utf-8")


def _checks(status: str = "pass") -> list[JsonObject]:
    return [
        {"name": name, "rationale": None, "status": status}
        for name in registry.GATE_CHECK_NAMES
    ]


def _documents(
    root: Path,
    *,
    lifecycle: str = "candidate",
    sensitivity: str = "public_input",
) -> tuple[JsonObject, JsonObject, JsonObject]:
    payload_path = "src/synthworld/benchmarks/sample.json"
    checksum_path = "src/synthworld/benchmarks/SHA256SUMS"
    payload_digest = hashlib.sha256((root / payload_path).read_bytes()).hexdigest()
    checksum_digest = hashlib.sha256((root / checksum_path).read_bytes()).hexdigest()
    published = lifecycle == "published"
    gate_id = "sample-v1" if published else None
    answer_key = (
        "Public answer key" if sensitivity == "public_reference_truth" else None
    )
    curated = {
        "schema_version": "1.0.0",
        "benchmarks": [
            {
                "id": "sample-v1",
                "title": "Sample v1",
                "lifecycle": lifecycle,
                "benchmark_kind": "conformance_fixture",
                "benchmark_version": "1.0.0",
                "evaluation_mode": "public_conformance",
                "introduced_in": "0.1.0",
                "artifact_ids": ["sample:payload", "sample:checksums"],
                "reproduction": (
                    registry._expected_reproduction("sample-v1") if published else None
                ),
                "example_command": None if published else "synthworld generate",
                "docs_route_ids": ["route:GUIDE.md#sample"],
                "limitations_route_id": "route:GUIDE.md#limits",
                "publication_gate_id": gate_id,
                "replacement_id": None,
            }
        ],
        "artifacts": [
            {
                "id": "sample:payload",
                "benchmark_id": "sample-v1",
                "path": payload_path,
                "kind": "evaluator_truth" if answer_key else "public_input",
                "sensitivity": sensitivity,
                "frozen": published,
                "approved_sha256": payload_digest,
                "integrity_record_ids": [f"sha256sum:{checksum_path}"],
                "present_in": ["repository", "python_package"],
                "approved_targets": ["repository", "python_package"],
                "answer_key_label": answer_key,
            },
            {
                "id": "sample:checksums",
                "benchmark_id": "sample-v1",
                "path": checksum_path,
                "kind": "checksum_manifest",
                "sensitivity": "public_input",
                "frozen": published,
                "approved_sha256": checksum_digest,
                "integrity_record_ids": [],
                "present_in": ["repository", "python_package"],
                "approved_targets": ["repository", "python_package"],
                "answer_key_label": None,
            },
        ],
    }
    gates = {
        "schema_version": "1.0.0",
        "gates": (
            [
                {
                    "id": "sample-v1",
                    "benchmark_id": "sample-v1",
                    "benchmark_version": "1.0.0",
                    "decision": "approved",
                    "approved_targets": ["repository", "python_package"],
                    "review_route_id": "route:GOLDEN_REVIEW.md#sample-review",
                    "release_tag": "v0.1.0",
                    "checks": _checks(),
                }
            ]
            if published
            else []
        ),
    }
    transitions = {"schema_version": "1.0.0", "transitions": []}
    return curated, gates, transitions


def _repo(tmp_path: Path, *, lifecycle: str = "candidate") -> Path:
    root = tmp_path / "repository"
    for schema in SCHEMAS:
        target = root / schema
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / schema, target)
    benchmark = root / "src/synthworld/benchmarks"
    benchmark.mkdir(parents=True)
    payload = b'{"synthetic":true}\n'
    (benchmark / "sample.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (benchmark / "SHA256SUMS").write_text(f"{digest}  sample.json\n", encoding="ascii")
    (root / "GUIDE.md").write_text(
        "# Sample\n```md\n# Ignored\n```\n# Limits\n# Limits\n", encoding="utf-8"
    )
    (root / "GOLDEN_REVIEW.md").write_text("# Sample review\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n## [Unreleased]\n## [0.1.0] - 2026-01-01\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    curated, gates, transitions = _documents(root, lifecycle=lifecycle)
    _write_json(root / registry.CURATED_PATH, curated)
    _write_json(root / registry.GATES_PATH, gates)
    _write_json(root / registry.TRANSITIONS_PATH, transitions)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    _git(root, "tag", "v0.1.0")
    return root


def _load(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _rewrite_documents(
    root: Path,
    mutate: Mutation,
    *,
    lifecycle: str = "candidate",
    canonical: bool = True,
) -> None:
    documents = list(_documents(root, lifecycle=lifecycle))
    mutate(*documents)
    for path, value in zip(
        (registry.CURATED_PATH, registry.GATES_PATH, registry.TRANSITIONS_PATH),
        documents,
        strict=True,
    ):
        _write_json(root / path, value, canonical=canonical)


def test_current_repository_discovers_exact_governed_inventory() -> None:
    generated = registry.discover_generated(PROJECT_ROOT)
    assert len(generated["artifacts"]) == 55
    assert generated["artifacts"] == sorted(
        generated["artifacts"], key=lambda item: item["path"]
    )
    assert all(
        forbidden not in json.dumps(generated)
        for forbidden in (
            str(PROJECT_ROOT),
            "lifecycle",
            "sensitivity",
            "approved_targets",
        )
    )
    schemes = {record["scheme"] for record in generated["integrity_records"]}
    assert schemes == {
        "sha256sum",
        "sha256-artifact-set-v1",
        "sha256-path-bound-v1",
        "sha256-size-manifest-v1",
    }


def test_tracked_artifact_reader_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(b"{}\n")
    (tmp_path / "linked.json").symlink_to(target)

    with pytest.raises(registry.RegistryError, match="tracked artifact is a symlink"):
        registry._read_artifact_bytes(tmp_path, ("linked.json",))


def test_write_check_canonicalization_drift_and_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    curated = _load(root / registry.CURATED_PATH)
    _write_json(root / registry.CURATED_PATH, curated, canonical=False)
    generated, resolved = registry.run(root, check=False, require_tags=True)
    assert generated["schema_version"] == resolved["schema_version"] == "1.0.0"
    assert (root / registry.CURATED_PATH).read_bytes() == registry.canonical_json(
        curated
    )
    registry.run(root, check=True)
    assert registry.main(["--root", str(root), "--check", "--require-tags"]) == 0
    (root / registry.GENERATED_PATH).write_text("{}\n", encoding="utf-8")
    with pytest.raises(registry.RegistryError, match="generated output drift"):
        registry.run(root, check=True)
    assert registry.main(["--root", str(root), "--check"]) == 1
    assert "benchmark registry error" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b'{"a":1,"a":2}\n', "duplicate JSON key"),
        (b"{\n", "invalid JSON at line"),
        (b"[]\n", "top-level JSON value"),
        (b"\xff", "invalid UTF-8"),
    ],
)
def test_json_decode_errors(payload: bytes, message: str) -> None:
    with pytest.raises(registry.RegistryError, match=message):
        registry._decode_json(payload, "fixture")


def test_noncanonical_check_and_missing_input(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    curated = _load(root / registry.CURATED_PATH)
    _write_json(root / registry.CURATED_PATH, curated, canonical=False)
    with pytest.raises(registry.RegistryError, match="not canonical"):
        registry.run(root, check=True)
    (root / registry.CURATED_PATH).unlink()
    with pytest.raises(registry.RegistryError, match="cannot read"):
        registry.run(root, check=False)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "not canonical"),
        (b"bad  x\n", "invalid checksum row"),
        (b"0" * 64 + b"  x\n" + b"1" * 64 + b"  x\n", "duplicate"),
        (b"0" * 64 + b"  ../x\n", "unsafe"),
        (b"\xff\n", "not ASCII"),
    ],
)
def test_checksum_parser_rejects_invalid_records(payload: bytes, message: str) -> None:
    with pytest.raises(registry.RegistryError, match=message):
        registry._parse_sha256sum(payload, "manifest")


def test_checksum_discovery_rejects_self_unknown_and_mismatch(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    manifest = root / "src/synthworld/benchmarks/SHA256SUMS"
    digest = "0" * 64
    for row, message in (
        (f"{digest}  SHA256SUMS\n", "include itself"),
        (f"{digest}  absent.json\n", "unknown manifest member"),
        (f"{digest}  sample.json\n", "checksum mismatch"),
    ):
        manifest.write_text(row, encoding="ascii")
        _git(root, "add", str(manifest.relative_to(root)))
        with pytest.raises(registry.RegistryError, match=message):
            registry.discover_generated(root)


def _asteria_mapping() -> dict[str, bytes]:
    public_owner = f"{registry.BENCHMARK_PREFIX}asteria-agentic-v1/public/manifest.json"
    evaluator_owner = (
        f"{registry.BENCHMARK_PREFIX}asteria-agentic-v1/evaluator/checksums.json"
    )
    public_payload = b"public\n"
    evaluator_payload = b"truth\n"
    public_files = {"input.json": public_payload}
    evaluator_files = {"truth.json": evaluator_payload}
    public = {
        "artifacts": {"input.json": hashlib.sha256(public_payload).hexdigest()},
        "artifact_set_digest": registry.artifact_set_digest(public_files),
    }
    evaluator = {
        "checksum_scheme": "sha256-artifact-set-v1",
        "evaluator_artifacts": {
            "truth.json": hashlib.sha256(evaluator_payload).hexdigest()
        },
        "public_artifact_set_digest": registry.artifact_set_digest(public_files),
        "evaluator_artifact_set_digest": registry.artifact_set_digest(evaluator_files),
    }
    return {
        public_owner: registry.canonical_json(public),
        public_owner.replace("manifest.json", "input.json"): public_payload,
        evaluator_owner: registry.canonical_json(evaluator),
        evaluator_owner.replace("checksums.json", "truth.json"): evaluator_payload,
    }


def _verify_asteria(artifacts: dict[str, bytes]) -> None:
    memberships: dict[str, list[str]] = {path: [] for path in artifacts}
    registry._verify_asteria(artifacts, memberships, [])


def test_asteria_valid_and_cross_digest_failures() -> None:
    artifacts = _asteria_mapping()
    _verify_asteria(artifacts)
    public_owner = f"{registry.BENCHMARK_PREFIX}asteria-agentic-v1/public/manifest.json"
    evaluator_owner = (
        f"{registry.BENCHMARK_PREFIX}asteria-agentic-v1/evaluator/checksums.json"
    )
    for owner, field, value, message in (
        (public_owner, "artifact_set_digest", "0" * 64, "set digest"),
        (evaluator_owner, "checksum_scheme", "other", "unsupported"),
        (evaluator_owner, "public_artifact_set_digest", "0" * 64, "cross-digest"),
        (evaluator_owner, "evaluator_artifact_set_digest", "0" * 64, "evaluator set"),
    ):
        changed = copy.deepcopy(artifacts)
        document = registry._decode_json(changed[owner], owner)
        document[field] = value
        changed[owner] = registry.canonical_json(document)
        with pytest.raises(registry.RegistryError, match=message):
            _verify_asteria(changed)


def test_asteria_rejects_incomplete_invalid_maps_inventory_and_digest() -> None:
    artifacts = _asteria_mapping()
    public_owner = f"{registry.BENCHMARK_PREFIX}asteria-agentic-v1/public/manifest.json"
    evaluator_owner = (
        f"{registry.BENCHMARK_PREFIX}asteria-agentic-v1/evaluator/checksums.json"
    )
    incomplete = dict(artifacts)
    incomplete.pop(evaluator_owner)
    with pytest.raises(registry.RegistryError, match="incomplete"):
        _verify_asteria(incomplete)
    for owner, field in (
        (public_owner, "artifacts"),
        (evaluator_owner, "evaluator_artifacts"),
    ):
        changed = copy.deepcopy(artifacts)
        document = registry._decode_json(changed[owner], owner)
        document[field] = []
        changed[owner] = registry.canonical_json(document)
        with pytest.raises(registry.RegistryError, match=r"invalid .*artifacts map"):
            _verify_asteria(changed)
    changed = copy.deepcopy(artifacts)
    document = registry._decode_json(changed[public_owner], public_owner)
    document["artifacts"]["input.json"] = "0" * 64
    changed[public_owner] = registry.canonical_json(document)
    with pytest.raises(registry.RegistryError, match="checksum mismatch"):
        _verify_asteria(changed)
    changed = copy.deepcopy(artifacts)
    changed[public_owner.replace("manifest.json", "extra.json")] = b"{}\n"
    with pytest.raises(registry.RegistryError, match="inventory differs"):
        _verify_asteria(changed)
    for owner, field, member, message in (
        (public_owner, "artifacts", "absent.json", "invalid member"),
        (evaluator_owner, "evaluator_artifacts", "absent.json", "invalid member"),
    ):
        changed = copy.deepcopy(artifacts)
        document = registry._decode_json(changed[owner], owner)
        document[field] = {member: "0" * 64}
        changed[owner] = registry.canonical_json(document)
        with pytest.raises(registry.RegistryError, match=message):
            _verify_asteria(changed)
    changed = copy.deepcopy(artifacts)
    document = registry._decode_json(changed[evaluator_owner], evaluator_owner)
    document["evaluator_artifacts"]["truth.json"] = "0" * 64
    changed[evaluator_owner] = registry.canonical_json(document)
    with pytest.raises(registry.RegistryError, match="checksum mismatch"):
        _verify_asteria(changed)
    changed = copy.deepcopy(artifacts)
    changed[evaluator_owner.replace("checksums.json", "extra.json")] = b"{}\n"
    with pytest.raises(registry.RegistryError, match="inventory differs"):
        _verify_asteria(changed)


def _path_bound_descriptor(path: str, payload: bytes) -> JsonObject:
    return {
        "byte_size": len(payload),
        "path": path,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _asteria_v2_mapping() -> dict[str, bytes]:
    root = f"{registry.BENCHMARK_PREFIX}asteria-agentic-c08-v2"
    public_payload = b"public\n"
    evaluator_payload = b"truth\n"
    public_files = {"c08-asteria-public.json": public_payload}
    evaluator_files = {"c08-asteria-evaluator.json": evaluator_payload}
    public_manifest = registry.canonical_json(
        {
            "artifact_set_digest": registry.artifact_set_digest(public_files),
            "artifacts": [
                {
                    **_path_bound_descriptor("c08-asteria-public.json", public_payload),
                    "synthetic": True,
                }
            ],
            "benchmark_id": "asteria-agentic-c08-v2",
            "schema_version": "2.0.0",
            "seed": 20260809,
            "synthetic": True,
            "visibility": "public",
        }
    )
    evaluator_manifest = registry.canonical_json(
        {
            "artifact_set_digest": registry.artifact_set_digest(evaluator_files),
            "artifacts": [
                {
                    **_path_bound_descriptor(
                        "c08-asteria-evaluator.json", evaluator_payload
                    ),
                    "synthetic": True,
                }
            ],
            "benchmark_id": "asteria-agentic-c08-v2",
            "public_input_digest": hashlib.sha256(public_payload).hexdigest(),
            "schema_version": "2.0.0",
            "seed": 20260809,
            "synthetic": True,
            "visibility": "evaluator",
        }
    )
    root_files = {
        "evaluator/manifest.json": evaluator_manifest,
        "evaluator/c08-asteria-evaluator.json": evaluator_payload,
        "public/c08-asteria-public.json": public_payload,
        "public/manifest.json": public_manifest,
    }
    root_manifest = registry.canonical_json(
        {
            "artifact_set_digest": registry.artifact_set_digest(root_files),
            "artifacts": [
                {**_path_bound_descriptor(path, payload), "synthetic": True}
                for path, payload in sorted(root_files.items())
            ],
            "benchmark_id": "asteria-agentic-c08-v2",
            "evaluator_artifact_set_digest": registry.artifact_set_digest(
                evaluator_files
            ),
            "evaluator_public_input_digest": hashlib.sha256(public_payload).hexdigest(),
            "public_artifact_set_digest": registry.artifact_set_digest(public_files),
            "public_input_digest": hashlib.sha256(public_payload).hexdigest(),
            "schema_version": "2.0.0",
            "seed": 20260809,
            "synthetic": True,
            "visibility": "root",
        }
    )
    return {
        f"{root}/manifest.json": root_manifest,
        f"{root}/public/c08-asteria-public.json": public_payload,
        f"{root}/public/manifest.json": public_manifest,
        f"{root}/evaluator/c08-asteria-evaluator.json": evaluator_payload,
        f"{root}/evaluator/manifest.json": evaluator_manifest,
    }


def test_asteria_v2_path_bound_manifests_record_layered_integrity() -> None:
    artifacts = _asteria_v2_mapping()
    memberships: dict[str, list[str]] = {path: [] for path in artifacts}
    records: list[JsonObject] = []
    registry._verify_asteria_v2(artifacts, memberships, records)

    root = f"{registry.BENCHMARK_PREFIX}asteria-agentic-c08-v2"
    root_record = f"c08-asteria-root:{root}/manifest.json"
    public_record = f"c08-asteria-public:{root}/public/manifest.json"
    evaluator_record = f"c08-asteria-evaluator:{root}/evaluator/manifest.json"
    assert memberships[f"{root}/public/c08-asteria-public.json"] == [
        root_record,
        public_record,
    ]
    assert memberships[f"{root}/evaluator/c08-asteria-evaluator.json"] == [
        root_record,
        evaluator_record,
    ]
    assert memberships[f"{root}/public/manifest.json"] == [root_record]
    assert memberships[f"{root}/evaluator/manifest.json"] == [root_record]
    assert {record["scheme"] for record in records} == {"sha256-path-bound-v1"}


def test_asteria_v2_rejects_partial_extra_and_contract_drift() -> None:
    artifacts = _asteria_v2_mapping()
    root = f"{registry.BENCHMARK_PREFIX}asteria-agentic-c08-v2"
    registry._verify_asteria_v2({}, {}, [])
    for removed in artifacts:
        changed = dict(artifacts)
        changed.pop(removed)
        memberships: dict[str, list[str]] = {path: [] for path in changed}
        with pytest.raises(registry.RegistryError, match="inventory differs"):
            registry._verify_asteria_v2(changed, memberships, [])
    changed = {**artifacts, f"{root}/extra.json": b"{}\n"}
    with pytest.raises(registry.RegistryError, match="inventory differs"):
        registry._verify_asteria_v2(changed, {path: [] for path in changed}, [])
    for owner, field in (
        (f"{root}/public/manifest.json", "benchmark_id"),
        (f"{root}/evaluator/manifest.json", "public_input_digest"),
        (f"{root}/manifest.json", "public_artifact_set_digest"),
    ):
        changed = dict(artifacts)
        document = registry._decode_json(changed[owner], owner)
        document[field] = "wrong"
        changed[owner] = registry.canonical_json(document)
        if owner != f"{root}/manifest.json":
            root_owner = f"{root}/manifest.json"
            root_document = registry._decode_json(changed[root_owner], root_owner)
            root_files = {
                path.removeprefix(f"{root}/"): payload
                for path, payload in changed.items()
                if path != root_owner
            }
            root_document["artifact_set_digest"] = registry.artifact_set_digest(
                root_files
            )
            root_document["artifacts"] = [
                {**_path_bound_descriptor(path, payload), "synthetic": True}
                for path, payload in sorted(root_files.items())
            ]
            changed[root_owner] = registry.canonical_json(root_document)
        memberships = {path: [] for path in changed}
        with pytest.raises(registry.RegistryError, match="manifest contract differs"):
            registry._verify_asteria_v2(changed, memberships, [])


def _verify_path_bound_fixture(
    manifest: JsonObject,
    *,
    expected_members: tuple[str, ...] | None = None,
    include_owner: bool = True,
) -> None:
    owner = f"{registry.BENCHMARK_PREFIX}path-bound/manifest.json"
    payload_path = f"{registry.BENCHMARK_PREFIX}path-bound/input.json"
    artifacts = {payload_path: b"payload\n"}
    if include_owner:
        artifacts[owner] = registry.canonical_json(manifest)
    memberships: dict[str, list[str]] = {path: [] for path in artifacts}
    registry._verify_path_bound_manifest(
        artifacts,
        memberships,
        [],
        owner=owner,
        record_prefix="path-bound",
        expected_members=expected_members or (payload_path,),
    )


def test_path_bound_manifest_rejects_missing_invalid_and_duplicate_descriptors() -> (
    None
):
    payload = b"payload\n"
    valid = _path_bound_descriptor("input.json", payload)
    digest = registry.artifact_set_digest({"input.json": payload})
    with pytest.raises(registry.RegistryError, match="missing manifest"):
        _verify_path_bound_fixture({}, include_owner=False)
    for descriptors in (
        None,
        [],
        [None],
        [{**valid, "path": None}],
        [valid, valid],
        [{**valid, "sha256": None}],
        [{**valid, "sha256": "invalid"}],
        [{**valid, "byte_size": None}],
    ):
        with pytest.raises(registry.RegistryError, match="invalid artifact descriptor"):
            _verify_path_bound_fixture(
                {"artifact_set_digest": digest, "artifacts": descriptors}
            )


def test_path_bound_manifest_rejects_unknown_binding_inventory_and_set_digest() -> None:
    payload = b"payload\n"
    valid = _path_bound_descriptor("input.json", payload)
    digest = registry.artifact_set_digest({"input.json": payload})
    failures = (
        (
            {"artifact_set_digest": digest, "artifacts": [{**valid, "path": "x"}]},
            None,
            "unknown manifest member",
        ),
        (
            {
                "artifact_set_digest": digest,
                "artifacts": [{**valid, "byte_size": len(payload) + 1}],
            },
            None,
            "manifest binding differs",
        ),
        (
            {
                "artifact_set_digest": digest,
                "artifacts": [{**valid, "sha256": "0" * 64}],
            },
            None,
            "manifest binding differs",
        ),
        (
            {"artifact_set_digest": digest, "artifacts": [valid]},
            (f"{registry.BENCHMARK_PREFIX}path-bound/extra.json",),
            "artifact inventory differs",
        ),
        (
            {"artifact_set_digest": "0" * 64, "artifacts": [valid]},
            None,
            "artifact set digest differs",
        ),
    )
    for manifest, expected_members, message in failures:
        with pytest.raises(registry.RegistryError, match=message):
            if expected_members is None:
                _verify_path_bound_fixture(manifest)
            else:
                _verify_path_bound_fixture(manifest, expected_members=expected_members)


def test_enterprise_c08_v2_requires_the_exact_checksum_inventory() -> None:
    root = f"{registry.BENCHMARK_PREFIX}enterprise-agentic-c08-v2"
    owner = f"{root}/SHA256SUMS"
    members = {
        "evaluator/truth.json": b"truth\n",
        "public/public-input.json": b"public\n",
    }
    manifest = {
        "benchmark_id": "enterprise-agentic-c08-v2",
        "checksum_algorithm": "sha256",
        "checksum_excludes": ["SHA256SUMS"],
        "checksum_file": "SHA256SUMS",
        "evaluator_inventory": [
            {
                **_path_bound_descriptor(
                    "evaluator/truth.json", members["evaluator/truth.json"]
                ),
                "synthetic": True,
            }
        ],
        "public_input_digest": hashlib.sha256(
            members["public/public-input.json"]
        ).hexdigest(),
        "public_inventory": [
            {
                **_path_bound_descriptor(
                    "public/public-input.json", members["public/public-input.json"]
                ),
                "synthetic": True,
            }
        ],
        "schema_version": "2.0.0",
        "seed": 20260809,
        "synthetic": True,
    }
    members["manifest.json"] = registry.canonical_json(manifest)
    checksum = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {path}\n"
        for path, payload in sorted(members.items())
    ).encode("ascii")
    artifacts = {owner: checksum}
    artifacts.update({f"{root}/{path}": payload for path, payload in members.items()})
    registry._verify_enterprise_c08_v2({})
    registry._verify_enterprise_c08_v2(artifacts)

    partial = dict(artifacts)
    partial.pop(owner)
    with pytest.raises(registry.RegistryError, match="inventory differs"):
        registry._verify_enterprise_c08_v2(partial)
    extra = {**artifacts, f"{root}/extra.json": b"{}\n"}
    with pytest.raises(registry.RegistryError, match="inventory differs"):
        registry._verify_enterprise_c08_v2(extra)
    reordered = dict(artifacts)
    reordered[owner] = b"".join(reversed(checksum.splitlines(keepends=True)))
    with pytest.raises(registry.RegistryError, match="checksum rows differ"):
        registry._verify_enterprise_c08_v2(reordered)
    invalid_manifest = dict(artifacts)
    invalid_manifest[f"{root}/manifest.json"] = b"{}\n"
    invalid_manifest[owner] = checksum.replace(
        hashlib.sha256(members["manifest.json"]).hexdigest().encode("ascii"),
        hashlib.sha256(b"{}\n").hexdigest().encode("ascii"),
    )
    with pytest.raises(registry.RegistryError, match="manifest differs"):
        registry._verify_enterprise_c08_v2(invalid_manifest)


def _authority_mapping() -> dict[str, bytes]:
    root = f"{registry.BENCHMARK_PREFIX}authority-governance-v1"
    result: dict[str, bytes] = {}
    checksum_rows = []
    for visibility, name in (
        ("public", "authority-governance-input.json"),
        ("evaluator", "authority-governance-evaluator.json"),
    ):
        payload = f"{visibility}\n".encode()
        payload_path = f"{root}/{visibility}/{name}"
        result[payload_path] = payload
        descriptor = {
            "artifacts": [
                {
                    "byte_size": len(payload),
                    "digest": {
                        "algorithm": "sha256",
                        "value": hashlib.sha256(payload).hexdigest(),
                    },
                    "path": name,
                }
            ]
        }
        manifest_path = f"{root}/{visibility}/manifest.json"
        result[manifest_path] = registry.canonical_json(descriptor)
    for relative in (
        "evaluator/authority-governance-evaluator.json",
        "evaluator/manifest.json",
        "public/authority-governance-input.json",
        "public/manifest.json",
    ):
        checksum_rows.append(
            f"{hashlib.sha256(result[f'{root}/{relative}']).hexdigest()}  {relative}"
        )
    result[f"{root}/SHA256SUMS"] = ("\n".join(checksum_rows) + "\n").encode()
    return result


def _verify_authority(artifacts: dict[str, bytes]) -> None:
    memberships: dict[str, list[str]] = {path: [] for path in artifacts}
    records: list[JsonObject] = []
    registry._verify_sha256_manifests(artifacts, memberships, records)
    registry._verify_authority_manifests(artifacts, memberships, records)


def _refresh_authority_checksum(artifacts: dict[str, bytes]) -> None:
    root = f"{registry.BENCHMARK_PREFIX}authority-governance-v1"
    rows: list[str] = []
    for relative in (
        "evaluator/authority-governance-evaluator.json",
        "evaluator/manifest.json",
        "public/authority-governance-input.json",
        "public/manifest.json",
    ):
        digest = hashlib.sha256(artifacts[f"{root}/{relative}"]).hexdigest()
        rows.append(f"{digest}  {relative}")
    artifacts[f"{root}/SHA256SUMS"] = ("\n".join(rows) + "\n").encode()


def test_authority_valid_and_manifest_failures() -> None:
    artifacts = _authority_mapping()
    _verify_authority(artifacts)
    root = f"{registry.BENCHMARK_PREFIX}authority-governance-v1"
    owner = f"{root}/public/manifest.json"
    transformations: tuple[tuple[Callable[[JsonObject], None], str], ...] = (
        (lambda descriptor: descriptor.update(byte_size=999), "binding differs"),
        (lambda descriptor: descriptor.update(path="../x"), "unsafe"),
        (
            lambda descriptor: descriptor.update(
                digest={"algorithm": "md5", "value": "0" * 64}
            ),
            "invalid artifact descriptor",
        ),
    )
    for transform, message in transformations:
        changed = copy.deepcopy(artifacts)
        document = registry._decode_json(changed[owner], owner)
        transform(document["artifacts"][0])
        changed[owner] = registry.canonical_json(document)
        _refresh_authority_checksum(changed)
        with pytest.raises(registry.RegistryError, match=message):
            _verify_authority(changed)
    changed = copy.deepcopy(artifacts)
    document = registry._decode_json(changed[owner], owner)
    document["artifacts"] = []
    changed[owner] = registry.canonical_json(document)
    _refresh_authority_checksum(changed)
    with pytest.raises(registry.RegistryError, match="invalid artifact descriptors"):
        _verify_authority(changed)


def test_authority_rejects_root_descriptor_and_inventory_errors() -> None:
    root = f"{registry.BENCHMARK_PREFIX}authority-governance-v1"
    owner = f"{root}/public/manifest.json"
    cases: list[tuple[Callable[[JsonObject], None], str]] = [
        (
            lambda document: document.update(artifacts=["bad"]),
            "invalid artifact descriptor",
        ),
        (
            lambda document: document["artifacts"][0].update(path="absent.json"),
            "unknown manifest member",
        ),
        (
            lambda document: document["artifacts"].append(
                copy.deepcopy(document["artifacts"][0])
            ),
            "invalid artifact descriptor",
        ),
    ]
    for mutate, message in cases:
        artifacts = _authority_mapping()
        document = registry._decode_json(artifacts[owner], owner)
        mutate(document)
        artifacts[owner] = registry.canonical_json(document)
        _refresh_authority_checksum(artifacts)
        with pytest.raises(registry.RegistryError, match=message):
            _verify_authority(artifacts)
    artifacts = _authority_mapping()
    artifacts[f"{root}/public/extra.json"] = b"{}\n"
    with pytest.raises(registry.RegistryError, match="artifact inventory differs"):
        _verify_authority(artifacts)
    artifacts = _authority_mapping()
    checksum = f"{root}/SHA256SUMS"
    artifacts[checksum] = artifacts[checksum].replace(
        b"public/manifest.json", b"public/other.json"
    )
    artifacts[f"{root}/public/other.json"] = artifacts.pop(
        f"{root}/public/manifest.json"
    )
    memberships: dict[str, list[str]] = {path: [] for path in artifacts}
    with pytest.raises(registry.RegistryError, match="root coverage"):
        registry._verify_authority_manifests(artifacts, memberships, [])


def test_routes_ignore_fences_and_suffix_collisions(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    routes = registry.discover_routes(root)
    assert "route:GUIDE.md#sample" in routes
    assert "route:GUIDE.md#ignored" not in routes
    assert "route:GUIDE.md#limits-1" in routes
    assert registry._slug("Hello, `World`!") == "hello-world"
    registry._validate_routes(
        {"id": "route-only", "docs_route_ids": [], "limitations_route_id": None},
        routes,
    )


def test_discovery_io_schema_and_release_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.setattr(registry, "_git", lambda *_args: b"\xff\0")
    with pytest.raises(registry.RegistryError, match="non-UTF-8"):
        registry.tracked_paths(root)
    monkeypatch.undo()
    (root / "src/synthworld/benchmarks/sample.json").unlink()
    with pytest.raises(registry.RegistryError, match="cannot read tracked artifact"):
        registry.discover_generated(root)

    root = _repo(tmp_path / "schema")
    schema_path = root / registry.CURATED_SCHEMA
    schema_path.write_text('{"type": 7}\n', encoding="utf-8")
    with pytest.raises(registry.RegistryError, match="invalid JSON Schema"):
        registry._load_schema(root, registry.CURATED_SCHEMA)
    (root / "GUIDE.md").unlink()
    with pytest.raises(registry.RegistryError, match="cannot read Markdown"):
        registry.discover_routes(root)

    root = _repo(tmp_path / "release")
    (root / "CHANGELOG.md").unlink()
    with pytest.raises(
        registry.RegistryError, match="cannot discover release evidence"
    ):
        registry.discover_releases(root)
    (root / "CHANGELOG.md").write_text("## [Unreleased]\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nversion = 1\n", encoding="utf-8")
    with pytest.raises(registry.RegistryError, match=r"project.version"):
        registry.discover_releases(root)
    with pytest.raises(registry.RegistryError, match="invalid id"):
        registry._unique([{}], "id", "items")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda c, _g, _t: c["benchmarks"].append(copy.deepcopy(c["benchmarks"][0])),
            "duplicate id",
        ),
        (
            lambda c, _g, _t: c["artifacts"].append(copy.deepcopy(c["artifacts"][0])),
            "duplicate id",
        ),
        (
            lambda c, _g, _t: c["benchmarks"][0]["artifact_ids"].append(
                "sample:payload"
            ),
            "duplicate artifact assignment",
        ),
        (
            lambda c, _g, _t: c["benchmarks"][0]["artifact_ids"].append("missing"),
            "unknown artifact",
        ),
        (
            lambda c, _g, _t: c["benchmarks"][0]["artifact_ids"].pop(),
            "unassigned curated artifact",
        ),
        (
            lambda c, _g, _t: c["artifacts"][0].update(
                path="src/synthworld/benchmarks/missing.json"
            ),
            "unknown tracked path",
        ),
        (
            lambda c, _g, _t: c["artifacts"][1].update(path=c["artifacts"][0]["path"]),
            "assigned twice",
        ),
        (
            lambda c, _g, _t: c["artifacts"][0]["integrity_record_ids"].append(
                "missing"
            ),
            "unknown integrity",
        ),
        (
            lambda c, _g, _t: c["artifacts"][0]["integrity_record_ids"].clear(),
            "incomplete integrity coverage",
        ),
        (
            lambda c, _g, _t: c["artifacts"][1].update(kind="public_input"),
            "non-manifest payload lacks integrity coverage",
        ),
        (
            lambda c, _g, _t: c["benchmarks"][0]["docs_route_ids"].append(
                "route:NO.md#no"
            ),
            "unknown documentation route",
        ),
        (
            lambda c, _g, _t: c["benchmarks"][0].update(introduced_in="9.9.9"),
            "unknown introduced release",
        ),
    ],
)
def test_exact_assignment_and_evidence_failures(
    tmp_path: Path, mutation: Mutation, message: str
) -> None:
    root = _repo(tmp_path)
    _rewrite_documents(root, mutation)
    with pytest.raises(registry.RegistryError, match=message):
        registry.run(root, check=False)


def test_remaining_assignment_and_release_semantics(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def second_benchmark(c: JsonObject, _g: JsonObject, _t: JsonObject) -> None:
        duplicate = copy.deepcopy(c["benchmarks"][0])
        duplicate.update(id="other", title="Other", artifact_ids=["sample:payload"])
        c["benchmarks"].append(duplicate)

    _rewrite_documents(root, second_benchmark)
    with pytest.raises(registry.RegistryError, match="multiple benchmarks"):
        registry.run(root, check=False)

    def mismatch(c: JsonObject, _g: JsonObject, _t: JsonObject) -> None:
        c["artifacts"][0]["benchmark_id"] = "other"

    _rewrite_documents(root, mismatch)
    with pytest.raises(registry.RegistryError, match="benchmark_id differs"):
        registry.run(root, check=False)

    def orphan_generated(c: JsonObject, _g: JsonObject, _t: JsonObject) -> None:
        c["benchmarks"][0]["artifact_ids"].pop()
        c["artifacts"].pop()

    _rewrite_documents(root, orphan_generated)
    with pytest.raises(registry.RegistryError, match="unassigned generated artifact"):
        registry.run(root, check=False)

    def bad_replacement(c: JsonObject, _g: JsonObject, _t: JsonObject) -> None:
        c["benchmarks"][0]["replacement_id"] = "missing"

    _rewrite_documents(root, bad_replacement)
    with pytest.raises(registry.RegistryError, match="unknown replacement"):
        registry.run(root, check=False)

    def self_replacement(c: JsonObject, _g: JsonObject, _t: JsonObject) -> None:
        c["benchmarks"][0]["replacement_id"] = "sample-v1"

    _rewrite_documents(root, self_replacement)
    with pytest.raises(registry.RegistryError, match="self replacement"):
        registry.run(root, check=False)

    def unreleased(c: JsonObject, _g: JsonObject, _t: JsonObject) -> None:
        c["benchmarks"][0]["introduced_in"] = "unreleased"

    _rewrite_documents(root, unreleased)
    registry.run(root, check=False, require_tags=True)
    _rewrite_documents(root, unreleased, lifecycle="published")
    with pytest.raises(registry.RegistryError, match="invalid unreleased"):
        registry.run(root, check=False)


def test_public_reference_truth_passes_and_private_material_fails(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    curated, gates, transitions = _documents(root, sensitivity="public_reference_truth")
    _write_json(root / registry.CURATED_PATH, curated)
    _write_json(root / registry.GATES_PATH, gates)
    _write_json(root / registry.TRANSITIONS_PATH, transitions)
    registry.run(root, check=False)
    curated["artifacts"][0]["answer_key_label"] = None
    _write_json(root / registry.CURATED_PATH, curated)
    with pytest.raises(registry.RegistryError, match="answer-key label"):
        registry.run(root, check=False)
    curated["artifacts"][0].update(
        sensitivity="private_held_out_truth", answer_key_label=None
    )
    _write_json(root / registry.CURATED_PATH, curated)
    with pytest.raises(registry.RegistryError, match="exposes material"):
        registry.run(root, check=False)


def test_private_metadata_and_public_missing_path_semantics(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    curated, gates, transitions = _documents(root)
    private = copy.deepcopy(curated["artifacts"][0])
    private.update(
        id="sample:private",
        path=None,
        sensitivity="private_held_out_truth",
        approved_sha256=None,
        integrity_record_ids=[],
        present_in=[],
        approved_targets=[],
        answer_key_label=None,
    )
    curated["artifacts"].append(private)
    curated["benchmarks"][0]["artifact_ids"].append("sample:private")
    _write_json(root / registry.CURATED_PATH, curated)
    _write_json(root / registry.GATES_PATH, gates)
    _write_json(root / registry.TRANSITIONS_PATH, transitions)
    _, resolved = registry.run(root, check=False)
    private_resolved = next(
        item
        for item in resolved["benchmarks"][0]["artifacts"]
        if item["id"] == "sample:private"
    )
    assert private_resolved["generated"] is None
    private["sensitivity"] = "public_input"
    _write_json(root / registry.CURATED_PATH, curated)
    with pytest.raises(registry.RegistryError, match="requires a tracked path"):
        registry.run(root, check=False)


def test_schema_rejects_axis_vocabulary_and_unknown_properties(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    curated = _load(root / registry.CURATED_PATH)
    for field, value in (
        ("lifecycle", "generated_profile"),
        ("lifecycle", "held_out_private"),
        ("benchmark_kind", "published"),
    ):
        changed = copy.deepcopy(curated)
        changed["benchmarks"][0][field] = value
        with pytest.raises(registry.RegistryError, match="validation failed"):
            registry._validate_schema(root, registry.CURATED_SCHEMA, changed)
    curated["extra"] = True
    with pytest.raises(registry.RegistryError, match="validation failed"):
        registry._validate_schema(root, registry.CURATED_SCHEMA, curated)
    for benchmark_kind, evaluation_mode in (
        ("frozen_fixture", "profile_smoke"),
        ("generated_profile", "public_reference"),
        ("generated_benchmark", "public_conformance"),
        ("projection", "public_conformance"),
    ):
        changed = copy.deepcopy(curated)
        changed["benchmarks"][0].update(
            benchmark_kind=benchmark_kind, evaluation_mode=evaluation_mode
        )
        with pytest.raises(registry.RegistryError, match="validation failed"):
            registry._validate_schema(root, registry.CURATED_SCHEMA, changed)


def test_candidate_hf_and_superseded_rules(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def add_hf(c: JsonObject, _g: JsonObject, _t: JsonObject) -> None:
        c["artifacts"][0]["approved_targets"].append("hugging_face_raw")

    _rewrite_documents(root, add_hf)
    with pytest.raises(registry.RegistryError, match="authorizes HF"):
        registry.run(root, check=False)

    def supersede(c: JsonObject, _g: JsonObject, _t: JsonObject) -> None:
        benchmark = c["benchmarks"][0]
        benchmark["lifecycle"] = "superseded"
        benchmark["reproduction"] = registry._expected_reproduction("sample-v1")
        benchmark["example_command"] = None

    _rewrite_documents(root, supersede)
    with pytest.raises(registry.RegistryError, match="needs replacement"):
        registry.run(root, check=False)

    def unknown_gate(c: JsonObject, _g: JsonObject, _t: JsonObject) -> None:
        c["benchmarks"][0]["publication_gate_id"] = "missing"

    _rewrite_documents(root, unknown_gate)
    with pytest.raises(registry.RegistryError, match="must omit publication gate"):
        registry.run(root, check=False)

    def known_gate(c: JsonObject, g: JsonObject, _t: JsonObject) -> None:
        c["benchmarks"][0]["publication_gate_id"] = "sample-v1"
        g["gates"] = _documents(root, lifecycle="published")[1]["gates"]

    _rewrite_documents(root, known_gate)
    with pytest.raises(registry.RegistryError, match="must omit publication gate"):
        registry.run(root, check=False)

    def orphan_gate(_c: JsonObject, g: JsonObject, _t: JsonObject) -> None:
        g["gates"] = _documents(root, lifecycle="published")[1]["gates"]

    _rewrite_documents(root, orphan_gate)
    with pytest.raises(registry.RegistryError, match="unassociated publication gate"):
        registry.run(root, check=False)


def test_superseded_benchmark_retains_gate_and_frozen_governance(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, lifecycle="published")
    curated, gates, transitions = _documents(root, lifecycle="published")
    replacement = copy.deepcopy(curated["benchmarks"][0])
    replacement.update(
        id="sample-v2",
        title="Sample v2",
        lifecycle="candidate",
        benchmark_version="2.0.0",
        artifact_ids=[],
        publication_gate_id=None,
        reproduction=None,
        example_command="synthworld generate",
    )
    curated["benchmarks"].append(replacement)
    curated["benchmarks"][0].update(lifecycle="superseded", replacement_id="sample-v2")
    _write_json(root / registry.CURATED_PATH, curated)
    _write_json(root / registry.GATES_PATH, gates)
    _write_json(root / registry.TRANSITIONS_PATH, transitions)
    _, resolved = registry.run(root, check=False)
    assert resolved["benchmarks"][0]["lifecycle"] == "superseded"
    curated["benchmarks"][0]["publication_gate_id"] = None
    _write_json(root / registry.CURATED_PATH, curated)
    with pytest.raises(registry.RegistryError, match="governed benchmark needs a gate"):
        registry.run(root, check=False)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda c, _g, _t: c["benchmarks"][0].update(publication_gate_id=None),
            "needs a gate",
        ),
        (
            lambda _c, g, _t: g["gates"][0].update(decision="blocked"),
            "does not approve",
        ),
        (
            lambda _c, g, _t: g["gates"][0]["checks"][0].update(status="pending"),
            "pending check",
        ),
        (
            lambda _c, g, _t: g["gates"][0]["checks"][0].update(
                status="not_applicable", rationale=None
            ),
            "needs rationale",
        ),
        (lambda c, _g, _t: c["artifacts"][0].update(frozen=False), "must be frozen"),
        (
            lambda c, _g, _t: c["artifacts"][0].update(approved_sha256="0" * 64),
            "approved digest differs",
        ),
        (
            lambda c, g, _t: (
                c["artifacts"][0]["approved_targets"].append("docs_catalog"),
                g["gates"][0]["approved_targets"].remove("python_package"),
            ),
            "not gate-authorized",
        ),
        (lambda _c, g, _t: g["gates"][0]["checks"].pop(), "checks differ"),
        (
            lambda _c, g, _t: g["gates"][0].update(review_route_id="route:NO.md#no"),
            "unknown gate review route",
        ),
    ],
)
def test_published_gate_failures(
    tmp_path: Path, mutation: Mutation, message: str
) -> None:
    root = _repo(tmp_path, lifecycle="published")
    _rewrite_documents(root, mutation, lifecycle="published")
    with pytest.raises(registry.RegistryError, match=message):
        registry.run(root, check=False)


def test_published_not_applicable_with_rationale_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path, lifecycle="published")

    def mutate(_c: JsonObject, gates: JsonObject, _t: JsonObject) -> None:
        gates["gates"][0]["checks"][0].update(
            status="not_applicable", rationale="Fixture has no submission format."
        )

    _rewrite_documents(root, mutate, lifecycle="published")
    registry.run(root, check=False, require_tags=True)


def test_hf_target_requires_catalogue_metadata_pass(tmp_path: Path) -> None:
    root = _repo(tmp_path, lifecycle="published")

    def mutate(c: JsonObject, gates: JsonObject, _t: JsonObject) -> None:
        c["artifacts"][0]["approved_targets"].append("hugging_face_raw")
        gates["gates"][0]["approved_targets"].append("hugging_face_raw")
        metadata = next(
            check
            for check in gates["gates"][0]["checks"]
            if check["name"] == "catalogue_hf_metadata"
        )
        metadata.update(status="not_applicable", rationale="No upload was planned.")

    _rewrite_documents(root, mutate, lifecycle="published")
    with pytest.raises(registry.RegistryError, match="HF targets require"):
        registry.run(root, check=False)
    gates = _load(root / registry.GATES_PATH)
    metadata = next(
        check
        for check in gates["gates"][0]["checks"]
        if check["name"] == "catalogue_hf_metadata"
    )
    metadata.update(status="pass", rationale=None)
    _write_json(root / registry.GATES_PATH, gates)
    registry.run(root, check=False)


def test_transition_evidence_routes_references_and_schema(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    benchmarks = {
        "sample-v1": {"id": "sample-v1"},
        "sample-v2": {"id": "sample-v2"},
    }
    artifacts = {
        "sample:payload": {
            "id": "sample:payload",
            "benchmark_id": "sample-v1",
        }
    }
    routes = registry.discover_routes(root)
    transition = {
        "id": "sample-transition",
        "benchmark_id": "sample-v1",
        "artifact_id": "sample:payload",
        "decision": "refreeze",
        "from_version": "1.0.0",
        "to_version": "1.0.0",
        "old_sha256": "0" * 64,
        "new_sha256": "1" * 64,
        "review_route_id": "route:GOLDEN_REVIEW.md#sample-review",
        "rationale": "Reviewed deterministic refreeze.",
    }
    registry._validate_transition_records(
        {"sample-transition": transition}, benchmarks, artifacts, routes
    )
    cases = (
        ({"rationale": "   "}, "needs rationale"),
        ({"review_route_id": "route:NO.md#missing"}, "unknown transition review"),
        ({"benchmark_id": "missing"}, "unknown transition benchmark"),
        ({"artifact_id": "missing"}, "unknown transition artifact"),
        ({"benchmark_id": "sample-v2"}, "unknown transition artifact"),
    )
    for changes, message in cases:
        changed = {**transition, **changes}
        with pytest.raises(registry.RegistryError, match=message):
            registry._validate_transition_records(
                {"sample-transition": changed}, benchmarks, artifacts, routes
            )

    supersede = {
        "id": "sample-supersede",
        "benchmark_id": "sample-v1",
        "decision": "supersede",
        "from_version": "1.0.0",
        "to_version": "1.0.0",
        "replacement_id": "sample-v2",
        "review_route_id": "route:GOLDEN_REVIEW.md#sample-review",
        "rationale": "Sample v2 replaces the published fixture.",
    }
    registry._validate_transition_records(
        {"sample-supersede": supersede}, benchmarks, artifacts, routes
    )
    document = {"schema_version": "1.0.0", "transitions": [supersede]}
    registry._validate_schema(root, registry.TRANSITIONS_SCHEMA, document)
    for changes, message in (
        ({"replacement_id": "sample-v1"}, "self replacement"),
        ({"replacement_id": "missing"}, "unknown transition replacement"),
    ):
        changed = {**supersede, **changes}
        with pytest.raises(registry.RegistryError, match=message):
            registry._validate_transition_records(
                {"sample-supersede": changed}, benchmarks, artifacts, routes
            )
    invalid = {
        "schema_version": "1.0.0",
        "transitions": [{**supersede, "artifact_id": "sample:payload"}],
    }
    with pytest.raises(registry.RegistryError, match="validation failed"):
        registry._validate_schema(root, registry.TRANSITIONS_SCHEMA, invalid)


def test_tags_release_prep_and_missing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry.run(root, check=False, require_tags=True)
    _git(root, "tag", "-d", "v0.1.0")
    registry.run(root, check=False, require_tags=True)
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n## [0.1.0] - 2026-01-01\n", encoding="utf-8"
    )
    _git(root, "add", "CHANGELOG.md")
    with pytest.raises(registry.RegistryError, match="missing release tag"):
        registry.run(root, check=False, require_tags=True)
    with pytest.raises(registry.RegistryError, match="gate: missing release tag"):
        registry.validate_tags(
            root,
            {"benchmarks": []},
            {"gates": [{"id": "gate", "release_tag": "v9.9.9"}]},
        )


def test_wheel_exact_inventory_missing_extra_and_python(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _, resolved = registry.run(root, check=False)
    expected = {
        "synthworld/benchmarks/sample.json": (
            root / "src/synthworld/benchmarks/sample.json"
        ).read_bytes(),
        "synthworld/benchmarks/SHA256SUMS": (
            root / "src/synthworld/benchmarks/SHA256SUMS"
        ).read_bytes(),
        "synthworld/benchmarks/__init__.py": b"",
    }

    def wheel(name: str, members: dict[str, bytes]) -> Path:
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as archive:
            for member, payload in members.items():
                archive.writestr(member, payload)
        return path

    registry.validate_wheel(wheel("valid.whl", expected), resolved)
    for name, members, message in (
        (
            "missing.whl",
            {
                key: value
                for key, value in expected.items()
                if not key.endswith("sample.json")
            },
            "inventory differs",
        ),
        (
            "extra.whl",
            {**expected, "synthworld/benchmarks/extra.json": b"x"},
            "inventory differs",
        ),
        (
            "python.whl",
            {**expected, "synthworld/benchmarks/extra.py": b""},
            "unexpected benchmark Python",
        ),
        (
            "changed.whl",
            {**expected, "synthworld/benchmarks/sample.json": b"changed\n"},
            "bytes differ",
        ),
    ):
        with pytest.raises(registry.RegistryError, match=message):
            registry.validate_wheel(wheel(name, members), resolved)
    duplicate = tmp_path / "duplicate.whl"
    with zipfile.ZipFile(duplicate, "w") as archive:
        for member, payload in expected.items():
            archive.writestr(member, payload)
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr(
                "synthworld/benchmarks/sample.json",
                expected["synthworld/benchmarks/sample.json"],
            )
    with pytest.raises(registry.RegistryError, match="duplicate members"):
        registry.validate_wheel(duplicate, resolved)
    with pytest.raises(registry.RegistryError, match="cannot read wheel"):
        registry.validate_wheel(tmp_path / "absent.whl", resolved)


def test_reproduction_contract_lifecycle_and_exact_argv(tmp_path: Path) -> None:
    root = _repo(tmp_path, lifecycle="published")
    curated, gates, transitions = _documents(root, lifecycle="published")
    benchmark = curated["benchmarks"][0]
    benchmark["reproduction"]["argv"][3] = "wrong-id"
    _write_json(root / registry.CURATED_PATH, curated)
    _write_json(root / registry.GATES_PATH, gates)
    _write_json(root / registry.TRANSITIONS_PATH, transitions)
    with pytest.raises(registry.RegistryError, match="exact reproduction argv"):
        registry.run(root, check=False)

    curated, gates, transitions = _documents(root)
    curated["benchmarks"][0]["reproduction"] = registry._expected_reproduction(
        "sample-v1"
    )
    _write_json(root / registry.CURATED_PATH, curated)
    _write_json(root / registry.GATES_PATH, gates)
    _write_json(root / registry.TRANSITIONS_PATH, transitions)
    with pytest.raises(registry.RegistryError, match="validation failed"):
        registry.run(root, check=False)


def test_reproduction_contract_remaining_lifecycle_branches() -> None:
    governed = {
        "id": "sample-v1",
        "lifecycle": "published",
        "reproduction": registry._expected_reproduction("sample-v1"),
        "example_command": "synthworld reproduce-benchmark",
    }
    with pytest.raises(registry.RegistryError, match="must omit example command"):
        registry._validate_reproduction_contract(governed)

    candidate = {
        "id": "sample-v1",
        "lifecycle": "candidate",
        "reproduction": registry._expected_reproduction("sample-v1"),
        "example_command": None,
    }
    with pytest.raises(registry.RegistryError, match="cannot claim reproduction"):
        registry._validate_reproduction_contract(candidate)


def _resolved_reproduction_fixture(root: Path) -> JsonObject:
    _, resolved = registry.run(root, check=False)
    return resolved


def _successful_reproduction_process(
    root: Path, calls: list[tuple[list[str], dict[str, object], bytes]]
) -> Callable[..., object]:
    class Process:
        returncode = 0
        stdout = b""
        stderr = b""

    def execute(command: list[str], **kwargs: object) -> Process:
        calls.append((command, kwargs, Path(command[5]).read_bytes()))
        output = Path(command[-1])
        output.mkdir()
        (output / "sample.json").write_bytes(
            (root / "src/synthworld/benchmarks/sample.json").read_bytes()
        )
        (output / "SHA256SUMS").write_bytes(
            (root / "src/synthworld/benchmarks/SHA256SUMS").read_bytes()
        )
        return Process()

    return execute


def test_snapshot_tree_records_directories_links_and_nonregular_entries(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    directory = root / "directory"
    directory.mkdir()
    regular = root / "regular"
    regular.write_bytes(b"content")
    (root / "directory-link").symlink_to(directory, target_is_directory=True)
    (root / "file-link").symlink_to(regular)
    os.mkfifo(root / "pipe")

    snapshot = registry._snapshot_tree(root)

    assert snapshot["directory/"] == ("directory", b"")
    assert snapshot["directory-link"][0] == "symlink"
    assert snapshot["file-link"][0] == "symlink"
    assert snapshot["regular"] == ("file", b"content")
    assert snapshot["pipe"] == ("nonregular", b"")


def test_collect_reproduction_output_rejects_invalid_roots_and_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    absent = tmp_path / "absent"
    with pytest.raises(registry.RegistryError, match="regular output directory"):
        registry._collect_reproduction_output(absent)

    target = tmp_path / "target"
    target.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(target, target_is_directory=True)
    with pytest.raises(registry.RegistryError, match="regular output directory"):
        registry._collect_reproduction_output(linked_root)

    output = tmp_path / "output"
    output.mkdir()
    (output / "directory-link").symlink_to(target, target_is_directory=True)
    with pytest.raises(registry.RegistryError, match="nonregular entry"):
        registry._collect_reproduction_output(output)

    claimed_directory = output / "claimed-directory"
    claimed_directory.write_bytes(b"not a directory")
    monkeypatch.setattr(
        os,
        "walk",
        lambda *_args, **_kwargs: [(str(output), [claimed_directory.name], [])],
    )
    with pytest.raises(registry.RegistryError, match="nonregular entry"):
        registry._collect_reproduction_output(output)


def test_collect_reproduction_output_rejects_nonregular_file(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    os.mkfifo(output / "pipe")
    with pytest.raises(registry.RegistryError, match="nonregular entry"):
        registry._collect_reproduction_output(output)


def test_collect_reproduction_output_continues_across_regular_directories(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    first = output / "first"
    second = output / "second"
    first.mkdir(parents=True)
    second.mkdir()
    (first / "one.json").write_bytes(b"one\n")
    (second / "two.json").write_bytes(b"two\n")

    assert registry._collect_reproduction_output(output) == {
        "first/one.json": b"one\n",
        "second/two.json": b"two\n",
    }


@pytest.mark.parametrize(
    ("path", "digest", "message"),
    [
        (None, "0" * 64, "no reproducible path"),
        ("outside/benchmark.json", "0" * 64, "no reproducible path"),
        (
            f"{registry.BENCHMARK_PREFIX}benchmark.json",
            None,
            "no approved digest",
        ),
    ],
)
def test_expected_reproduction_outputs_rejects_invalid_artifact_contracts(
    path: str | None, digest: str | None, message: str
) -> None:
    benchmark = {
        "id": "sample-v1",
        "artifacts": [{"path": path, "approved_sha256": digest}],
    }
    with pytest.raises(registry.RegistryError, match=message):
        registry._expected_reproduction_outputs(benchmark)


def test_expected_reproduction_outputs_rejects_case_collisions() -> None:
    benchmark = {
        "id": "sample-v1",
        "artifacts": [
            {
                "path": f"{registry.BENCHMARK_PREFIX}sample.json",
                "approved_sha256": "0" * 64,
            },
            {
                "path": f"{registry.BENCHMARK_PREFIX}Sample.json",
                "approved_sha256": "1" * 64,
            },
        ],
    }
    with pytest.raises(registry.RegistryError, match="case-colliding paths"):
        registry._expected_reproduction_outputs(benchmark)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (OSError("unavailable"), "cannot execute reproduction"),
        (subprocess.TimeoutExpired("uv", 120), "reproduction timed out"),
    ],
)
def test_reproduction_launch_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: OSError | subprocess.TimeoutExpired,
    message: str,
) -> None:
    benchmark = {
        "id": "sample-v1",
        "reproduction": registry._expected_reproduction("sample-v1"),
    }
    wheel = tmp_path / "fixture.whl"
    wheel.write_bytes(b"wheel")
    cwd = tmp_path / "work"
    cwd.mkdir()

    def fail(*_args: object, **_kwargs: object) -> NoReturn:
        raise error

    monkeypatch.setattr(registry, "_run_process", fail)
    with pytest.raises(registry.RegistryError, match=message):
        registry._run_reproduction(
            "/bin/uv", wheel, benchmark, tmp_path / "output", cwd
        )


def test_reproduction_skips_prepublication_benchmarks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    resolved = _resolved_reproduction_fixture(root)
    wheel = tmp_path / "fixture.whl"
    wheel.write_bytes(b"wheel")
    calls: list[object] = []
    monkeypatch.setattr(registry, "_find_executable", lambda _name: "/bin/uv")
    monkeypatch.setattr(
        registry,
        "_run_process",
        lambda *_args, **_kwargs: calls.append(object()),
    )

    registry.validate_reproduction(wheel, resolved, root)

    assert calls == []


def test_isolated_wheel_reproduction_command_and_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, lifecycle="published")
    resolved = _resolved_reproduction_fixture(root)
    wheel = tmp_path / "fixture.whl"
    wheel.write_bytes(b"wheel")
    calls: list[tuple[list[str], dict[str, object], bytes]] = []
    monkeypatch.setenv("PYTHONPATH", "forbidden")
    monkeypatch.setenv("PYTHONHOME", "forbidden")
    monkeypatch.setattr(registry, "_find_executable", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        registry, "_run_process", _successful_reproduction_process(root, calls)
    )

    registry.validate_reproduction(wheel, resolved, root)

    assert len(calls) == 2
    staged_wheels: set[Path] = set()
    for command, kwargs, staged_bytes in calls:
        assert command[:5] == [
            str(Path("/bin/uv").resolve()),
            "run",
            "--isolated",
            "--no-project",
            "--with",
        ]
        staged_wheel = Path(command[5])
        staged_wheels.add(staged_wheel)
        assert staged_wheel.is_absolute()
        assert staged_wheel != wheel.resolve()
        assert staged_wheel.name == wheel.name
        assert staged_bytes == wheel.read_bytes()
        assert command[6:11] == [
            "synthworld",
            "reproduce-benchmark",
            "--benchmark",
            "sample-v1",
            "--output",
        ]
        assert not Path(command[-1]).exists()
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == registry.REPRODUCTION_TIMEOUT_SECONDS
        assert kwargs["cwd"] == Path(command[-1]).parent
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert "PYTHONPATH" not in environment
        assert "PYTHONHOME" not in environment
    assert len(staged_wheels) == 1
    assert not next(iter(staged_wheels)).exists()


def test_reproduction_rejects_wheel_staging_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    resolved = _resolved_reproduction_fixture(root)
    wheel = tmp_path / "fixture.whl"
    wheel.write_bytes(b"wheel")
    monkeypatch.setattr(registry, "_find_executable", lambda _name: "/bin/uv")

    def fail_copy(*_args: object, **_kwargs: object) -> NoReturn:
        raise OSError("denied")

    monkeypatch.setattr(shutil, "copyfile", fail_copy)
    with pytest.raises(registry.RegistryError, match="cannot stage validated wheel"):
        registry.validate_reproduction(wheel, resolved, root)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("missing", "inventory differs"),
        ("extra", "inventory differs"),
        ("symlink", "nonregular entry"),
        ("case_collision", "case-colliding paths"),
        ("digest", "reproduced bytes differ"),
        ("nondeterministic", "not deterministic"),
    ],
)
def test_reproduction_rejects_unsafe_or_inexact_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    message: str,
) -> None:
    root = _repo(tmp_path, lifecycle="published")
    resolved = _resolved_reproduction_fixture(root)
    wheel = tmp_path / "fixture.whl"
    wheel.write_bytes(b"wheel")
    calls = 0

    class Process:
        returncode = 0
        stdout = b""
        stderr = b""

    def execute(command: list[str], **_kwargs: object) -> Process:
        nonlocal calls
        calls += 1
        output = Path(command[-1])
        output.mkdir()
        payload = (root / "src/synthworld/benchmarks/sample.json").read_bytes()
        checksums = (root / "src/synthworld/benchmarks/SHA256SUMS").read_bytes()
        if failure != "missing":
            (output / "sample.json").write_bytes(
                b"different\n" if failure in {"digest", "nondeterministic"} else payload
            )
        (output / "SHA256SUMS").write_bytes(checksums)
        if failure == "extra":
            (output / "extra.json").write_bytes(b"{}\n")
        elif failure == "symlink":
            (output / "link.json").symlink_to(output / "sample.json")
        elif failure == "case_collision":
            (output / "Sample.json").write_bytes(payload)
        elif failure == "nondeterministic" and calls == 1:
            (output / "sample.json").write_bytes(payload)
        return Process()

    monkeypatch.setattr(registry, "_find_executable", lambda _name: "/bin/uv")
    monkeypatch.setattr(registry, "_run_process", execute)
    with pytest.raises(registry.RegistryError, match=message):
        registry.validate_reproduction(wheel, resolved, root)


def test_reproduction_process_failures_uv_and_source_immutability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, lifecycle="published")
    resolved = _resolved_reproduction_fixture(root)
    wheel = tmp_path / "fixture.whl"
    wheel.write_bytes(b"wheel")
    monkeypatch.setattr(registry, "_find_executable", lambda _name: None)
    with pytest.raises(registry.RegistryError, match="uv executable is unavailable"):
        registry.validate_reproduction(wheel, resolved, root)

    monkeypatch.setattr(registry, "_find_executable", lambda _name: "/bin/uv")

    class Failed:
        returncode = 2
        stdout = b""
        stderr = b"bad command"

    monkeypatch.setattr(registry, "_run_process", lambda *_args, **_kwargs: Failed())
    with pytest.raises(
        registry.RegistryError, match="reproduction failed: bad command"
    ):
        registry.validate_reproduction(wheel, resolved, root)

    def timeout(*_args: object, **_kwargs: object) -> NoReturn:
        raise subprocess.TimeoutExpired("uv", 120)

    monkeypatch.setattr(registry, "_run_process", timeout)
    with pytest.raises(registry.RegistryError, match="reproduction timed out"):
        registry.validate_reproduction(wheel, resolved, root)

    def modify_source(*_args: object, **_kwargs: object) -> NoReturn:
        (root / "src/synthworld/benchmarks/sample.json").write_bytes(b"modified\n")
        raise OSError("failed")

    monkeypatch.setattr(registry, "_run_process", modify_source)
    with pytest.raises(registry.RegistryError, match="modified source benchmark"):
        registry.validate_reproduction(wheel, resolved, root)


def test_check_reproduction_cli_implies_wheel_and_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, lifecycle="published")
    registry.run(root, check=False)
    wheel = tmp_path / "fixture.whl"
    wheel.write_bytes(b"wheel")
    calls: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        registry,
        "validate_wheel",
        lambda path, _resolved: calls.append(("wheel", path)),
    )
    monkeypatch.setattr(
        registry,
        "validate_reproduction",
        lambda path, _resolved, _root: calls.append(("reproduction", path)),
    )
    assert registry.main(["--root", str(root), "--check-reproduction", str(wheel)]) == 0
    assert calls == [("wheel", wheel), ("reproduction", wheel)]


def test_base_bootstrap_incomplete_demotion_and_transition(tmp_path: Path) -> None:
    root = _repo(tmp_path, lifecycle="published")
    registry.validate_base_transition(
        root, "HEAD", {"benchmarks": []}, {"transitions": []}
    )
    with pytest.raises(registry.RegistryError, match="git rev-parse"):
        registry.validate_base_transition(
            root, "missing-ref", {"benchmarks": []}, {"transitions": []}
        )
    registry.run(root, check=False)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "registry")
    base = "HEAD"

    payload = root / "src/synthworld/benchmarks/sample.json"
    payload.write_bytes(b'{"synthetic":true,"version":2}\n')
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    checksum = root / "src/synthworld/benchmarks/SHA256SUMS"
    checksum.write_text(f"{digest}  sample.json\n", encoding="ascii")
    curated, gates, transitions = _documents(root, lifecycle="published")
    _write_json(root / registry.CURATED_PATH, curated)
    _write_json(root / registry.GATES_PATH, gates)
    _write_json(root / registry.TRANSITIONS_PATH, transitions)
    _git(root, "add", "src/synthworld/benchmarks")
    with pytest.raises(registry.RegistryError, match="needs exact refreeze"):
        registry.run(root, check=False, base_ref=base)
    old = _load(root / registry.RESOLVED_PATH)["benchmarks"][0]["artifacts"]
    old_by_id = {item["id"]: item["approved_sha256"] for item in old}
    transitions["transitions"] = [
        {
            "id": f"transition-{artifact['id']}",
            "benchmark_id": "sample-v1",
            "artifact_id": artifact["id"],
            "decision": "refreeze",
            "from_version": "1.0.0",
            "to_version": "1.0.0",
            "old_sha256": old_by_id[artifact["id"]],
            "new_sha256": artifact["approved_sha256"],
            "review_route_id": "route:GOLDEN_REVIEW.md#sample-review",
            "rationale": "Reviewed deterministic refreeze.",
        }
        for artifact in curated["artifacts"]
    ]
    _write_json(root / registry.TRANSITIONS_PATH, transitions)
    registry.run(root, check=False, base_ref=base)

    curated["benchmarks"][0].update(
        lifecycle="candidate",
        publication_gate_id=None,
        reproduction=None,
        example_command="synthworld generate",
    )
    for artifact in curated["artifacts"]:
        artifact["frozen"] = False
    _write_json(root / registry.CURATED_PATH, curated)
    gates["gates"] = []
    _write_json(root / registry.GATES_PATH, gates)
    with pytest.raises(registry.RegistryError, match="cannot be demoted"):
        registry.run(root, check=False, base_ref=base)


def test_base_version_transition_and_superseded_immutability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_artifact = {"id": "a", "frozen": True, "approved_sha256": "0" * 64}
    old = {
        "benchmarks": [
            {
                "id": "b",
                "lifecycle": "published",
                "benchmark_version": "1.0.0",
                "artifacts": [old_artifact],
            }
        ]
    }
    new_artifact = {"id": "a", "frozen": True, "approved_sha256": "1" * 64}
    new = {
        "benchmarks": [
            {
                "id": "b",
                "lifecycle": "published",
                "benchmark_version": "2.0.0",
                "artifacts": [new_artifact],
            }
        ]
    }
    monkeypatch.setattr(registry, "_load_base_registry", lambda *_args: (old, {}))
    transition = {
        "transitions": [
            {
                "benchmark_id": "b",
                "artifact_id": "a",
                "decision": "version_transition",
                "from_version": "1.0.0",
                "to_version": "2.0.0",
                "old_sha256": "0" * 64,
                "new_sha256": "1" * 64,
            }
        ]
    }
    registry.validate_base_transition(tmp_path, "HEAD", new, transition)
    new["benchmarks"][0].update(lifecycle="superseded", replacement_id="replacement")
    with pytest.raises(registry.RegistryError, match="exact governance"):
        registry.validate_base_transition(tmp_path, "HEAD", new, transition)
    transition["transitions"].append(
        {
            "benchmark_id": "b",
            "decision": "supersede",
            "from_version": "1.0.0",
            "to_version": "2.0.0",
            "replacement_id": "replacement",
        }
    )
    registry.validate_base_transition(tmp_path, "HEAD", new, transition)
    old["benchmarks"][0]["lifecycle"] = "candidate"
    with pytest.raises(registry.RegistryError, match="only a published"):
        registry.validate_base_transition(tmp_path, "HEAD", new, transition)
    old["benchmarks"][0]["lifecycle"] = "published"
    old["benchmarks"][0]["lifecycle"] = "superseded"
    with pytest.raises(
        registry.RegistryError, match="superseded benchmark is immutable"
    ):
        registry.validate_base_transition(tmp_path, "HEAD", new, transition)


def test_base_comparison_remaining_structural_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = {"id": "a", "frozen": True, "approved_sha256": "0" * 64}
    base: JsonObject = {
        "benchmarks": [
            {
                "id": "b",
                "lifecycle": "published",
                "benchmark_version": "1.0.0",
                "artifacts": [artifact],
            }
        ]
    }
    same = copy.deepcopy(base)

    monkeypatch.setattr(registry, "_load_base_registry", lambda *_args: (base, None))
    with pytest.raises(registry.RegistryError, match="base registry is incomplete"):
        registry.validate_base_transition(tmp_path, "HEAD", same, {"transitions": []})

    monkeypatch.setattr(registry, "_load_base_registry", lambda *_args: (base, {}))
    with pytest.raises(registry.RegistryError, match="base benchmark removed"):
        registry.validate_base_transition(
            tmp_path, "HEAD", {"benchmarks": []}, {"transitions": []}
        )
    removed = copy.deepcopy(same)
    removed["benchmarks"][0]["artifacts"] = []
    with pytest.raises(registry.RegistryError, match="frozen artifact removed"):
        registry.validate_base_transition(
            tmp_path, "HEAD", removed, {"transitions": []}
        )
    added = copy.deepcopy(same)
    added["benchmarks"][0]["artifacts"].append(
        {"id": "new", "frozen": False, "approved_sha256": "1" * 64}
    )
    with pytest.raises(registry.RegistryError, match="frozen benchmark artifact added"):
        registry.validate_base_transition(tmp_path, "HEAD", added, {"transitions": []})
    registry.validate_base_transition(tmp_path, "HEAD", same, {"transitions": []})
    base["benchmarks"][0]["artifacts"][0]["frozen"] = False
    registry.validate_base_transition(tmp_path, "HEAD", same, {"transitions": []})


def test_base_transition_rejects_frozen_state_regression_for_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base: JsonObject = {
        "benchmarks": [
            {
                "id": "candidate",
                "lifecycle": "candidate",
                "benchmark_version": "1.0.0",
                "artifacts": [
                    {"id": "frozen", "frozen": True, "approved_sha256": "0" * 64}
                ],
            }
        ]
    }
    current = copy.deepcopy(base)
    current["benchmarks"][0]["artifacts"][0]["frozen"] = False
    monkeypatch.setattr(registry, "_load_base_registry", lambda *_args: (base, {}))

    with pytest.raises(
        registry.RegistryError, match="frozen artifact cannot be unfrozen"
    ):
        registry.validate_base_transition(
            tmp_path, "HEAD", current, {"transitions": []}
        )


def test_candidate_frozen_artifact_rejects_stale_approved_digest(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)

    def mutate(
        curated: JsonObject, _gates: JsonObject, _transitions: JsonObject
    ) -> None:
        artifact = curated["artifacts"][0]
        artifact["frozen"] = True
        artifact["approved_sha256"] = "0" * 64

    _rewrite_documents(root, mutate)

    with pytest.raises(
        registry.RegistryError, match="sample:payload: approved digest differs"
    ):
        registry.run(root, check=False)


def test_base_transition_rejects_newly_introduced_superseded_benchmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base: JsonObject = {"benchmarks": []}
    current: JsonObject = {
        "benchmarks": [
            {
                "id": "invalid-history",
                "lifecycle": "superseded",
                "benchmark_version": "1.0.0",
                "artifacts": [],
            }
        ]
    }
    monkeypatch.setattr(registry, "_load_base_registry", lambda *_args: (base, {}))

    with pytest.raises(
        registry.RegistryError,
        match="newly introduced benchmark cannot be superseded",
    ):
        registry.validate_base_transition(
            tmp_path, "HEAD", current, {"transitions": []}
        )


def test_base_loader_fails_closed_for_unreadable_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)

    def non_utf8(_root: Path, arguments: tuple[str, ...]) -> bytes:
        if arguments[0] == "rev-parse":
            return b"0" * 40 + b"\n"
        return b"\xff"

    monkeypatch.setattr(registry, "_git", non_utf8)
    with pytest.raises(registry.RegistryError, match="non-UTF-8 base registry"):
        registry._load_base_registry(root, "HEAD")

    def unreadable(_root: Path, arguments: tuple[str, ...]) -> bytes:
        if arguments[0] == "rev-parse":
            return b"0" * 40 + b"\n"
        if arguments[0] == "ls-tree":
            return (
                registry.RESOLVED_PATH.as_posix()
                + "\0"
                + registry.GENERATED_PATH.as_posix()
                + "\0"
            ).encode()
        raise registry.RegistryError("base object is unreadable")

    monkeypatch.setattr(registry, "_git", unreadable)
    with pytest.raises(registry.RegistryError, match="base object is unreadable"):
        registry._load_base_registry(root, "HEAD")


def test_run_wheel_and_output_io_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    registry.run(root, check=False)
    wheel = tmp_path / "valid.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("synthworld/benchmarks/__init__.py", b"")
        archive.writestr(
            "synthworld/benchmarks/sample.json",
            (root / "src/synthworld/benchmarks/sample.json").read_bytes(),
        )
        archive.writestr(
            "synthworld/benchmarks/SHA256SUMS",
            (root / "src/synthworld/benchmarks/SHA256SUMS").read_bytes(),
        )
    registry.run(root, check=True, wheel=wheel)
    (root / registry.RESOLVED_PATH).unlink()
    with pytest.raises(
        registry.RegistryError, match=r"cannot read docs/_data/benchmarks.resolved"
    ):
        registry.run(root, check=True)

    original = Path.write_bytes

    def fail_input(path: Path, payload: bytes) -> int:
        if path == root / registry.CURATED_PATH:
            raise OSError("denied")
        return original(path, payload)

    monkeypatch.setattr(Path, "write_bytes", fail_input)
    with pytest.raises(
        registry.RegistryError, match=r"cannot write docs/_data/benchmarks.curated"
    ):
        registry.run(root, check=False)
    monkeypatch.undo()
    registry.run(root, check=False)

    def fail_output(path: Path, payload: bytes) -> int:
        if path == root / registry.GENERATED_PATH:
            raise OSError("denied")
        return original(path, payload)

    monkeypatch.setattr(Path, "write_bytes", fail_output)
    with pytest.raises(
        registry.RegistryError, match=r"cannot write docs/_data/benchmarks.generated"
    ):
        registry.run(root, check=False)


def test_git_and_file_failures_are_concise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Process:
        returncode = 1
        stdout = b""
        stderr = b"failure\n"

    commands: list[list[str]] = []

    def failed_process(command: list[str], **_kwargs: object) -> Process:
        commands.append(command)
        return Process()

    monkeypatch.setattr(registry, "_find_executable", lambda _name: "/portable/bin/git")
    monkeypatch.setattr(registry, "_run_process", failed_process)
    with pytest.raises(registry.RegistryError, match=r"git .* failed: failure"):
        registry.tracked_paths(tmp_path)
    assert commands == [
        [
            str(Path("/portable/bin/git").resolve()),
            "-C",
            str(tmp_path),
            "ls-files",
            "-z",
        ]
    ]

    def broken(*_args: object, **_kwargs: object) -> NoReturn:
        raise OSError("missing")

    monkeypatch.setattr(registry, "_run_process", broken)
    with pytest.raises(registry.RegistryError, match="cannot execute git"):
        registry.tracked_paths(tmp_path)
    monkeypatch.setattr(registry, "_find_executable", lambda _name: None)
    with pytest.raises(registry.RegistryError, match="git executable is unavailable"):
        registry.tracked_paths(tmp_path)


def test_path_independent_and_untracked_invariant(tmp_path: Path) -> None:
    first = _repo(tmp_path / "one")
    second = _repo(tmp_path / "two")
    (first / "src/synthworld/benchmarks/untracked.json").write_text("{}\n")
    assert registry.discover_generated(first) == registry.discover_generated(second)
