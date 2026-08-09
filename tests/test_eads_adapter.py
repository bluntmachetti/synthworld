from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
import yaml
from pydantic import ValidationError

from examples.eads_adapter.adapter import AdapterConfig, run_adapter
from examples.eads_adapter.models import SourceVintage, parse_source
from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessUniverseV1,
)
from synthworld.enterprise.serialization import (
    load_evaluator_enterprise_canonical_binding_truth,
    load_public_enterprise_identity_access_universe,
)

FIXTURES = Path(__file__).parents[1] / "examples" / "eads_adapter" / "fixtures"
REPORT_PATH = Path("private/reports/eads-adapter-gap-report.json")
IMPORT_SUFFIX = Path("private/imports/enterprise-import.json")
PUBLIC_SUFFIX = Path("public/identity-access-universe.json")
TRUTH_SUFFIX = Path("evaluator/canonical-binding-truth.json")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _json_fixture(name: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((FIXTURES / name).read_text(encoding="utf-8")),
    )


def _yaml_fixture(name: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8")),
    )


def _config(
    *,
    max_principals: int = 100_000,
    namespace_salt: str = "a" * 64,
) -> AdapterConfig:
    return AdapterConfig(
        seed=20260808,
        namespace_salt=namespace_salt,
        max_principals_per_organisation=max_principals,
    )


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


def _single_path(root: Path, suffix: Path) -> Path:
    matches = sorted(path for path in root.rglob("*") if path.is_file())
    selected = [
        path
        for path in matches
        if path.name == suffix.name
        and all(part in path.parts for part in suffix.parts[:-1])
    ]
    assert len(selected) == 1
    return selected[0]


def _report(root: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((root / REPORT_PATH).read_text(encoding="utf-8")),
    )


def _gap_codes(report: Mapping[str, object]) -> set[str]:
    gaps = cast(list[dict[str, object]], report["gaps"])
    return {cast(str, gap["code"]) for gap in gaps}


def _organisation(payload: dict[str, object]) -> dict[str, object]:
    organisations = cast(list[dict[str, object]], payload["organisations"])
    assert len(organisations) == 1
    return organisations[0]


def _assert_no_organisation_artifacts(root: Path) -> None:
    artifacts = root / "artifacts"
    assert not artifacts.exists() or not any(artifacts.rglob("*.json"))


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "examples.eads_adapter", *args],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("fixture_name", "vintage", "measurement_field", "measurement_value"),
    [
        ("sdk-size-v1-humans.json", SourceVintage.SDK_SIZE_V1, "size", 400),
        (
            "topology-headcount-v1-anchor.yaml",
            SourceVintage.TOPOLOGY_HEADCOUNT_V1,
            "headcount",
            120,
        ),
    ],
)
def test_parse_source_requires_an_explicit_vintage_and_retains_ignored_measurement(
    fixture_name: str,
    vintage: SourceVintage,
    measurement_field: str,
    measurement_value: int,
) -> None:
    payload = (
        _yaml_fixture(fixture_name)
        if fixture_name.endswith(".yaml")
        else _json_fixture(fixture_name)
    )

    source = parse_source(payload, vintage)

    measurement = source.organisations[0].teams[0].ignored_source_measurements[0]
    assert source.source_vintage is vintage
    assert measurement.field == measurement_field
    assert measurement.value == measurement_value


