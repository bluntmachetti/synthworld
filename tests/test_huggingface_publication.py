from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools import check_huggingface_publication as publication

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "huggingface/publication-manifest.json"
SCHEMA = ROOT / "huggingface/publication-manifest.schema.json"
REGISTRY = ROOT / "docs/_data/benchmarks.resolved.json"
REGISTRY_SCHEMA = ROOT / "docs/_schemas/benchmarks-resolved.schema.json"
CARD = ROOT / "huggingface/README.md"


def _approved_hf_gate(benchmark_id: str, target: str) -> dict[str, object]:
    return {
        "approved_targets": [target],
        "benchmark_id": benchmark_id,
        "benchmark_version": "1.0.0",
        "checks": [
            {"name": name, "status": "pass"}
            for name in sorted(publication.REQUIRED_HF_CHECKS)
        ],
        "decision": "approved",
        "id": f"{benchmark_id}-1.0.0",
    }


def _complete_registry(registry: dict[str, Any]) -> dict[str, Any]:
    for benchmark in registry["benchmarks"]:
        artifacts = benchmark.get("artifacts", [])
        benchmark.setdefault(
            "artifact_ids", [artifact.get("id") for artifact in artifacts]
        )
        benchmark.setdefault(
            "publication_gate_id",
            (
                f"{benchmark['id']}-{benchmark['benchmark_version']}"
                if benchmark.get("publication_gate") is not None
                else None
            ),
        )
        for artifact in artifacts:
            artifact.setdefault("benchmark_id", benchmark["id"])
            if set(artifact.get("approved_targets", [])) & publication.HF_TARGETS:
                artifact.setdefault("hf_destination_path", artifact.get("path"))
    return registry


def _manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return manifest


def _write_json(path: Path, value: object) -> None:
    path.write_text(publication.canonical_json(value), encoding="utf-8", newline="\n")


def _validate(manifest_path: Path) -> dict[str, Any]:
    return publication.validate_publication(
        manifest_path,
        SCHEMA,
        REGISTRY,
        REGISTRY_SCHEMA,
        CARD,
        ROOT,
    )


def _remote_baseline(
    files: Sequence[object],
    **overrides: object,
) -> dict[str, object]:
    valid_files = [item for item in files if isinstance(item, dict)]
    baseline: dict[str, object] = {
        "deletion_policy": "none",
        "file_count": len(files),
        "files": files,
        "hub_commit_sha": "a" * 40,
        "total_bytes": sum(
            item.get("size_bytes", 0)
            for item in valid_files
            if type(item.get("size_bytes")) is int
        ),
    }
    baseline.update(overrides)
    return baseline


def _remote_file(path: object = "frozen/sample.json") -> dict[str, object]:
    return {"path": path, "sha256": "b" * 64, "size_bytes": 7}


def test_repository_manifest_derives_bounded_dry_run_operations() -> None:
    plan = _validate(MANIFEST)

    assert plan["dataset_repository"] == "Bluntmachetti7/synthworld-benchmarks"
    assert plan["remote_parent_commit"] == ("54a7d1e89f683ade507c3518b3e0c0bfddfbe528")
    assert plan["deletion_policy"] == "none"
    assert plan["network_access"] is False
    assert plan["upload_enabled"] is False
    assert plan["status"] == "ready_for_protected_dry_run"
    assert len(plan["operations"]) == 9
    assert {operation["benchmark_id"] for operation in plan["operations"]} == {
        "ambiguity-v1",
        "authority-governance-v1",
    }
    assert all(
        operation["remote_precondition"] == {"sha256": None, "status": "absent"}
        for operation in plan["operations"]
    )
    assert plan["card_operation"]["remote_precondition"]["status"] == "match"
    assert plan["prohibited_benchmark_ids"] == [
        "asteria-agentic-c08-v2",
        "enterprise-agentic-c08-v2",
    ]
    assert {
        operation["destination_path"]
        for operation in plan["operations"]
        if operation["benchmark_id"] == "ambiguity-v1"
    } == {
        "frozen/ambiguity-v1/SHA256SUMS",
        "frozen/ambiguity-v1/ambiguity-dispositions-v1.json",
        "frozen/ambiguity-v1/ambiguity-memberships-v1.json",
        "frozen/ambiguity-v1/ambiguity-public-v1.json",
    }


