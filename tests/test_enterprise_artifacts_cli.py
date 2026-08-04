"""Enterprise artifact, scaffold, schema, and CLI acceptance tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from synthworld.cli import main
from synthworld.enterprise.canonical import canonical_json_value_bytes
from synthworld.enterprise.compiler import (
    compile_enterprise_identity_access_universe,
)
from synthworld.enterprise.models import (
    EnterpriseArtifactDescriptorV1,
    EnterpriseArtifactManifestV1,
    EnterpriseIdentityAccessCompileResultV1,
    SyntheticDigestV1,
)
from synthworld.enterprise.parsers import (
    CSV_HEADERS,
    load_enterprise_identity_access_import,
)
from synthworld.enterprise.reference import (
    REFERENCE_NAMESPACE_SALT,
    reference_enterprise_identity_access_import,
)
from synthworld.enterprise.scaffold import (
    EnterpriseScaffoldError,
    scaffold_enterprise_access,
)
from synthworld.enterprise.serialization import (
    EVALUATOR_BINDING_PATH,
    EVALUATOR_MANIFEST_PATH,
    PUBLIC_MANIFEST_PATH,
    PUBLIC_UNIVERSE_PATH,
    EnterpriseArtifactError,
    _validate_descriptor,
    export_enterprise_identity_access_compile_result,
    load_evaluator_enterprise_canonical_binding_truth,
    load_public_enterprise_identity_access_universe,
)

CONTRACT_ROOT = Path("enterprise-identity-access-contract")


@pytest.fixture(scope="module")
def compiled_reference() -> EnterpriseIdentityAccessCompileResultV1:
    return compile_enterprise_identity_access_universe(
        import_model=reference_enterprise_identity_access_import(),
        seed=20_260_804,
    )


def _export(
    tmp_path: Path, result: EnterpriseIdentityAccessCompileResultV1, name: str = "run"
) -> Path:
    root = tmp_path / name
    export_enterprise_identity_access_compile_result(root, result)
    return root


def _document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_canonical(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_value_bytes(value))


def test_export_is_deterministic_exact_and_physically_separated(
    tmp_path: Path, compiled_reference: EnterpriseIdentityAccessCompileResultV1
) -> None:
    first = _export(tmp_path, compiled_reference, "first")
    second = _export(tmp_path, compiled_reference, "second")
    expected = {
        PUBLIC_UNIVERSE_PATH,
        PUBLIC_MANIFEST_PATH,
        EVALUATOR_BINDING_PATH,
        EVALUATOR_MANIFEST_PATH,
    }
    assert {
        path.relative_to(first).as_posix()
        for path in first.rglob("*")
        if path.is_file()
    } == expected
    for relative in expected:
        payload = (first / relative).read_bytes()
        assert payload == (second / relative).read_bytes()
        assert payload.endswith(b"\n")

    assert load_public_enterprise_identity_access_universe(first) == (
        compiled_reference.public_universe
    )
    assert load_evaluator_enterprise_canonical_binding_truth(first) == (
        compiled_reference.evaluator_canonical_binding_truth
    )
    public_bytes = (first / PUBLIC_UNIVERSE_PATH).read_bytes()
    assert b'"bindings"' not in public_bytes
    assert b"id_namespace_salt" not in public_bytes


def test_public_and_evaluator_loaders_do_not_traverse_the_other_tree(
    tmp_path: Path, compiled_reference: EnterpriseIdentityAccessCompileResultV1
) -> None:
    public_case = _export(tmp_path, compiled_reference, "public-case")
    (public_case / EVALUATOR_BINDING_PATH).write_bytes(b"not evaluator json")
    assert load_public_enterprise_identity_access_universe(public_case) == (
        compiled_reference.public_universe
    )

    evaluator_case = _export(tmp_path, compiled_reference, "evaluator-case")
    (evaluator_case / PUBLIC_UNIVERSE_PATH).write_bytes(b"not public json")
    assert load_evaluator_enterprise_canonical_binding_truth(evaluator_case) == (
        compiled_reference.evaluator_canonical_binding_truth
    )


def test_evaluator_loader_rejects_public_visibility(
    tmp_path: Path, compiled_reference: EnterpriseIdentityAccessCompileResultV1
) -> None:
    root = _export(tmp_path, compiled_reference)
    manifest_path = root / EVALUATOR_MANIFEST_PATH
    manifest = _document(manifest_path)
    manifest["visibility"] = "public"
    _write_canonical(manifest_path, manifest)
    with pytest.raises(EnterpriseArtifactError, match="wrong visibility"):
        load_evaluator_enterprise_canonical_binding_truth(root)


def test_descriptor_read_errors_are_normalized(tmp_path: Path) -> None:
    manifest = EnterpriseArtifactManifestV1(
        visibility="public",
        artifacts=(
            EnterpriseArtifactDescriptorV1(
                path="missing.json",
                schema_version="1.0.0",
                digest=SyntheticDigestV1(value="0" * 64),
                byte_size=0,
            ),
        ),
    )
    with pytest.raises(
        EnterpriseArtifactError, match="declared artifact is unreadable"
    ):
        _validate_descriptor(
            tmp_path,
            manifest,
            expected_path="missing.json",
            expected_schema="1.0.0",
        )


def test_export_refuses_an_existing_root(
    tmp_path: Path, compiled_reference: EnterpriseIdentityAccessCompileResultV1
) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    with pytest.raises(EnterpriseArtifactError, match="must not already exist"):
        export_enterprise_identity_access_compile_result(root, compiled_reference)


@pytest.mark.parametrize("entry_kind", ["extra", "missing", "directory", "symlink"])
def test_public_loader_rejects_non_exact_or_non_regular_inventory(
    tmp_path: Path,
    compiled_reference: EnterpriseIdentityAccessCompileResultV1,
    entry_kind: str,
) -> None:
    root = _export(tmp_path, compiled_reference)
    universe = root / PUBLIC_UNIVERSE_PATH
    if entry_kind == "extra":
        (root / "public/extra.json").write_text("{}\n", encoding="utf-8")
    elif entry_kind == "missing":
        universe.unlink()
    elif entry_kind == "directory":
        universe.unlink()
        universe.mkdir()
    else:
        payload = root / "universe-copy.json"
        payload.write_bytes(universe.read_bytes())
        universe.unlink()
        universe.symlink_to(payload)
    with pytest.raises(EnterpriseArtifactError, match=r"inventory|non-regular"):
        load_public_enterprise_identity_access_universe(root)


def test_public_loader_rejects_missing_or_linked_root(
    tmp_path: Path, compiled_reference: EnterpriseIdentityAccessCompileResultV1
) -> None:
    with pytest.raises(EnterpriseArtifactError, match="unreadable"):
        load_public_enterprise_identity_access_universe(tmp_path / "absent")

    root = _export(tmp_path, compiled_reference)
    real_public = root / "real-public"
    (root / "public").rename(real_public)
    (root / "public").symlink_to(real_public, target_is_directory=True)
    with pytest.raises(EnterpriseArtifactError, match="not a real directory"):
        load_public_enterprise_identity_access_universe(root)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("visibility", "wrong visibility"),
        ("empty", "exactly one artifact"),
        ("path", "path or schema binding"),
        ("schema", "path or schema binding"),
        ("size", "byte size or digest"),
        ("digest", "byte size or digest"),
    ],
)
def test_public_loader_rejects_manifest_misbinding(
    tmp_path: Path,
    compiled_reference: EnterpriseIdentityAccessCompileResultV1,
    case: str,
    message: str,
) -> None:
    root = _export(tmp_path, compiled_reference)
    manifest_path = root / PUBLIC_MANIFEST_PATH
    manifest = _document(manifest_path)
    if case == "visibility":
        manifest["visibility"] = "evaluator"
    elif case == "empty":
        manifest["artifacts"] = []
    else:
        artifacts = manifest["artifacts"]
        assert isinstance(artifacts, list)
        descriptor = artifacts[0]
        assert isinstance(descriptor, dict)
        if case == "path":
            descriptor["path"] = "other.json"
        elif case == "schema":
            descriptor["schema_version"] = "9.0.0"
        elif case == "size":
            descriptor["byte_size"] = 0
        else:
            digest = descriptor["digest"]
            assert isinstance(digest, dict)
            digest["value"] = "0" * 64
    _write_canonical(manifest_path, manifest)
    with pytest.raises(EnterpriseArtifactError, match=message):
        load_public_enterprise_identity_access_universe(root)


@pytest.mark.parametrize("target", [PUBLIC_MANIFEST_PATH, PUBLIC_UNIVERSE_PATH])
def test_public_loader_rejects_malformed_and_noncanonical_json(
    tmp_path: Path,
    compiled_reference: EnterpriseIdentityAccessCompileResultV1,
    target: str,
) -> None:
    malformed = _export(tmp_path, compiled_reference, "malformed")
    (malformed / target).write_bytes(b"not json")
    with pytest.raises(EnterpriseArtifactError, match="does not match its schema"):
        load_public_enterprise_identity_access_universe(malformed)

    noncanonical = _export(tmp_path, compiled_reference, "noncanonical")
    path = noncanonical / target
    path.write_text(
        json.dumps(_document(path), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(EnterpriseArtifactError, match="not canonical JSON"):
        load_public_enterprise_identity_access_universe(noncanonical)


@pytest.mark.parametrize("output_format", ["yaml", "json", "csv"])
def test_scaffolds_round_trip_with_a_fixed_private_namespace(
    tmp_path: Path, output_format: str
) -> None:
    output = tmp_path / (
        "bundle" if output_format == "csv" else f"input.{output_format}"
    )
    salt = scaffold_enterprise_access(
        output_format=output_format,  # type: ignore[arg-type]
        output=output,
        id_namespace_salt=REFERENCE_NAMESPACE_SALT,
    )
    assert salt == REFERENCE_NAMESPACE_SALT
    assert load_enterprise_identity_access_import(output) == (
        reference_enterprise_identity_access_import()
    )
    if output_format == "csv":
        assert {path.name for path in output.iterdir()} == set(CSV_HEADERS)
        assert len(tuple(output.iterdir())) == 20
    else:
        assert output.read_bytes().endswith(b"\n")


def test_scaffold_generates_one_salt_and_refuses_reuse_or_invalid_salt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated_salt = "a" * 64
    monkeypatch.setattr(
        "synthworld.enterprise.scaffold.secrets.token_hex", lambda _: generated_salt
    )
    output = tmp_path / "private.yaml"
    assert (
        scaffold_enterprise_access(output_format="yaml", output=output)
        == generated_salt
    )
    assert (
        load_enterprise_identity_access_import(output).blueprint.id_namespace_salt
        == generated_salt
    )
    with pytest.raises(EnterpriseScaffoldError, match="must not already exist"):
        scaffold_enterprise_access(output_format="yaml", output=output)
    with pytest.raises(ValidationError, match="id_namespace_salt"):
        scaffold_enterprise_access(
            output_format="json",
            output=tmp_path / "bad.json",
            id_namespace_salt="not-a-256-bit-hex-value",
        )


def test_enterprise_cli_scaffold_validate_and_compile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.yaml"
    assert (
        main(
            [
                "scaffold-enterprise-access",
                "--format",
                "yaml",
                "--output",
                str(source),
                "--id-namespace-salt",
                REFERENCE_NAMESPACE_SALT,
            ]
        )
        == 0
    )
    scaffold_output = capsys.readouterr().out
    assert "Private enterprise identity/access template ready" in scaffold_output
    assert "not anonymisation" in scaffold_output

    assert main(["validate-enterprise-access", "--input", str(source)]) == 0
    assert "import: valid" in capsys.readouterr().out

    assert (
        main(
            [
                "compile-enterprise-access",
                "--input",
                str(source),
                "--seed",
                "20260804",
                "--output",
                str(tmp_path / "artifacts"),
            ]
        )
        == 0
    )
    assert "6 principals, 4 account slots, 16 access atoms" in capsys.readouterr().out


def test_enterprise_cli_reports_machine_and_human_validation_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}\n", encoding="utf-8")
    assert (
        main(
            [
                "validate-enterprise-access",
                "--input",
                str(invalid),
                "--json",
            ]
        )
        == 1
    )
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is False
    assert report["diagnostics"][0]["code"] == "model_validation"

    assert main(["validate-enterprise-access", "--input", str(invalid)]) == 1
    assert "model_validation" in capsys.readouterr().err

    assert (
        main(
            [
                "compile-enterprise-access",
                "--input",
                str(invalid),
                "--seed",
                "1",
                "--output",
                str(tmp_path / "unused"),
            ]
        )
        == 1
    )
    assert "model_validation" in capsys.readouterr().err

    existing = tmp_path / "existing.yaml"
    existing.write_text("occupied\n", encoding="utf-8")
    assert (
        main(
            [
                "scaffold-enterprise-access",
                "--output",
                str(existing),
            ]
        )
        == 1
    )
    assert "must not already exist" in capsys.readouterr().err


def test_generated_schemas_and_examples_match_the_contract(
    compiled_reference: EnterpriseIdentityAccessCompileResultV1,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "enterprise-identity-access-contract/tools/generate_contract.py",
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "match the models" in completed.stdout

    imported = reference_enterprise_identity_access_import()
    instances = {
        "enterprise-identity-access-import": imported,
        "enterprise-identity-access-blueprint": imported.blueprint,
        "enterprise-iam-universe-extension": imported.iam_universe_extension,
        "enterprise-directory-rbac-state-input": imported.directory_rbac_state,
        "enterprise-identity-access-universe": compiled_reference.public_universe,
        "enterprise-canonical-binding-truth": (
            compiled_reference.evaluator_canonical_binding_truth
        ),
    }
    for stem, instance in instances.items():
        schema = _document(CONTRACT_ROOT / "schemas" / f"{stem}.schema.json")
        validator = Draft202012Validator(schema)
        document = instance.model_dump(mode="json")
        assert validator.is_valid(document), list(validator.iter_errors(document))
        assert not validator.is_valid(document | {"unexpected": True})

    examples = CONTRACT_ROOT / "examples"
    assert (
        load_enterprise_identity_access_import(
            examples / "enterprise-access-smoke.yaml"
        )
        == imported
    )
    assert (
        load_enterprise_identity_access_import(
            examples / "enterprise-access-smoke.json"
        )
        == imported
    )
    assert load_enterprise_identity_access_import(examples / "csv") == imported
    assert len(tuple((examples / "csv").iterdir())) == 20