def test_parse_source_rejects_wrong_mixed_and_negative_measurement_shapes() -> None:
    sdk = _json_fixture("sdk-size-v1-humans.json")
    topology = _yaml_fixture("topology-headcount-v1-anchor.yaml")
    mixed = copy.deepcopy(sdk)
    mixed_team = cast(list[dict[str, object]], _organisation(mixed)["teams"])[0]
    mixed_team["headcount"] = mixed_team["size"]
    negative = copy.deepcopy(sdk)
    cast(list[dict[str, object]], _organisation(negative)["teams"])[0]["size"] = -1
    coerced = copy.deepcopy(sdk)
    cast(list[dict[str, object]], _organisation(coerced)["teams"])[0]["size"] = "400"

    with pytest.raises(ValidationError):
        parse_source(sdk, SourceVintage.TOPOLOGY_HEADCOUNT_V1)
    with pytest.raises(ValidationError):
        parse_source(topology, SourceVintage.SDK_SIZE_V1)
    with pytest.raises(ValidationError):
        parse_source(mixed, SourceVintage.SDK_SIZE_V1)
    with pytest.raises(ValidationError):
        parse_source(negative, SourceVintage.SDK_SIZE_V1)
    with pytest.raises(ValidationError):
        parse_source(coerced, SourceVintage.SDK_SIZE_V1)
    with pytest.raises(ValueError, match="not-a-vintage"):
        parse_source(sdk, "not-a-vintage")


def test_humans_fixture_emits_valid_import_and_split_compiled_artifacts(
    tmp_path: Path,
) -> None:
    run_adapter(
        payload=_json_fixture("sdk-size-v1-humans.json"),
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )

    imported = EnterpriseIdentityAccessImportV1.model_validate_json(
        _single_path(tmp_path, IMPORT_SUFFIX).read_bytes()
    )
    public = EnterpriseIdentityAccessUniverseV1.model_validate_json(
        _single_path(tmp_path, PUBLIC_SUFFIX).read_bytes()
    )
    truth = EnterpriseCanonicalBindingTruthV1.model_validate_json(
        _single_path(tmp_path, TRUTH_SUFFIX).read_bytes()
    )
    report = _report(tmp_path)

    assert len(imported.blueprint.tenants) == 1
    assert len(imported.blueprint.organisations) == 1
    assert imported.blueprint.populations
    assert {item.population_kind.value for item in imported.blueprint.populations} == {
        "employee"
    }
    assert len(public.tenants) == 1
    assert len(public.organisations) == 1
    assert public.principals
    assert SHA256_RE.fullmatch(truth.identity_access_universe_digest.value)
    assert report["schema_version"] == "1.0.0"
    assert report["source_vintage"] == SourceVintage.SDK_SIZE_V1
    assert _gap_codes(report) >= {
        "ignored_source_population_field",
        "ownership_widened_to_team_population",
        "unexpressed_region_metadata",
        "unexpressed_service_classification",
    }
    assert _single_path(tmp_path, PUBLIC_SUFFIX) != _single_path(tmp_path, TRUTH_SUFFIX)
    compiled_root = _single_path(tmp_path, PUBLIC_SUFFIX).parents[1]
    assert load_public_enterprise_identity_access_universe(compiled_root) == public
    assert load_evaluator_enterprise_canonical_binding_truth(compiled_root) == truth


def test_identical_inputs_and_config_produce_identical_relative_bytes(
    tmp_path: Path,
) -> None:
    payload = _json_fixture("sdk-size-v1-humans.json")
    first = tmp_path / "first"
    second = tmp_path / "second"

    run_adapter(
        payload=payload,
        vintage="sdk-size-v1",
        output_dir=first,
        config=_config(),
    )
    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=second,
        config=_config(),
    )

    assert _files(first) == _files(second)


def test_source_size_is_ignored_and_fixed_mix_policy_sets_population_counts(
    tmp_path: Path,
) -> None:
    run_adapter(
        payload=_json_fixture("sdk-size-v1-humans.json"),
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )

    document = cast(
        dict[str, object],
        json.loads(_single_path(tmp_path, IMPORT_SUFFIX).read_text(encoding="utf-8")),
    )
    blueprint = cast(dict[str, object], document["blueprint"])
    populations = cast(list[dict[str, object]], blueprint["populations"])
    counts = [cast(int, item["count"]) for item in populations]
    report = _report(tmp_path)

    assert sorted(counts) == [16, 20, 24]
    assert report["population_policy_version"] == "eads-human-population-policy-v1"
    outcomes = cast(list[dict[str, object]], report["outcomes"])
    assert outcomes[0]["raw_population"] == sum(counts)