def _checksum_operations(
    tmp_path: Path,
    *,
    content: str,
    payload_destination: str = "frozen/sample/payload.json",
    payload_sha256: str = "a" * 64,
    include_extra: bool = False,
) -> list[dict[str, Any]]:
    checksum = tmp_path / "SHA256SUMS"
    checksum.write_text(content, encoding="utf-8", newline="\n")
    operations: list[dict[str, Any]] = [
        {
            "artifact_id": "sample:checksum",
            "artifact_kind": "checksum_manifest",
            "benchmark_id": "sample",
            "destination_path": "frozen/sample/SHA256SUMS",
            "source_path": "SHA256SUMS",
            "target": "hugging_face_raw",
        },
        {
            "artifact_kind": "public_input",
            "benchmark_id": "sample",
            "destination_path": payload_destination,
            "sha256": payload_sha256,
            "target": "hugging_face_raw",
        },
    ]
    if include_extra:
        operations.append(
            {
                "artifact_kind": "evaluator_truth",
                "benchmark_id": "sample",
                "destination_path": "frozen/sample/extra.json",
                "sha256": "b" * 64,
                "target": "hugging_face_raw",
            }
        )
    return operations


def test_checksum_destinations_bind_relative_inventory(tmp_path: Path) -> None:
    operations = _checksum_operations(tmp_path, content=f"{'a' * 64}  payload.json\n")

    publication._validate_checksum_destinations(operations, tmp_path)


@pytest.mark.parametrize(
    ("content", "payload_destination", "payload_sha256", "include_extra", "message"),
    [
        ("", "frozen/sample/payload.json", "a" * 64, False, "manifest is empty"),
        (
            "invalid\n",
            "frozen/sample/payload.json",
            "a" * 64,
            False,
            "invalid checksum line",
        ),
        (
            f"{'a' * 64}  payload.json\n{'a' * 64}  payload.json\n",
            "frozen/sample/payload.json",
            "a" * 64,
            False,
            "duplicate checksum path",
        ),
        (
            f"{'a' * 64}  payload.json\n",
            "frozen/sample/renamed.json",
            "a" * 64,
            False,
            "does not bind an authorized artifact",
        ),
        (
            f"{'a' * 64}  payload.json\n",
            "frozen/sample/payload.json",
            "b" * 64,
            False,
            "does not bind an authorized artifact",
        ),
        (
            f"{'a' * 64}  payload.json\n",
            "frozen/sample/payload.json",
            "a" * 64,
            True,
            "inventory differs",
        ),
    ],
)
def test_checksum_destinations_reject_broken_projection(
    tmp_path: Path,
    content: str,
    payload_destination: str,
    payload_sha256: str,
    include_extra: bool,
    message: str,
) -> None:
    operations = _checksum_operations(
        tmp_path,
        content=content,
        payload_destination=payload_destination,
        payload_sha256=payload_sha256,
        include_extra=include_extra,
    )

    with pytest.raises(publication.PublicationError, match=message):
        publication._validate_checksum_destinations(operations, tmp_path)


def test_content_type_supports_jsonl_and_rejects_unknown_suffix() -> None:
    assert publication._content_type(Path("sample.jsonl")) == "application/x-ndjson"
    with pytest.raises(publication.PublicationError, match="unsupported"):
        publication._content_type(Path("sample.csv"))


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("frozen/cafe\u0301.json", "NFC-normalized"),
        ("README.md", "reserved for the dataset card"),
        ("frozen/bad name.json", "forbidden characters"),
        ("frozen//sample.json", "not canonical"),
        ("frozen/../sample.json", "reserved segment"),
        ("frozen/.hidden/sample.json", "reserved segment"),
        ("frozen/trailing./sample.json", "reserved segment"),
        ("frozen/CON/sample.json", "reserved segment"),
    ],
)
def test_destination_path_rejects_noncanonical_or_reserved_forms(
    path: str,
    message: str,
) -> None:
    with pytest.raises(publication.PublicationError, match=message):
        publication._validate_destination_path(path)


def test_remote_baseline_requires_an_array() -> None:
    with pytest.raises(publication.PublicationError, match="files must be an array"):
        publication._remote_file_map({"files": "invalid"})


@pytest.mark.parametrize(
    "record",
    [
        None,
        {"path": "frozen/sample.json"},
        _remote_file(path=1),
        {**_remote_file(), "sha256": 1},
        {**_remote_file(), "sha256": "invalid"},
        {**_remote_file(), "size_bytes": "7"},
        {**_remote_file(), "size_bytes": True},
        {**_remote_file(), "size_bytes": -1},
    ],
)
def test_remote_baseline_rejects_malformed_file_records(record: object) -> None:
    with pytest.raises(publication.PublicationError, match="malformed file record"):
        publication._remote_file_map(_remote_baseline([record]))


def test_remote_baseline_rejects_case_collisions_and_noncanonical_order() -> None:
    collision = [_remote_file("frozen/A.json"), _remote_file("frozen/a.json")]
    with pytest.raises(publication.PublicationError, match="path collision"):
        publication._remote_file_map(_remote_baseline(collision))

    unordered = [_remote_file("frozen/b.json"), _remote_file("frozen/a.json")]
    with pytest.raises(publication.PublicationError, match="canonically ordered"):
        publication._remote_file_map(_remote_baseline(unordered))


