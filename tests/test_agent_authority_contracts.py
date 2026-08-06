"""Published-schema, CLI, and legacy-draft migration contract tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from synthworld.agent_authority.migration import (
    LegacyDraftMigrationError,
    partition_legacy_draft_manifest,
)
from synthworld.agent_authority.reference import (
    build_reference_agent_authority_run_receipt,
    reference_observations,
    reference_plan,
    reference_stimuli,
    reference_systems,
    reference_truth,
)
from synthworld.agent_authority.scoring import evaluate_agent_authority_lab
from synthworld.assurance.agent_authority import EVALUATION_PATH
from synthworld.assurance.models_v2 import ExecutionReceiptV2, RunReceiptManifestV2
from synthworld.assurance.receipt import EXECUTION_PATH, MANIFEST_PATH
from synthworld.cli import main

SCHEMA_DIR = Path("agent-authority-contract/schemas")
LEGACY_EXAMPLE = Path(
    "agent-authority-contract/examples/migration/run-manifest-0.1.0-supported.json"
)


@pytest.fixture(scope="module")
def protocol_receipt(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("protocol-contract-receipt") / "run"
    build_reference_agent_authority_run_receipt(root)
    return root


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validator(stem: str) -> Draft202012Validator:
    schema = _load(SCHEMA_DIR / f"{stem}.schema.json")
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_legacy_draft_example_partitions_without_information_loss() -> None:
    source = _load(LEGACY_EXAMPLE)
    legacy_schema = _load(SCHEMA_DIR / "run-manifest.schema.json")
    Draft202012Validator(
        legacy_schema,
        format_checker=FormatChecker(),
    ).validate(source)

    partition = partition_legacy_draft_manifest(source)
    assert partition.reconstruct_source() == source
    assert tuple(item.name for item in partition.receipt_v2_fields) == (
        "manifest_version",
        "run_id",
        "created_at",
        "completed_at",
        "operator",
        "benchmark_identity",
        "scoring",
        "build_provenance",
        "adapter",
        "systems_under_test",
    )
    assert tuple(item.name for item in partition.run_plan_fields) == (
        "run_layer",
        "controls_exercised",
        "topology",
        "authority_critical_dependencies",
        "declared_bounds",
        "review",
        "conflicts_declared",
    )
    assert tuple(item.name for item in partition.observation_fields) == ("limitations",)
    assert "synthetic" not in partition.model_dump()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"vendor_extension": True}, "unsupported.*vendor_extension"),
        ({"manifest_version": "0.2.0-draft"}, "unsupported.*version"),
    ],
)
def test_legacy_draft_migration_has_explicit_diagnostics(
    mutation: dict[str, object], message: str
) -> None:
    source = _load(LEGACY_EXAMPLE)
    source.update(mutation)
    with pytest.raises(LegacyDraftMigrationError, match=message):
        partition_legacy_draft_manifest(source)


def test_legacy_draft_migration_rejects_missing_fields_and_nonobjects() -> None:
    source = _load(LEGACY_EXAMPLE)
    del source["run_id"]
    with pytest.raises(LegacyDraftMigrationError, match=r"missing.*run_id"):
        partition_legacy_draft_manifest(source)
    with pytest.raises(LegacyDraftMigrationError, match="JSON object"):
        partition_legacy_draft_manifest([])
    with pytest.raises(LegacyDraftMigrationError, match="JSON object"):
        partition_legacy_draft_manifest({1: "not a JSON object key"})


@pytest.mark.parametrize(
    ("stem", "document"),
    [
        ("agent-authority-run-plan", reference_plan().model_dump(mode="json")),
        (
            "agent-authority-observations",
            reference_observations().model_dump(mode="json"),
        ),
        ("agent-authority-lab-truth", reference_truth().model_dump(mode="json")),
        (
            "agent-authority-lab-report",
            evaluate_agent_authority_lab(
                reference_plan(),
                reference_stimuli(),
                reference_observations(),
                reference_truth(),
                reference_systems(),
            ).model_dump(mode="json"),
        ),
    ],
)
def test_reference_protocol_documents_match_published_schemas(
    stem: str, document: dict[str, Any]
) -> None:
    validator = _validator(stem)
    assert validator.is_valid(document), list(validator.iter_errors(document))
    assert not validator.is_valid(document | {"unexpected": True})


def test_reference_receipt_documents_match_published_schemas(
    protocol_receipt: Path,
) -> None:
    manifest = RunReceiptManifestV2.model_validate_json(
        (protocol_receipt / MANIFEST_PATH).read_bytes()
    )
    execution = ExecutionReceiptV2.model_validate_json(
        (protocol_receipt / EXECUTION_PATH).read_bytes()
    )
    for stem, model in (
        ("run-receipt-manifest-v2", manifest),
        ("execution-receipt-v2", execution),
    ):
        document = model.model_dump(mode="json")
        validator = _validator(stem)
        assert validator.is_valid(document), list(validator.iter_errors(document))
        assert not validator.is_valid(document | {"unexpected": True})

    report = _load(protocol_receipt / EVALUATION_PATH)
    assert _validator("agent-authority-lab-report").is_valid(report)


def test_generated_protocol_schemas_have_no_drift() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "agent-authority-contract/tools/generate_protocol_schemas.py",
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "match the models" in completed.stdout


def test_agent_authority_validation_cli_paths(
    protocol_receipt: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = protocol_receipt / "context/run-plan.json"
    assert (
        main(["validate", "agent-authority-run-plan", "--input", str(plan_path)]) == 0
    )
    assert "run-plan: valid" in capsys.readouterr().out

    assert (
        main(["validate", "agent-authority-receipt", "--input", str(protocol_receipt)])
        == 0
    )
    assert "8 bound artifacts" in capsys.readouterr().out

    invalid = tmp_path / "invalid-plan.json"
    invalid.write_text('{"schema_version":"1.0.0"}\n', encoding="utf-8")
    assert main(["validate", "agent-authority-run-plan", "--input", str(invalid)]) == 1
    assert "validation error" in capsys.readouterr().err

    assert (
        main(
            [
                "validate",
                "agent-authority-receipt",
                "--input",
                str(tmp_path / "absent"),
            ]
        )
        == 1
    )
    assert "No such file" in capsys.readouterr().err