@pytest.mark.parametrize(
    ("team_type", "expected_count"),
    [("product", 24), ("operations", 20), ("control", 16)],
)
def test_population_policy_binds_counts_to_team_type(
    tmp_path: Path,
    team_type: str,
    expected_count: int,
) -> None:
    payload = _json_fixture("sdk-size-v1-humans.json")
    organisation = _organisation(payload)
    teams = cast(list[dict[str, object]], organisation["teams"])
    selected_team = next(team for team in teams if team["team_type"] == team_type)
    services = cast(list[dict[str, object]], organisation["services"])
    service = services[0]
    service["owning_team_id"] = selected_team["team_id"]
    organisation["teams"] = [selected_team]
    organisation["services"] = [service]
    organisation["ownerships"] = [
        {
            "team_id": selected_team["team_id"],
            "service_id": service["service_id"],
            "relationship": "owner",
        }
    ]
    output = tmp_path / team_type
    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=output,
        config=_config(),
    )
    imported = EnterpriseIdentityAccessImportV1.model_validate_json(
        _single_path(output, IMPORT_SUFFIX).read_bytes()
    )
    assert tuple(item.count for item in imported.blueprint.populations) == (
        expected_count,
    )


@pytest.mark.parametrize(
    ("fixture_name", "vintage", "field"),
    [
        ("sdk-size-v1-humans.json", SourceVintage.SDK_SIZE_V1, "size"),
        (
            "topology-headcount-v1-anchor.yaml",
            SourceVintage.TOPOLOGY_HEADCOUNT_V1,
            "headcount",
        ),
    ],
)
def test_compiled_outputs_ignore_source_population_measurements(
    tmp_path: Path,
    fixture_name: str,
    vintage: SourceVintage,
    field: str,
) -> None:
    payload = (
        _yaml_fixture(fixture_name)
        if fixture_name.endswith(".yaml")
        else _json_fixture(fixture_name)
    )
    changed = copy.deepcopy(payload)
    for team in cast(list[dict[str, object]], _organisation(changed)["teams"]):
        team[field] = 7
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_adapter(
        payload=payload,
        vintage=vintage,
        output_dir=first,
        config=_config(),
    )
    run_adapter(
        payload=changed,
        vintage=vintage,
        output_dir=second,
        config=_config(),
    )
    first_files = _files(first)
    second_files = _files(second)
    assert {
        path: content
        for path, content in first_files.items()
        if path != REPORT_PATH.as_posix()
    } == {
        path: content
        for path, content in second_files.items()
        if path != REPORT_PATH.as_posix()
    }


def test_population_cap_declares_proportional_downscaling_deterministically(
    tmp_path: Path,
) -> None:
    payload = _json_fixture("sdk-size-v1-humans.json")
    first = tmp_path / "first"
    second = tmp_path / "second"

    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=first,
        config=_config(max_principals=7),
    )
    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=second,
        config=_config(max_principals=7),
    )

    report = _report(first)
    outcomes = cast(list[dict[str, object]], report["outcomes"])
    downscale = cast(dict[str, object], outcomes[0]["downscale"])
    assert cast(int, outcomes[0]["raw_population"]) > 7
    assert outcomes[0]["emitted_population"] == 7
    assert downscale["applied"] is True
    assert downscale["emitted_total"] == 7
    assert downscale["numerator"] == 7
    assert cast(int, downscale["denominator"]) > 7
    imported = EnterpriseIdentityAccessImportV1.model_validate_json(
        _single_path(first, IMPORT_SUFFIX).read_bytes()
    )
    assert sorted(item.count for item in imported.blueprint.populations) == [2, 2, 3]
    assert _files(first) == _files(second)