@pytest.mark.parametrize(
    "overrides",
    [
        {"deletion_policy": "replace"},
        {"hub_commit_sha": None},
        {"hub_commit_sha": "invalid"},
        {"file_count": 2},
        {"total_bytes": 8},
    ],
)
def test_remote_baseline_rejects_invalid_summary_or_policy(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(publication.PublicationError, match="summary or policy"):
        publication._remote_file_map(_remote_baseline([_remote_file()], **overrides))


def test_destination_inventory_allows_exact_remote_replacement() -> None:
    remote = {"frozen/sample.json": _remote_file()}
    publication._validate_destination_inventory(
        [{"destination_path": "frozen/sample.json"}], remote
    )


def test_destination_inventory_rejects_operation_and_remote_case_collisions() -> None:
    with pytest.raises(publication.PublicationError, match="destination collision"):
        publication._validate_destination_inventory(
            [
                {"destination_path": "frozen/sample.json"},
                {"destination_path": "FROZEN/SAMPLE.JSON"},
            ],
            {},
        )

    with pytest.raises(
        publication.PublicationError, match="remote path case collision"
    ):
        publication._validate_destination_inventory(
            [{"destination_path": "FROZEN/SAMPLE.JSON"}],
            {"frozen/sample.json": _remote_file()},
        )


@pytest.mark.parametrize(
    ("destination", "remote_path"),
    [
        ("frozen/existing/child.json", "frozen/existing"),
        ("frozen/existing", "frozen/existing/child.json"),
    ],
)
def test_destination_inventory_rejects_file_directory_collisions(
    destination: str,
    remote_path: str,
) -> None:
    with pytest.raises(publication.PublicationError, match="file/directory collision"):
        publication._validate_destination_inventory(
            [{"destination_path": destination}],
            {remote_path: _remote_file(remote_path)},
        )


@pytest.mark.parametrize("content", ["[]\n", "not-json\n"])
def test_load_json_object_rejects_non_objects_and_invalid_json(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "input.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(publication.PublicationError):
        publication.load_json_object(path, "fixture")


def test_load_json_object_normalizes_missing_file() -> None:
    with pytest.raises(publication.PublicationError):
        publication.load_json_object(Path("does-not-exist.json"), "fixture")


def test_validate_schema_reports_first_error() -> None:
    with pytest.raises(publication.PublicationError, match="schema error"):
        publication.validate_schema({}, {"required": ["value"]}, "fixture")


def test_validate_schema_rejects_invalid_schema() -> None:
    with pytest.raises(publication.PublicationError, match="invalid JSON schema"):
        publication.validate_schema({}, {"type": "invalid"}, "fixture")


@pytest.mark.parametrize(
    "content",
    [
        "no frontmatter\n",
        "---\nconfigs: [\n---\nbody\n",
        "---\nconfigs: invalid\n---\nbody\n",
        "---\nnull\n---\nbody\n",
        "---\nconfigs:\n- invalid\n---\nbody\n",
        (
            "---\nconfigs:\n- config_name: sample\n"
            "  data_files: []\n  extra: true\n---\nbody\n"
        ),
        (
            "---\nconfigs:\n- config_name: sample\n"
            "  data_files: []\n  default: 'false'\n---\nbody\n"
        ),
        "---\nconfigs:\n- config_name: 1\n  data_files: []\n---\nbody\n",
        (
            "---\nconfigs:\n- config_name: sample\n  data_files:\n"
            "  - path: sample.json\n---\nbody\n"
        ),
        "---\nconfigs:\n- config_name: sample\n  data_files:\n  - invalid\n---\nbody\n",
    ],
)
def test_card_config_parser_rejects_invalid_frontmatter(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "README.md"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(publication.PublicationError):
        publication.read_card_configs(path)


def test_card_config_parser_normalizes_missing_file() -> None:
    with pytest.raises(publication.PublicationError):
        publication.read_card_configs(Path("missing-card.md"))


def test_registry_target_intersection_requires_gate_and_artifact_approval(
    tmp_path: Path,
) -> None:
    source = tmp_path / "frozen/sample.json"
    source.parent.mkdir()
    source.write_bytes(b"sample\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    registry = {
        "benchmarks": [
            {
                "artifacts": [
                    {
                        "answer_key_label": None,
                        "approved_sha256": digest,
                        "approved_targets": [
                            "hugging_face_raw",
                            "hugging_face_viewer",
                        ],
                        "id": "sample:public",
                        "kind": "public_input",
                        "path": "frozen/sample.json",
                        "sensitivity": "public_input",
                    }
                ],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": _approved_hf_gate("sample", "hugging_face_raw"),
            },
            {
                "artifacts": [],
                "benchmark_version": "1.0.0",
                "id": "candidate",
                "lifecycle": "candidate",
                "publication_gate": None,
            },
        ]
    }

    operations, benchmarks, summary = publication.derive_registry_state(
        _complete_registry(registry),
        tmp_path,
    )

    assert operations == [
        {
            "answer_key_label": None,
            "artifact_id": "sample:public",
            "artifact_kind": "public_input",
            "benchmark_id": "sample",
            "benchmark_version": "1.0.0",
            "content_type": "application/json",
            "destination_path": "frozen/sample.json",
            "remote_precondition": {"sha256": None, "status": "absent"},
            "sha256": digest,
            "sensitivity": "public_input",
            "size_bytes": 7,
            "source_path": "frozen/sample.json",
            "target": "hugging_face_raw",
        }
    ]
    assert benchmarks == [
        {
            "benchmark_id": "sample",
            "benchmark_version": "1.0.0",
            "targets": ["hugging_face_raw"],
        }
    ]
    assert summary == {
        "candidate": 1,
        "hf_authorized_artifacts": 1,
        "published": 1,
        "total": 2,
    }


def test_registry_ignores_valid_non_hf_gate_targets() -> None:
    registry = _complete_registry(
        {
            "benchmarks": [
                {
                    "artifacts": [],
                    "benchmark_version": "1.0.0",
                    "id": "sample",
                    "lifecycle": "candidate",
                    "publication_gate": {"approved_targets": ["repository"]},
                }
            ]
        }
    )

    operations, benchmarks, summary = publication.derive_registry_state(registry, ROOT)

    assert operations == []
    assert benchmarks == []
    assert summary == {
        "candidate": 1,
        "hf_authorized_artifacts": 0,
        "published": 0,
        "total": 1,
    }


def test_registry_rejects_hf_gate_for_candidate_lifecycle() -> None:
    registry = _complete_registry(
        {
            "benchmarks": [
                {
                    "artifacts": [],
                    "benchmark_version": "1.0.0",
                    "id": "sample",
                    "lifecycle": "candidate",
                    "publication_gate": _approved_hf_gate("sample", "hugging_face_raw"),
                }
            ]
        }
    )

    with pytest.raises(publication.PublicationError, match="published lifecycle"):
        publication.derive_registry_state(registry, ROOT)


def test_registry_rejects_duplicate_benchmark_identity() -> None:
    registry = _complete_registry(
        {
            "benchmarks": [
                {
                    "artifacts": [],
                    "benchmark_version": "1.0.0",
                    "id": "sample",
                    "lifecycle": "candidate",
                    "publication_gate": None,
                },
                {
                    "artifacts": [],
                    "benchmark_version": "1.0.0",
                    "id": "sample",
                    "lifecycle": "published",
                    "publication_gate": None,
                },
            ]
        }
    )

    with pytest.raises(
        publication.PublicationError, match="duplicate benchmark identity"
    ):
        publication.derive_registry_state(registry, ROOT)


def test_registry_rejects_invalid_benchmark_inventory() -> None:
    with pytest.raises(
        publication.PublicationError, match="benchmarks must be an array"
    ):
        publication.derive_registry_state({"benchmarks": "invalid"}, ROOT)


@pytest.mark.parametrize(
    "artifact",
    [
        {
            "answer_key_label": None,
            "approved_sha256": None,
            "approved_targets": ["hugging_face_raw"],
            "id": "sample:missing-digest",
            "kind": "public_input",
            "path": "sample.json",
            "sensitivity": "public_input",
        },
        {
            "answer_key_label": None,
            "approved_sha256": "a" * 64,
            "approved_targets": ["hugging_face_raw"],
            "id": "sample:missing-path",
            "kind": "public_input",
            "path": None,
            "sensitivity": "public_input",
        },
    ],
)
def test_registry_rejects_incomplete_authorized_artifact(
    tmp_path: Path,
    artifact: dict[str, object],
) -> None:
    registry = {
        "benchmarks": [
            {
                "artifacts": [artifact],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": _approved_hf_gate("sample", "hugging_face_raw"),
            }
        ]
    }

    with pytest.raises(
        publication.PublicationError,
        match="require a source path, destination path, and digest",
    ):
        publication.derive_registry_state(
            _complete_registry(registry),
            tmp_path,
        )


def test_registry_normalizes_malformed_entries() -> None:
    with pytest.raises(publication.PublicationError, match="malformed benchmark entry"):
        publication.derive_registry_state({"benchmarks": [{}]}, ROOT)


def test_registry_rejects_non_dict_benchmark() -> None:
    with pytest.raises(publication.PublicationError, match="malformed benchmark entry"):
        publication.derive_registry_state({"benchmarks": [None]}, ROOT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 1),
        ("benchmark_version", 1),
        ("artifact_ids", [1]),
        ("artifact_ids", ["sample", "sample"]),
        ("lifecycle", 1),
        ("artifacts", {}),
        ("publication_gate_id", 1),
    ],
)
def test_registry_rejects_invalid_benchmark_field_types(
    field: str,
    value: object,
) -> None:
    benchmark: dict[str, object] = {
        "artifact_ids": [],
        "artifacts": [],
        "benchmark_version": "1.0.0",
        "id": "sample",
        "lifecycle": "candidate",
        "publication_gate": None,
        "publication_gate_id": None,
    }
    benchmark[field] = value

    with pytest.raises(publication.PublicationError, match="malformed benchmark entry"):
        publication.derive_registry_state({"benchmarks": [benchmark]}, ROOT)


def test_registry_rejects_non_dict_gate() -> None:
    registry = {
        "benchmarks": [
            {
                "artifact_ids": [],
                "artifacts": [],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "candidate",
                "publication_gate": [],
                "publication_gate_id": "sample-1.0.0",
            }
        ]
    }

    with pytest.raises(
        publication.PublicationError, match="malformed publication gate"
    ):
        publication.derive_registry_state(registry, ROOT)


def test_registry_rejects_missing_gate_id() -> None:
    registry: dict[str, Any] = {
        "benchmarks": [
            {
                "artifact_ids": [],
                "artifacts": [],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "candidate",
                "publication_gate": {"approved_targets": ["hugging_face_raw"]},
                "publication_gate_id": None,
            }
        ]
    }

    with pytest.raises(publication.PublicationError, match="gate ID is missing"):
        publication.derive_registry_state(registry, ROOT)


def test_registry_rejects_non_dict_artifact() -> None:
    registry = {
        "benchmarks": [
            {
                "artifact_ids": [],
                "artifacts": [None],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "candidate",
                "publication_gate": None,
                "publication_gate_id": None,
            }
        ]
    }

    with pytest.raises(publication.PublicationError, match="malformed artifact entry"):
        publication.derive_registry_state(registry, ROOT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 1),
        ("benchmark_id", "other"),
        ("kind", 1),
        ("sensitivity", 1),
        ("answer_key_label", 1),
    ],
)
def test_registry_rejects_invalid_artifact_field_types(
    field: str,
    value: object,
) -> None:
    artifact: dict[str, object] = {
        "answer_key_label": None,
        "approved_targets": ["hugging_face_raw"],
        "id": "sample:public",
        "kind": "public_input",
        "benchmark_id": "sample",
        "sensitivity": "public_input",
    }
    artifact[field] = value
    registry = {
        "benchmarks": [
            {
                "artifact_ids": ["sample:public"],
                "artifacts": [artifact],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "candidate",
                "publication_gate": None,
                "publication_gate_id": None,
            }
        ]
    }

    with pytest.raises(publication.PublicationError, match="malformed artifact entry"):
        publication.derive_registry_state(registry, ROOT)


