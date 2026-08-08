from __future__ import annotations

import hashlib
import json
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
    return registry


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(publication.canonical_json(value), encoding="utf-8", newline="\n")


def _validate(manifest_path: Path) -> dict[str, object]:
    return publication.validate_publication(
        manifest_path, SCHEMA, REGISTRY, REGISTRY_SCHEMA, CARD, ROOT
    )


def test_repository_manifest_derives_no_upload_operations() -> None:
    plan = _validate(MANIFEST)

    assert plan == {
        "dataset_repository": "Bluntmachetti7/synthworld-benchmarks",
        "network_access": False,
        "operations": [],
        "registry_sha256": "16160bbf11c73285319374133aa9d5caf3d8699393029fc9d3dd58e89d848818",
        "status": "blocked_no_authorized_targets",
        "upload_enabled": False,
    }


@pytest.mark.parametrize("content", ["[]\n", "not-json\n"])
def test_load_json_object_rejects_non_objects_and_invalid_json(
    tmp_path: Path, content: str
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
        "---\nconfigs:\n- config_name: sample\n  data_files: []\n  extra: true\n---\nbody\n",
        "---\nconfigs:\n- config_name: sample\n  data_files: []\n  default: 'false'\n---\nbody\n",
        "---\nconfigs:\n- config_name: sample\n  data_files:\n  - path: sample.json\n---\nbody\n",
        "---\nconfigs:\n- config_name: sample\n  data_files:\n  - invalid\n---\nbody\n",
    ],
)
def test_card_config_parser_rejects_invalid_frontmatter(
    tmp_path: Path, content: str
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
                "publication_gate": _approved_hf_gate(
                    "sample", "hugging_face_raw"
                ),
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
        _complete_registry(registry), tmp_path
    )

    assert operations == [
        {
            "answer_key_label": None,
            "artifact_id": "sample:public",
            "artifact_kind": "public_input",
            "benchmark_id": "sample",
            "sha256": digest,
            "sensitivity": "public_input",
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

    operations, benchmarks, summary = publication.derive_registry_state(
        registry, ROOT
    )

    assert operations == []
    assert benchmarks == []
    assert summary == {
        "candidate": 1,
        "hf_authorized_artifacts": 0,
        "published": 0,
        "total": 1,
    }


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
    with pytest.raises(publication.PublicationError, match="benchmarks must be an array"):
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
    tmp_path: Path, artifact: dict[str, object]
) -> None:
    registry = {
        "benchmarks": [
            {
                "artifacts": [artifact],
                "benchmark_version": "1.0.0",
                "id": "sample",
                "lifecycle": "published",
                "publication_gate": _approved_hf_gate(
                    "sample", "hugging_face_raw"
                ),
            }
        ]
    }

    with pytest.raises(publication.PublicationError, match="require a path and digest"):
        publication.derive_registry_state(_complete_registry(registry), tmp_path)


def test_registry_normalizes_malformed_entries() -> None:
    with pytest.raises(publication.PublicationError, match="malformed benchmark entry"):
        publication.derive_registry_state({"benchmarks": [{}]}, ROOT)


def test_registry_rejects_non_dict_benchmark() -> None:
    with pytest.raises(
        publication.PublicationError, match="malformed benchmark entry"
    ):
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
    field: str, value: object
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

    with pytest.raises(
        publication.PublicationError, match="malformed benchmark entry"
    ):
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
    registry = {
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

    with pytest.raises(
        publication.PublicationError, match="gate ID is missing"
    ):
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

    with pytest.raises(
        publication.PublicationError, match="malformed artifact entry"
    ):
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
    field: str, value: object
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

    with pytest.raises(
        publication.PublicationError, match="malformed artifact entry"
    ):
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

    with pytest.raises(publication.PublicationError, match="invalid publication targets"):
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
                "publication_gate": _approved_hf_gate(
                    "sample", "hugging_face_viewer"
                ),
            }
        ]
    }

    with pytest.raises(
        publication.PublicationError, match="public-only artifact"
    ):
        publication.derive_registry_state(_complete_registry(registry), tmp_path)


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
                "publication_gate": _approved_hf_gate(
                    "sample", "hugging_face_viewer"
                ),
            }
        ]
    }

    with pytest.raises(
        publication.PublicationError, match="public-only artifact"
    ):
        publication.derive_registry_state(_complete_registry(registry), tmp_path)


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
                "publication_gate": _approved_hf_gate(
                    "sample", "hugging_face_raw"
                ),
            }
        ]
    }

    operations, _, _ = publication.derive_registry_state(
        _complete_registry(registry), tmp_path
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
    tmp_path: Path, kind: str, sensitivity: str, label: str | None
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
                "publication_gate": _approved_hf_gate(
                    "sample", "hugging_face_raw"
                ),
            }
        ]
    }

    with pytest.raises(publication.PublicationError):
        publication.derive_registry_state(
            _complete_registry(registry), tmp_path
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
                    "publication_gate": _approved_hf_gate(
                        "sample", "hugging_face_raw"
                    ),
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


@pytest.mark.parametrize("source_path", [".", "../escape.json", "/tmp/escape.json"])
def test_registry_rejects_source_path_escape(
    tmp_path: Path, source_path: str
) -> None:
    with pytest.raises(publication.PublicationError, match="escapes repository"):
        publication._source_file(tmp_path, source_path)


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
                "publication_gate": _approved_hf_gate(
                    "sample", "hugging_face_raw"
                ),
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


def test_manifest_schema_failure_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest()
    del manifest["schema_version"]
    path = tmp_path / "manifest.json"
    _write_json(path, manifest)

    with pytest.raises(publication.PublicationError, match="schema error"):
        _validate(path)


@pytest.mark.parametrize("target", ["registry", "historical_card"])
def test_manifest_digest_drift_is_rejected(tmp_path: Path, target: str) -> None:
    manifest = _manifest()
    manifest[target]["sha256"] = "0" * 64
    path = tmp_path / "manifest.json"
    _write_json(path, manifest)

    with pytest.raises(publication.PublicationError, match="SHA-256"):
        _validate(path)


def test_card_config_drift_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["historical_card"]["configs"] = []
    path = tmp_path / "manifest.json"
    _write_json(path, manifest)

    with pytest.raises(publication.PublicationError, match="config inventory"):
        _validate(path)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        (
            "operations",
            [
                {
                    "answer_key_label": None,
                    "artifact_id": "sample:public",
                    "artifact_kind": "public_input",
                    "benchmark_id": "sample",
                    "sha256": "a" * 64,
                    "sensitivity": "public_input",
                    "source_path": "sample.json",
                    "target": "hugging_face_raw",
                }
            ],
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
    assert json.loads(stdout)["status"] == "blocked_no_authorized_targets"
    assert publication.main(["--emit-plan", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["operations"] == []


def test_cli_reports_validation_error() -> None:
    with pytest.raises(SystemExit) as error:
        publication.main(["--manifest", "missing-manifest.json"])

    assert error.value.code == 2


def test_protected_workflow_has_no_hf_credential_or_upload_command() -> None:
    workflow = (ROOT / ".github/workflows/huggingface-publication.yml").read_text(
        encoding="utf-8"
    )

    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)

    assert set(parsed["on"]) == {"pull_request", "push", "workflow_dispatch"}
    assert set(parsed["on"]["push"]["paths"]) >= {"pyproject.toml", "uv.lock"}
    assert set(parsed["on"]["pull_request"]["paths"]) >= {
        "pyproject.toml",
        "uv.lock",
    }
    assert parsed["on"]["push"]["branches"] == ["main"]
    protected = parsed["jobs"]["protected-dry-run"]
    assert protected["environment"] == "hugging-face-publication"
    condition = " ".join(protected["if"].split())
    assert condition == (
        "github.event_name == 'workflow_dispatch' && "
        "github.ref == 'refs/heads/main'"
    )
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert workflow.count("uv run --offline --frozen") == 2
    action_refs = [
        line.split("@", 1)[1].split()[0]
        for line in workflow.splitlines()
        if line.lstrip().startswith("uses:")
    ]
    assert action_refs
    assert all(
        len(ref) == 40 and set(ref) <= set("0123456789abcdef")
        for ref in action_refs
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