def test_population_cap_below_team_count_fails_with_stable_code(tmp_path: Path) -> None:
    run_adapter(
        payload=_json_fixture("sdk-size-v1-humans.json"),
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(max_principals=2),
    )

    assert _gap_codes(_report(tmp_path)) >= {
        "ignored_source_population_field",
        "population_cap_below_team_count",
        "unexpressed_region_metadata",
        "unexpressed_service_classification",
    }
    _assert_no_organisation_artifacts(tmp_path)


def test_unmapped_service_type_is_sanitized_and_blocks_organisation_artifacts(
    tmp_path: Path,
) -> None:
    payload = _json_fixture("sdk-size-v1-gaps.json")
    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )

    report_bytes = (tmp_path / REPORT_PATH).read_bytes()
    assert "unmapped_service_type" in _gap_codes(_report(tmp_path))
    assert b"Tier 1" not in report_bytes
    assert b"Gap Laboratory Example Ltd" not in report_bytes
    assert b"example-gap-laboratory" not in report_bytes
    _assert_no_organisation_artifacts(tmp_path)


def test_fictionalisation_boundary_removes_vendor_product_and_source_labels(
    tmp_path: Path,
) -> None:
    run_adapter(
        payload=_json_fixture("fictionalisation-boundary.json"),
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )

    combined = b"\n".join(_files(tmp_path).values()).lower()
    forbidden = (
        b"contoso",
        b"okta",
        b"microsoft",
        b"entra",
        b"salesforce",
        b"boundary-input-only",
        b"identity-team",
        b"entra-production",
    )
    assert not any(label in combined for label in forbidden)
    assert _single_path(tmp_path, PUBLIC_SUFFIX).is_file()


def test_private_salt_keys_source_references(tmp_path: Path) -> None:
    payload = _json_fixture("fictionalisation-boundary.json")
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=first,
        config=_config(namespace_salt="a" * 64),
    )
    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=second,
        config=_config(namespace_salt="b" * 64),
    )
    assert _files(first) != _files(second)
    assert b"a" * 64 not in b"".join(_files(first).values())
    assert b"b" * 64 not in b"".join(_files(second).values())


def test_supported_subset_compiles_while_semantic_gaps_are_reported(
    tmp_path: Path,
) -> None:
    payload = _json_fixture("sdk-size-v1-humans.json")
    organisation = _organisation(payload)
    organisation["industry"] = "unknown-vertical"
    domains = cast(list[dict[str, object]], organisation["domains"])
    child = cast(list[dict[str, object]], domains[0]["children"])[0]
    child["children"] = [
        {
            "domain_id": "deep-fourth-level",
            "name": "Deep Fourth Level",
            "children": [],
        }
    ]
    teams = cast(list[dict[str, object]], organisation["teams"])
    teams[2]["team_type"] = "unknown-team-type"
    services = cast(list[dict[str, object]], organisation["services"])
    services[1]["classification"] = None
    ownerships = cast(list[dict[str, object]], organisation["ownerships"])
    ownerships[1]["relationship"] = "informal-custodian"

    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )

    assert _gap_codes(_report(tmp_path)) >= {
        "deep_hierarchy_collapsed",
        "null_classification",
        "unknown_industry",
        "unknown_team_type",
        "unsupported_ownership_semantics",
    }
    public = EnterpriseIdentityAccessUniverseV1.model_validate_json(
        _single_path(tmp_path, PUBLIC_SUFFIX).read_bytes()
    )
    assert public.authorization_targets