@pytest.mark.parametrize(
    "approved_targets",
    [["unknown"], ["repository", "repository"], [1], "repository"],
)
def test_registry_rejects_invalid_target_vocabularies(
    approved_targets: object,
) -> None:
    registry = {
        "benchmarks": [
            {
                "artifacts": [],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "candidate",
                "publication_gate": {"approved_targets": approved_targets},
            }
        ]
    }

    with pytest.raises(
        publication.PublicationError, match="invalid publication targets"
    ):
        publication.derive_registry_state(_complete_registry(registry), ROOT)


def test_registry_rejects_viewer_evaluator_artifact(tmp_path: Path) -> None:
    source = tmp_path / "evaluator/truth.json"
    source.parent.mkdir()
    source.write_bytes(b"{}\n")
    registry = {
        "benchmarks": [
            {
                "artifacts": [
                    {
                        "answer_key_label": "Evaluator truth.",
                        "approved_sha256": hashlib.sha256(
                            source.read_bytes()
                        ).hexdigest(),
                        "approved_targets": ["hugging_face_viewer"],
                        "id": "sample:truth",
                        "kind": "evaluator_truth",
                        "path": "evaluator/truth.json",
                        "sensitivity": "public_reference_truth",
                    }
                ],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": _approved_hf_gate("sample", "hugging_face_viewer"),
            }
        ]
    }

    with pytest.raises(publication.PublicationError, match="public-only artifact"):
        publication.derive_registry_state(
            _complete_registry(registry),
            tmp_path,
        )


def test_registry_rejects_viewer_evaluator_marker_for_public_input(
    tmp_path: Path,
) -> None:
    source = tmp_path / "evaluator/truth.json"
    source.parent.mkdir()
    source.write_bytes(b"{}\n")
    registry = {
        "benchmarks": [
            {
                "artifacts": [
                    {
                        "answer_key_label": None,
                        "approved_sha256": hashlib.sha256(
                            source.read_bytes()
                        ).hexdigest(),
                        "approved_targets": ["hugging_face_viewer"],
                        "id": "sample:public",
                        "kind": "public_input",
                        "path": "evaluator/truth.json",
                        "sensitivity": "public_input",
                    }
                ],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": _approved_hf_gate("sample", "hugging_face_viewer"),
            }
        ]
    }

    with pytest.raises(publication.PublicationError, match="public-only artifact"):
        publication.derive_registry_state(
            _complete_registry(registry),
            tmp_path,
        )


def test_registry_allows_viewer_safe_public_input(tmp_path: Path) -> None:
    source = tmp_path / "public/sample.json"
    source.parent.mkdir()
    source.write_bytes(b"{}\n")
    registry = {
        "benchmarks": [
            {
                "artifacts": [
                    {
                        "answer_key_label": None,
                        "approved_sha256": hashlib.sha256(
                            source.read_bytes()
                        ).hexdigest(),
                        "approved_targets": ["hugging_face_viewer"],
                        "id": "sample:public",
                        "kind": "public_input",
                        "path": "public/sample.json",
                        "sensitivity": "public_input",
                    }
                ],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": _approved_hf_gate("sample", "hugging_face_viewer"),
            }
        ]
    }

    operations, _, _ = publication.derive_registry_state(
        _complete_registry(registry),
        tmp_path,
    )

    assert operations[0]["target"] == "hugging_face_viewer"
    assert operations[0]["source_path"] == "public/sample.json"