def test_owner_divergence_is_explicit(tmp_path: Path) -> None:
    payload = _json_fixture("sdk-size-v1-humans.json")
    organisation = _organisation(payload)
    ownerships = cast(list[dict[str, object]], organisation["ownerships"])
    ownerships[0]["team_id"] = "risk-review"
    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )
    assert "declared_owner_diverges_from_owning_team" in _gap_codes(_report(tmp_path))


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [
        ("domain", "dangling_domain_reference"),
        ("region", "dangling_region_reference"),
        ("team", "dangling_team_reference"),
        ("service", "dangling_service_reference"),
    ],
)
def test_dangling_references_fail_with_sanitized_stable_codes(
    tmp_path: Path,
    kind: str,
    expected_code: str,
) -> None:
    payload = _json_fixture("sdk-size-v1-humans.json")
    organisation = _organisation(payload)
    teams = cast(list[dict[str, object]], organisation["teams"])
    services = cast(list[dict[str, object]], organisation["services"])
    ownerships = cast(list[dict[str, object]], organisation["ownerships"])
    if kind == "domain":
        teams[0]["domain_id"] = "raw-missing-domain"
    elif kind == "region":
        teams[0]["region_ids"] = ["raw-missing-region"]
    elif kind == "team":
        services[0]["owning_team_id"] = "raw-missing-team"
    else:
        ownerships[0]["service_id"] = "raw-missing-service"

    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )

    report_bytes = (tmp_path / REPORT_PATH).read_bytes()
    assert expected_code in _gap_codes(_report(tmp_path))
    assert b"raw-missing" not in report_bytes
    _assert_no_organisation_artifacts(tmp_path)


def test_bian_like_organisation_is_excluded(tmp_path: Path) -> None:
    payload = _json_fixture("sdk-size-v1-humans.json")
    organisation = _organisation(payload)
    organisation["organisation_id"] = "bian-source-row"
    organisation["name"] = "BIAN Service Landscape"
    organisation["industry"] = "bian"

    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )

    report_bytes = (tmp_path / REPORT_PATH).read_bytes()
    assert "bian_framework_excluded" in _gap_codes(_report(tmp_path))
    assert b"BIAN Service Landscape" not in report_bytes
    assert b"bian-source-row" not in report_bytes
    _assert_no_organisation_artifacts(tmp_path)


def test_nested_bian_domain_is_excluded(tmp_path: Path) -> None:
    payload = _json_fixture("sdk-size-v1-humans.json")
    domains = cast(list[dict[str, object]], _organisation(payload)["domains"])
    children = cast(list[dict[str, object]], domains[0]["children"])
    children[0]["domain_id"] = "bian_core"
    children[0]["name"] = "Service Domain Landscape"
    report = run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )
    assert report.status == "failed"
    assert report.error_code == "no_organisations_compiled"
    assert "bian_framework_excluded" in _gap_codes(_report(tmp_path))
    _assert_no_organisation_artifacts(tmp_path)


@pytest.mark.parametrize(
    ("fixture_name", "vintage"),
    [
        ("sdk-size-v1-humans.json", "sdk-size-v1"),
        ("topology-headcount-v1-anchor.yaml", "topology-headcount-v1"),
    ],
)
def test_cli_accepts_json_and_yaml_with_explicit_vintage(
    tmp_path: Path,
    fixture_name: str,
    vintage: str,
) -> None:
    output = tmp_path / vintage
    salt_file = tmp_path / "namespace-salt"
    salt_file.write_text("a" * 64 + "\n", encoding="ascii")
    result = _run_cli(
        "--source",
        str(FIXTURES / fixture_name),
        "--vintage",
        vintage,
        "--output",
        str(output),
        "--seed",
        "20260808",
        "--namespace-salt-file",
        str(salt_file),
    )

    assert result.returncode == 0, result.stderr
    assert (output / REPORT_PATH).is_file()
    assert _single_path(output, PUBLIC_SUFFIX).is_file()


def test_cli_requires_explicit_vintage(tmp_path: Path) -> None:
    salt_file = tmp_path / "namespace-salt"
    salt_file.write_text("a" * 64 + "\n", encoding="ascii")
    result = _run_cli(
        "--source",
        str(FIXTURES / "sdk-size-v1-humans.json"),
        "--output",
        str(tmp_path / "output"),
        "--seed",
        "20260808",
        "--namespace-salt-file",
        str(salt_file),
    )

    assert result.returncode != 0
    assert "vintage" in result.stderr.lower()