def test_registry_allows_explicitly_labeled_raw_evaluator_artifact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "evaluator/truth.json"
    source.parent.mkdir()
    source.write_bytes(b"{}\n")
    registry = {
        "benchmarks": [
            {
                "artifacts": [
                    {
                        "answer_key_label": "Published reference truth.",
                        "approved_sha256": hashlib.sha256(
                            source.read_bytes()
                        ).hexdigest(),
                        "approved_targets": ["hugging_face_raw"],
                        "id": "sample:truth",
                        "kind": "evaluator_truth",
                        "path": "evaluator/truth.json",
                        "sensitivity": "public_reference_truth",
                    }
                ],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": _approved_hf_gate("sample", "hugging_face_raw"),
            }
        ]
    }

    operations, _, _ = publication.derive_registry_state(
        _complete_registry(registry),
        tmp_path,
    )

    assert operations[0]["artifact_kind"] == "evaluator_truth"
    assert operations[0]["answer_key_label"] == "Published reference truth."


@pytest.mark.parametrize(
    ("kind", "sensitivity", "label"),
    [
        ("evaluator_truth", "public_reference_truth", None),
        ("evaluator_truth", "public_input", "Truth."),
        ("public_input", "public_input", "Truth."),
    ],
)
def test_registry_rejects_incorrectly_labeled_raw_artifact(
    tmp_path: Path,
    kind: str,
    sensitivity: str,
    label: str | None,
) -> None:
    source = tmp_path / "sample.json"
    source.write_bytes(b"{}\n")
    registry = {
        "benchmarks": [
            {
                "artifacts": [
                    {
                        "answer_key_label": label,
                        "approved_sha256": hashlib.sha256(
                            source.read_bytes()
                        ).hexdigest(),
                        "approved_targets": ["hugging_face_raw"],
                        "id": "sample:data",
                        "kind": kind,
                        "path": "sample.json",
                        "sensitivity": sensitivity,
                    }
                ],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": _approved_hf_gate("sample", "hugging_face_raw"),
            }
        ]
    }

    with pytest.raises(publication.PublicationError):
        publication.derive_registry_state(
            _complete_registry(registry),
            tmp_path,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"decision": "blocked"},
        {"benchmark_id": "other"},
        {"benchmark_version": "2.0.0"},
        {"id": "other-gate"},
        {"checks": "invalid"},
        {"checks": []},
    ],
)
def test_registry_rejects_invalid_hf_gate(mutation: dict[str, object]) -> None:
    gate = _approved_hf_gate("sample", "hugging_face_raw")
    gate.update(mutation)
    registry = {
        "benchmarks": [
            {
                "artifacts": [],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": gate,
            }
        ]
    }

    with pytest.raises(publication.PublicationError):
        publication.derive_registry_state(_complete_registry(registry), ROOT)


@pytest.mark.parametrize(
    "checks",
    [
        [None],
        [
            {"name": "adversarial_review", "status": "pass"},
            {"name": "adversarial_review", "status": "pass"},
        ],
    ],
)
def test_registry_rejects_malformed_or_duplicate_hf_checks(
    checks: list[object],
) -> None:
    gate = _approved_hf_gate("sample", "hugging_face_raw")
    gate["checks"] = checks
    registry = {
        "benchmarks": [
            {
                "artifacts": [],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "candidate",
                "publication_gate": gate,
            }
        ]
    }

    with pytest.raises(publication.PublicationError, match="checks"):
        publication.derive_registry_state(_complete_registry(registry), ROOT)


@pytest.mark.parametrize("field", ["artifact_ids", "artifact_benchmark_id"])
def test_registry_binds_artifact_identity(tmp_path: Path, field: str) -> None:
    source = tmp_path / "sample.json"
    source.write_bytes(b"{}\n")
    registry = _complete_registry(
        {
            "benchmarks": [
                {
                    "artifacts": [
                        {
                            "answer_key_label": None,
                            "approved_sha256": hashlib.sha256(
                                source.read_bytes()
                            ).hexdigest(),
                            "approved_targets": ["hugging_face_raw"],
                            "id": "sample:public",
                            "kind": "public_input",
                            "path": "sample.json",
                            "sensitivity": "public_input",
                        }
                    ],
                    "benchmark_version": "1.0.0",
                    "id": "sample",
                    "lifecycle": "published",
                    "publication_gate": _approved_hf_gate("sample", "hugging_face_raw"),
                }
            ]
        }
    )
    if field == "artifact_ids":
        registry["benchmarks"][0]["artifact_ids"] = ["other:public"]
    else:
        registry["benchmarks"][0]["artifacts"][0]["benchmark_id"] = "other"

    with pytest.raises(publication.PublicationError):
        publication.derive_registry_state(registry, tmp_path)


@pytest.mark.parametrize("source_path", [".", "../escape.json", "absolute"])
def test_registry_rejects_source_path_escape(tmp_path: Path, source_path: str) -> None:
    if source_path == "absolute":
        source_path = str(tmp_path.parent / "escape.json")
    with pytest.raises(publication.PublicationError, match="escapes repository"):
        publication._source_file(tmp_path, source_path)