@pytest.mark.parametrize("contents", ["[1, 2, 3]\n", "{not valid json\n"])
def test_cli_rejects_non_mapping_and_malformed_input(
    tmp_path: Path,
    contents: str,
) -> None:
    source = tmp_path / "invalid.json"
    source.write_text(contents, encoding="utf-8")
    salt_file = tmp_path / "namespace-salt"
    salt_file.write_text("a" * 64 + "\n", encoding="ascii")

    result = _run_cli(
        "--source",
        str(source),
        "--vintage",
        "sdk-size-v1",
        "--output",
        str(tmp_path / "output"),
        "--seed",
        "20260808",
        "--namespace-salt-file",
        str(salt_file),
    )

    assert result.returncode != 0


def test_gap_report_has_digest_only_portable_artifact_paths_and_no_run_metadata(
    tmp_path: Path,
) -> None:
    run_adapter(
        payload=_json_fixture("sdk-size-v1-humans.json"),
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )

    report = _report(tmp_path)
    digest = cast(str, report["canonical_source_payload_digest"])
    outcomes = cast(list[dict[str, object]], report["outcomes"])
    artifact_paths = cast(list[str], outcomes[0]["artifacts"])
    serialized = (tmp_path / REPORT_PATH).read_text(encoding="utf-8").lower()

    assert SHA256_RE.fullmatch(digest)
    assert artifact_paths
    assert artifact_paths == sorted(artifact_paths)
    assert all(not Path(path).is_absolute() for path in artifact_paths)
    assert all((tmp_path / path).is_file() for path in artifact_paths)
    assert str(FIXTURES).lower() not in serialized
    assert "source_path" not in serialized
    assert "salt" not in serialized
    assert "timestamp" not in serialized


def test_schema_invalid_source_retains_canonical_digest(tmp_path: Path) -> None:
    payload: dict[str, object] = {"organisations": []}
    report = run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )
    digest = report.canonical_source_payload_digest
    assert report.error_code == "source_validation_failed"
    assert SHA256_RE.fullmatch(digest)
    assert digest != hashlib.sha256(b"invalid-json-native-payload").hexdigest()
    assert _report(tmp_path)["canonical_source_payload_digest"] == digest


def test_non_json_native_source_uses_sanitized_failure_digest(tmp_path: Path) -> None:
    report = run_adapter(
        payload={"organisations": object()},
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=tmp_path,
        config=_config(),
    )
    assert report.error_code == "source_payload_not_json_compatible"
    assert (
        report.canonical_source_payload_digest
        == hashlib.sha256(b"invalid-json-native-payload").hexdigest()
    )


def test_existing_output_root_is_refused_without_changing_bytes(tmp_path: Path) -> None:
    payload = _json_fixture("sdk-size-v1-humans.json")
    output = tmp_path / "output"
    run_adapter(
        payload=payload,
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=output,
        config=_config(),
    )
    before = _files(output)
    with pytest.raises(FileExistsError, match="must be absent or an empty directory"):
        run_adapter(
            payload=payload,
            vintage=SourceVintage.SDK_SIZE_V1,
            output_dir=output,
            config=_config(max_principals=2),
        )
    assert _files(output) == before


@pytest.mark.parametrize(
    "contents",
    [
        "organisations:\n  - &row {organisation_id: x}\n  - *row\n",
        "organisations: []\norganisations: []\n",
        "value: 2026-08-08\n",
        "value: .nan\n",
    ],
)
def test_cli_rejects_non_json_compatible_yaml(
    tmp_path: Path,
    contents: str,
) -> None:
    source = tmp_path / "invalid.yaml"
    source.write_text(contents, encoding="utf-8")
    salt_file = tmp_path / "namespace-salt"
    salt_file.write_text("a" * 64 + "\n", encoding="ascii")
    result = _run_cli(
        "--source",
        str(source),
        "--vintage",
        "sdk-size-v1",
        "--output",
        str(tmp_path / "output"),
        "--seed",
        "20260808",
        "--namespace-salt-file",
        str(salt_file),
    )
    assert result.returncode == 2
    assert not (tmp_path / "output").exists()