def test_registry_rejects_symlink_source_path(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(b"{}\n")
    (tmp_path / "linked.json").symlink_to(target)

    with pytest.raises(publication.PublicationError, match="path is a symlink"):
        publication._source_file(tmp_path, "linked.json")


def test_registry_rejects_source_digest_drift(tmp_path: Path) -> None:
    source = tmp_path / "sample.json"
    source.write_bytes(b"actual\n")
    registry = {
        "benchmarks": [
            {
                "artifacts": [
                    {
                        "answer_key_label": None,
                        "approved_sha256": "0" * 64,
                        "approved_targets": ["hugging_face_raw"],
                        "id": "sample:public",
                        "kind": "public_input",
                        "path": "sample.json",
                        "sensitivity": "public_input",
                    }
                ],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": _approved_hf_gate("sample", "hugging_face_raw"),
            }
        ]
    }

    with pytest.raises(publication.PublicationError, match="source bytes"):
        publication.derive_registry_state(_complete_registry(registry), tmp_path)


def test_file_sha256_normalizes_missing_file() -> None:
    with pytest.raises(publication.PublicationError, match="cannot hash"):
        publication.file_sha256(Path("missing-artifact.json"))


def test_build_plan_reports_authorized_dry_run() -> None:
    manifest = _manifest()
    operation = {"artifact_id": "sample"}

    plan = publication.build_plan(manifest, [operation])

    assert plan["status"] == "ready_for_protected_dry_run"
    assert plan["upload_enabled"] is False


def test_noncanonical_manifest_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(MANIFEST.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(publication.PublicationError, match="not canonical"):
        _validate(path)


def test_unreadable_canonical_manifest_bytes_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")

    def fail_read_bytes(_path: Path) -> bytes:
        raise OSError("synthetic read failure")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    with pytest.raises(publication.PublicationError, match="canonical bytes"):
        _validate(path)


def test_manifest_schema_failure_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest()
    del manifest["schema_version"]
    path = tmp_path / "manifest.json"
    _write_json(path, manifest)

    with pytest.raises(publication.PublicationError, match="schema error"):
        _validate(path)


@pytest.mark.parametrize("target", ["registry", "dataset_card"])
def test_manifest_digest_drift_is_rejected(tmp_path: Path, target: str) -> None:
    manifest = _manifest()
    if target == "registry":
        manifest[target]["sha256"] = "0" * 64
    else:
        manifest[target]["operation"]["sha256"] = "0" * 64
    path = tmp_path / "manifest.json"
    _write_json(path, manifest)

    with pytest.raises(publication.PublicationError, match="SHA-256"):
        _validate(path)


def test_card_config_drift_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["dataset_card"]["configs"] = []
    path = tmp_path / "manifest.json"
    _write_json(path, manifest)

    with pytest.raises(publication.PublicationError, match="config inventory"):
        _validate(path)


def test_dataset_card_operation_must_be_derived(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["dataset_card"]["operation"]["size_bytes"] += 1
    path = tmp_path / "manifest.json"
    _write_json(path, manifest)

    with pytest.raises(publication.PublicationError, match="operation is not derived"):
        _validate(path)


def test_prohibited_benchmark_cannot_be_authorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()

    def prohibited_registry_state(
        _registry: dict[str, Any],
        _repository_root: Path,
        _remote_baseline: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
        return (
            [{"benchmark_id": "asteria-agentic-c08-v2"}],
            manifest["authorized_benchmarks"],
            manifest["registry_summary"],
        )

    monkeypatch.setattr(
        publication,
        "derive_registry_state",
        prohibited_registry_state,
    )
    with pytest.raises(publication.PublicationError, match="prohibited benchmark"):
        _validate(MANIFEST)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        (
            "operations",
            [],
        ),
        (
            "authorized_benchmarks",
            [
                {
                    "benchmark_id": "sample",
                    "benchmark_version": "1.0.0",
                    "targets": ["hugging_face_raw"],
                }
            ],
        ),
        (
            "registry_summary",
            {
                "candidate": 0,
                "hf_authorized_artifacts": 0,
                "published": 0,
                "total": 0,
            },
        ),
    ],
)
def test_manifest_must_match_derived_registry_state(
    tmp_path: Path, field: str, replacement: object
) -> None:
    manifest = _manifest()
    manifest[field] = replacement
    path = tmp_path / "manifest.json"
    _write_json(path, manifest)

    with pytest.raises(publication.PublicationError, match=field):
        _validate(path)


def test_cli_emits_plan_to_stdout_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    output = tmp_path / "nested/dry-run.json"

    assert publication.main([]) == 0
    stdout = capsys.readouterr().out
    assert json.loads(stdout)["status"] == "ready_for_protected_dry_run"
    assert publication.main(["--emit-plan", str(output)]) == 0
    assert len(json.loads(output.read_text(encoding="utf-8"))["operations"]) == 9


def test_cli_reports_validation_error() -> None:
    with pytest.raises(SystemExit) as error:
        publication.main(["--manifest", "missing-manifest.json"])

    assert error.value.code == 2


def test_protected_workflow_has_no_hf_credential_or_upload_command() -> None:
    workflow = (ROOT / ".github/workflows/huggingface-publication.yml").read_text(
        encoding="utf-8"
    )

    parsed = yaml.safe_load(workflow.replace("\non:", '\n"on":', 1))

    assert set(parsed["on"]) == {"pull_request", "push", "workflow_dispatch"}
    publication_inputs = {
        ".github/workflows/huggingface-publication.yml",
        "docs/_data/benchmark-publication-gates.json",
        "docs/_data/benchmark-transitions.json",
        "docs/_data/benchmarks.curated.json",
        "docs/_data/benchmarks.generated.json",
        "docs/_data/benchmarks.resolved.json",
        "docs/_schemas/benchmarks-resolved.schema.json",
        "huggingface/**",
        "src/synthworld/benchmarks/**",
        "pyproject.toml",
        "tests/test_huggingface_publication.py",
        "tools/check_huggingface_publication.py",
        "tools/generate_benchmark_registry.py",
        "uv.lock",
    }
    assert set(parsed["on"]["push"]["paths"]) == publication_inputs
    assert set(parsed["on"]["pull_request"]["paths"]) == publication_inputs
    assert parsed["on"]["push"]["branches"] == ["main"]
    protected = parsed["jobs"]["protected-dry-run"]
    assert protected["environment"] == "hugging-face-publication"
    condition = " ".join(protected["if"].split())
    assert condition == (
        "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
    )
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert workflow.count("uv run --offline --frozen") == 3
    assert "tools/generate_benchmark_registry.py" in workflow
    action_refs = [
        line.split("@", 1)[1].split()[0]
        for line in workflow.splitlines()
        if line.lstrip().startswith("uses:")
    ]
    assert action_refs
    assert all(
        len(ref) == 40 and set(ref) <= set("0123456789abcdef") for ref in action_refs
    )
    lowered = workflow.lower()
    for forbidden in (
        "${{ secrets[",
        "curl ",
        "gh api",
        "git push",
        "github.token",
        "hf upload",
        "hf_api_token",
        "hf_token",
        "huggingface_hub_token",
        "huggingface-cli",
        "huggingface_hub",
        "requests.",
        "secrets.",
        "socket.",
        "urllib",
        "vars.",
        "wget ",
    ):
        assert forbidden not in lowered
