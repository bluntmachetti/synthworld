from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from collections.abc import ItemsView, Iterator, Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from examples.eads_adapter import (
    ADAPTER_VERSION,
    AdapterCode,
    AdapterConfig,
    AdapterRunReport,
    ArtifactKind,
    ArtifactRecord,
    ArtifactVisibility,
    parse_source,
    run_adapter,
)
from examples.eads_adapter import __main__ as cli_module
from examples.eads_adapter import adapter as adapter_module
from examples.eads_adapter.models import (
    MAX_ORGANISATIONS,
    MAX_SOURCE_TEXT_BYTES,
    SourceVintage,
)
from synthworld.enterprise.serialization import (
    load_public_enterprise_identity_access_universe,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "examples" / "eads_adapter" / "fixtures" / "fictionalisation-boundary.json"
)
REPORT_RELATIVE_PATH = Path("private/reports/eads-adapter-gap-report.json")
NAMESPACE_SALT = "a" * 64
REPORT_SCHEMA_VERSION = "2.0.0"
EXPECTED_ADAPTER_VERSION = "repository-eads-shaped-structure-v1"
MAX_SEED = adapter_module.MAX_SEED


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _source_payload() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_bytes())
    assert isinstance(payload, dict)
    return payload


def _config(
    *,
    seed: int = 20260809,
    max_principals_per_organisation: int = 128,
    namespace_salt: str = NAMESPACE_SALT,
) -> AdapterConfig:
    return AdapterConfig(
        max_principals_per_organisation=max_principals_per_organisation,
        namespace_salt=namespace_salt,
        seed=seed,
    )


def _run(
    tmp_path: Path,
    payload: Mapping[str, object] | dict[str, Any] | list[object] | object,
    *,
    name: str = "output",
    config: AdapterConfig | None = None,
) -> tuple[Path, AdapterRunReport]:
    output_root = tmp_path / name
    report = run_adapter(
        payload=cast(Mapping[str, object], payload),
        vintage=SourceVintage.SDK_SIZE_V1,
        output_dir=output_root,
        config=config or _config(),
    )
    return output_root, report


def _report_from_disk(output_root: Path) -> AdapterRunReport:
    return AdapterRunReport.model_validate_json(
        (output_root / REPORT_RELATIVE_PATH).read_bytes(),
        strict=True,
    )


def _all_artifacts(report: AdapterRunReport) -> tuple[ArtifactRecord, ...]:
    return (
        report.evaluator_artifacts + report.private_artifacts + report.public_artifacts
    )


def _tree_bytes(root: Path, *, include_report: bool = True) -> dict[str, bytes]:
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    if not include_report:
        files.pop(REPORT_RELATIVE_PATH.as_posix(), None)
    return files


def _first_organisation(payload: dict[str, Any]) -> dict[str, Any]:
    organisations = payload["organisations"]
    assert isinstance(organisations, list)
    organisation = organisations[0]
    assert isinstance(organisation, dict)
    return organisation


def _duplicate_organisation(
    payload: dict[str, Any],
    *,
    organisation_id: str,
) -> dict[str, Any]:
    duplicate = copy.deepcopy(_first_organisation(payload))
    duplicate["organisation_id"] = organisation_id
    duplicate["name"] = f"Fictional Canary Organisation {organisation_id}"
    payload["organisations"].append(duplicate)
    return duplicate


def _reverse_mapping_order(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _reverse_mapping_order(item)
            for key, item in reversed(tuple(value.items()))
        }
    if isinstance(value, list):
        return [_reverse_mapping_order(item) for item in value]
    return value


def _reverse_source_collections(value: object) -> object:
    if isinstance(value, dict):
        return {key: _reverse_source_collections(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_reverse_source_collections(item) for item in reversed(value)]
    return value


def _write_cli_inputs(
    tmp_path: Path,
    *,
    source_bytes: bytes | None = None,
    source_suffix: str = ".json",
    salt_bytes: bytes | None = None,
) -> tuple[Path, Path]:
    source = tmp_path / f"source{source_suffix}"
    source.write_bytes(
        source_bytes
        if source_bytes is not None
        else _canonical_json_bytes(_source_payload())
    )
    salt = tmp_path / "namespace-salt.txt"
    salt.write_bytes(
        salt_bytes if salt_bytes is not None else f"{NAMESPACE_SALT}\n".encode()
    )
    return source, salt


def _cli_args(
    source: Path,
    salt: Path,
    output_root: Path,
    *,
    seed: str = "20260809",
    maximum: str = "128",
) -> list[str]:
    return [
        "--source",
        str(source),
        "--vintage",
        SourceVintage.SDK_SIZE_V1.value,
        "--namespace-salt-file",
        str(salt),
        "--output",
        str(output_root),
        "--seed",
        seed,
        "--max-principals-per-organisation",
        maximum,
    ]


def _assert_closed_cli_error(
    capsys: pytest.CaptureFixture[str],
    *,
    expected_category: str,
    exit_code: int,
    sensitive_fragments: tuple[str, ...] = (),
) -> None:
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"eads-shaped-adapter: {expected_category}\n"
    for fragment in sensitive_fragments:
        if fragment.strip():
            assert fragment not in captured.err
    assert exit_code in {2, 3, 4, 5, 6}


def _validation_payload(report: AdapterRunReport) -> dict[str, Any]:
    return report.model_dump()


class _StatefulSource(Mapping[str, object]):
    """Yield one stable snapshot, then make a second read observably invalid."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.exhausted = False

    def __getitem__(self, key: str) -> object:
        return self.payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.payload)

    def __len__(self) -> int:
        return len(self.payload)

    def items(self) -> ItemsView[str, object]:
        def stateful_items() -> Iterator[tuple[str, object]]:
            stable_items = tuple(self.payload.items())
            yield from stable_items
            self.payload["organisations"] = [object()]
            self.exhausted = True

        return cast(ItemsView[str, object], stateful_items())


def test_fixture_is_safely_fictional_and_current_contract_compiles(
    tmp_path: Path,
) -> None:
    fixture_bytes = FIXTURE.read_bytes()
    assert b"Fictional Canary Organisation" in fixture_bytes
    assert b"fictional-canary-region" in fixture_bytes
    assert b"fictional-canary-identity" in fixture_bytes
    assert b"fictional-canary-team" in fixture_bytes
    assert b"fictional-canary-service" in fixture_bytes

    output_root, report = _run(tmp_path, _source_payload())

    assert report.schema_version == REPORT_SCHEMA_VERSION
    assert report.adapter_version == EXPECTED_ADAPTER_VERSION == ADAPTER_VERSION
    assert report.repository_only is True
    assert report.network_access is False
    assert report.real_eads_compatibility is False
    assert report.status.value == "succeeded"
    assert report.error_code is None
    assert _report_from_disk(output_root) == report


def test_fictional_names_do_not_drive_mapping_or_exclusion(tmp_path: Path) -> None:
    payload = _source_payload()
    organisation = _first_organisation(payload)
    organisation["name"] = "Fictional Canary Organisation"
    for collection_name in ("domains", "regions", "services", "teams"):
        records = organisation[collection_name]
        for index, record in enumerate(records):
            record["name"] = f"Fictional Canary {collection_name} {index}"

    _, report = _run(tmp_path, payload)

    assert report.status.value == "succeeded"
    assert len(report.outcomes) == 1
    assert report.outcomes[0].status.value == "compiled"


def test_mapping_and_downscale_declarations_are_explicit(tmp_path: Path) -> None:
    payload = _source_payload()
    _, report = _run(
        tmp_path,
        payload,
        config=_config(max_principals_per_organisation=16),
    )

    outcome = report.outcomes[0]
    assert outcome.downscale is not None
    declaration = outcome.downscale.model_dump(mode="json")
    assert report.max_principals_per_organisation == 16
    assert any(value == 16 for value in declaration.values())
    assert outcome.artifacts
    assert not any(
        gap.code is AdapterCode.NO_SUPPORTED_ACCESS_MAPPING for gap in report.gaps
    )


@pytest.mark.parametrize("seed", [-1, MAX_SEED + 1, True, 1.5])
def test_config_rejects_invalid_seed(seed: object) -> None:
    with pytest.raises(ValidationError):
        AdapterConfig.model_validate(
            {
                "max_principals_per_organisation": 16,
                "namespace_salt": NAMESPACE_SALT,
                "seed": seed,
            },
            strict=True,
        )


@pytest.mark.parametrize("seed", [0, MAX_SEED])
def test_config_accepts_seed_contract_boundaries(seed: int) -> None:
    assert _config(seed=seed).seed == seed


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("namespace_salt", "A" * 64),
        ("namespace_salt", "a" * 63),
        ("namespace_salt", "g" * 64),
        ("max_principals_per_organisation", 0),
        ("max_principals_per_organisation", 1_000_001),
    ],
)
def test_config_rejects_invalid_salt_and_population_cap(
    field: str,
    value: object,
) -> None:
    config: dict[str, object] = {
        "max_principals_per_organisation": 16,
        "namespace_salt": NAMESPACE_SALT,
        "seed": 0,
    }
    config[field] = value
    with pytest.raises(ValidationError):
        AdapterConfig.model_validate(config, strict=True)


def test_source_semantic_discriminators_are_ascii_only() -> None:
    payload = _source_payload()
    organisation = _first_organisation(payload)
    organisation["services"][0]["service_type"] = "ficti\u00f3nal-api"

    with pytest.raises(ValidationError, match="ascii"):
        parse_source(payload, SourceVintage.SDK_SIZE_V1)


def test_source_descriptive_strings_allow_nfc_unicode() -> None:
    payload = _source_payload()
    _first_organisation(payload)["name"] = "Fictional Caf\u00e9 Organisation"

    source = parse_source(payload, SourceVintage.SDK_SIZE_V1)

    assert source.organisations[0].name == "Fictional Caf\u00e9 Organisation"


def test_api_rejects_non_nfc_and_byte_oversized_source_strings(
    tmp_path: Path,
) -> None:
    non_nfc = _source_payload()
    _first_organisation(non_nfc)["name"] = "Cafe\u0301"
    _, non_nfc_report = _run(tmp_path, non_nfc, name="non-nfc")
    assert non_nfc_report.error_code is AdapterCode.SOURCE_TEXT_NOT_NFC

    oversized = _source_payload()
    _first_organisation(oversized)["name"] = "x" * (MAX_SOURCE_TEXT_BYTES + 1)
    _, oversized_report = _run(tmp_path, oversized, name="oversized-text")
    assert oversized_report.error_code is AdapterCode.SOURCE_TEXT_BYTE_LIMIT_EXCEEDED


def test_api_snapshots_mutable_payload_without_mutating_it(tmp_path: Path) -> None:
    payload = _source_payload()
    original = copy.deepcopy(payload)

    _, report = _run(tmp_path, payload)

    assert report.status.value == "succeeded"
    assert payload == original


def test_api_uses_one_canonical_snapshot_for_digest_and_parse(tmp_path: Path) -> None:
    payload = _source_payload()
    expected_digest = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    stateful = _StatefulSource(payload)

    _, report = _run(tmp_path, stateful)

    assert stateful.exhausted is True
    assert stateful.payload["organisations"] == [stateful.payload["organisations"][0]]
    assert not isinstance(stateful.payload["organisations"][0], dict)
    assert report.status.value == "succeeded"
    assert report.canonical_source_payload_digest == expected_digest


@pytest.mark.parametrize("unsupported", [object(), {"not": {1, 2}}])
def test_api_rejects_non_json_payloads(
    tmp_path: Path,
    unsupported: object,
) -> None:
    _, report = _run(tmp_path, unsupported, name=f"non-json-{id(unsupported)}")

    assert report.status.value == "failed"
    assert report.error_code is AdapterCode.SOURCE_PAYLOAD_NOT_JSON_COMPATIBLE
    assert report.outcomes == ()


def test_api_rejects_cyclic_payload_without_recursing_forever(tmp_path: Path) -> None:
    payload = _source_payload()
    cycle: list[object] = []
    cycle.append(cycle)
    payload["cycle"] = cycle

    _, report = _run(tmp_path, payload)

    assert report.status.value == "failed"
    assert report.error_code is AdapterCode.SOURCE_DEPTH_LIMIT_EXCEEDED


def test_api_enforces_node_depth_and_snapshot_byte_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapter_module, "MAX_SOURCE_NODES", 8)
    _, nodes = _run(tmp_path, _source_payload(), name="nodes")
    assert nodes.error_code is AdapterCode.SOURCE_NODE_LIMIT_EXCEEDED

    monkeypatch.setattr(adapter_module, "MAX_SOURCE_NODES", 100_000)
    monkeypatch.setattr(adapter_module, "MAX_SOURCE_DEPTH", 2)
    _, depth = _run(tmp_path, _source_payload(), name="depth")
    assert depth.error_code is AdapterCode.SOURCE_DEPTH_LIMIT_EXCEEDED

    monkeypatch.setattr(adapter_module, "MAX_SOURCE_DEPTH", 64)
    monkeypatch.setattr(adapter_module, "MAX_SOURCE_BYTES", 16)
    _, size = _run(tmp_path, _source_payload(), name="bytes")
    assert size.error_code is AdapterCode.SOURCE_BYTE_LIMIT_EXCEEDED


def test_api_enforces_source_collection_limit(tmp_path: Path) -> None:
    payload = _source_payload()
    template = _first_organisation(payload)
    payload["organisations"] = []
    for index in range(MAX_ORGANISATIONS + 1):
        organisation = copy.deepcopy(template)
        organisation["id"] = f"fictional-org-{index:04d}"
        payload["organisations"].append(organisation)

    _, report = _run(tmp_path, payload)

    assert report.status.value == "failed"
    assert report.error_code is AdapterCode.SOURCE_VALIDATION_FAILED


def test_run_requires_an_absent_output_root(tmp_path: Path) -> None:
    for kind in ("file", "directory", "symlink"):
        output_root = tmp_path / kind
        if kind == "file":
            output_root.write_text("occupied", encoding="utf-8")
        elif kind == "directory":
            output_root.mkdir()
        else:
            target = tmp_path / "symlink-target"
            target.mkdir(exist_ok=True)
            try:
                output_root.symlink_to(target, target_is_directory=True)
            except (NotImplementedError, OSError):
                pytest.skip("platform cannot create directory symlinks")
        with pytest.raises(FileExistsError):
            run_adapter(
                payload=_source_payload(),
                vintage=SourceVintage.SDK_SIZE_V1,
                output_dir=output_root,
                config=_config(),
            )


def test_cli_success_uses_absent_output_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, salt = _write_cli_inputs(tmp_path)
    output_root = tmp_path / "output"

    exit_code = cli_module.main(_cli_args(source, salt, output_root))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""
    assert _report_from_disk(output_root).status.value == "succeeded"


def test_cli_returns_one_for_closed_report_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = _source_payload()
    _first_organisation(payload)["services"][0]["service_type"] = "unsupported"
    source, salt = _write_cli_inputs(
        tmp_path,
        source_bytes=_canonical_json_bytes(payload),
    )
    output_root = tmp_path / "output"

    exit_code = cli_module.main(_cli_args(source, salt, output_root))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == ""
    assert _report_from_disk(output_root).status.value == "failed"


@pytest.mark.parametrize(
    "source_bytes",
    [
        b'{"organisations":[],"organisations":[]}\n',
        b'{"nonfinite":NaN}\n',
        b'{"nonfinite":Infinity}\n',
        b"\xff\n",
        b'{"organisations":[]} trailing\n',
    ],
)
def test_cli_json_rejects_duplicate_nonfinite_utf8_and_suffix_content(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    source_bytes: bytes,
) -> None:
    source, salt = _write_cli_inputs(tmp_path, source_bytes=source_bytes)

    exit_code = cli_module.main(
        _cli_args(source, salt, tmp_path / "output"),
    )

    _assert_closed_cli_error(
        capsys,
        expected_category="source",
        exit_code=exit_code,
        sensitive_fragments=(str(source), source_bytes[:8].decode("ascii", "ignore")),
    )
    assert exit_code == 2


def test_cli_rejects_unsupported_source_suffix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, salt = _write_cli_inputs(tmp_path, source_suffix=".txt")

    exit_code = cli_module.main(_cli_args(source, salt, tmp_path / "output"))

    _assert_closed_cli_error(
        capsys,
        expected_category="source",
        exit_code=exit_code,
        sensitive_fragments=(str(source),),
    )
    assert exit_code == 2


@pytest.mark.parametrize(
    "yaml_bytes",
    [
        b"organisations: []\norganisations: []\n",
        b"value: &value []\norganisations: *value\n",
        b"organisations: !fictional []\n",
        b"1: value\norganisations: []\n",
    ],
)
def test_cli_yaml_rejects_duplicate_alias_tag_and_nonstring_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    yaml_bytes: bytes,
) -> None:
    source, salt = _write_cli_inputs(
        tmp_path,
        source_bytes=yaml_bytes,
        source_suffix=".yaml",
    )

    exit_code = cli_module.main(_cli_args(source, salt, tmp_path / "output"))

    _assert_closed_cli_error(
        capsys,
        expected_category="source",
        exit_code=exit_code,
        sensitive_fragments=(str(source),),
    )
    assert exit_code == 2


def test_cli_yaml_enforces_node_and_depth_limits(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, salt = _write_cli_inputs(
        tmp_path,
        source_bytes=b"a:\n  b:\n    c:\n      d: value\n",
        source_suffix=".yaml",
    )
    monkeypatch.setattr(cli_module, "MAX_SOURCE_DEPTH", 2)
    depth_exit = cli_module.main(_cli_args(source, salt, tmp_path / "depth"))
    _assert_closed_cli_error(
        capsys,
        expected_category="source",
        exit_code=depth_exit,
    )
    assert depth_exit == 2

    monkeypatch.setattr(cli_module, "MAX_SOURCE_DEPTH", 64)
    monkeypatch.setattr(cli_module, "MAX_SOURCE_NODES", 2)
    node_exit = cli_module.main(_cli_args(source, salt, tmp_path / "nodes"))
    _assert_closed_cli_error(
        capsys,
        expected_category="source",
        exit_code=node_exit,
    )
    assert node_exit == 2


def test_cli_json_enforces_api_node_depth_string_and_collection_limits(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, salt = _write_cli_inputs(tmp_path)

    monkeypatch.setattr(adapter_module, "MAX_SOURCE_NODES", 8)
    node_exit = cli_module.main(_cli_args(source, salt, tmp_path / "nodes"))
    assert node_exit == 1
    assert (
        _report_from_disk(tmp_path / "nodes").error_code
        is AdapterCode.SOURCE_NODE_LIMIT_EXCEEDED
    )

    monkeypatch.setattr(adapter_module, "MAX_SOURCE_NODES", 100_000)
    monkeypatch.setattr(adapter_module, "MAX_SOURCE_DEPTH", 2)
    depth_exit = cli_module.main(_cli_args(source, salt, tmp_path / "depth"))
    assert depth_exit == 1
    assert (
        _report_from_disk(tmp_path / "depth").error_code
        is AdapterCode.SOURCE_DEPTH_LIMIT_EXCEEDED
    )

    monkeypatch.setattr(adapter_module, "MAX_SOURCE_DEPTH", 64)
    payload = _source_payload()
    _first_organisation(payload)["name"] = "x" * (MAX_SOURCE_TEXT_BYTES + 1)
    source.write_bytes(_canonical_json_bytes(payload))
    string_exit = cli_module.main(_cli_args(source, salt, tmp_path / "string"))
    assert string_exit == 1
    assert (
        _report_from_disk(tmp_path / "string").error_code
        is AdapterCode.SOURCE_TEXT_BYTE_LIMIT_EXCEEDED
    )

    payload = _source_payload()
    template = _first_organisation(payload)
    payload["organisations"] = []
    for index in range(MAX_ORGANISATIONS + 1):
        organisation = copy.deepcopy(template)
        organisation["id"] = f"fictional-cli-org-{index:04d}"
        payload["organisations"].append(organisation)
    source.write_bytes(_canonical_json_bytes(payload))
    collection_exit = cli_module.main(
        _cli_args(source, salt, tmp_path / "collection"),
    )
    assert collection_exit == 1
    assert (
        _report_from_disk(tmp_path / "collection").error_code
        is AdapterCode.SOURCE_VALIDATION_FAILED
    )
    assert capsys.readouterr().err == ""


def test_cli_resource_limit_is_closed_and_distinct(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, salt = _write_cli_inputs(tmp_path)
    monkeypatch.setattr(cli_module, "MAX_SOURCE_BYTES", 8)

    exit_code = cli_module.main(_cli_args(source, salt, tmp_path / "output"))

    _assert_closed_cli_error(
        capsys,
        expected_category="resource",
        exit_code=exit_code,
        sensitive_fragments=(str(source),),
    )
    assert exit_code == 6


@pytest.mark.parametrize("seed", ["-1", str(MAX_SEED + 1), "not-an-integer"])
def test_cli_seed_validation_is_closed_config_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    seed: str,
) -> None:
    source, salt = _write_cli_inputs(tmp_path)

    exit_code = cli_module.main(
        _cli_args(source, salt, tmp_path / "output", seed=seed),
    )

    _assert_closed_cli_error(
        capsys,
        expected_category="config",
        exit_code=exit_code,
        sensitive_fragments=(seed, str(salt)),
    )
    assert exit_code == 3


@pytest.mark.parametrize(
    "salt_bytes",
    [b"a" * 63 + b"\n", b"A" * 64 + b"\n", b"g" * 64 + b"\n", b"a" * 64 + b"\n\n"],
)
def test_cli_salt_validation_is_closed_config_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    salt_bytes: bytes,
) -> None:
    source, salt = _write_cli_inputs(tmp_path, salt_bytes=salt_bytes)

    exit_code = cli_module.main(_cli_args(source, salt, tmp_path / "output"))

    _assert_closed_cli_error(
        capsys,
        expected_category="config",
        exit_code=exit_code,
        sensitive_fragments=(str(salt), salt_bytes.decode("ascii", "ignore").strip()),
    )
    assert exit_code == 3


@pytest.mark.parametrize("maximum", ["0", "1000001", "not-an-integer"])
def test_cli_population_config_validation_is_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    maximum: str,
) -> None:
    source, salt = _write_cli_inputs(tmp_path)

    exit_code = cli_module.main(
        _cli_args(source, salt, tmp_path / "output", maximum=maximum),
    )

    _assert_closed_cli_error(
        capsys,
        expected_category="config",
        exit_code=exit_code,
        sensitive_fragments=(maximum,),
    )
    assert exit_code == 3


@pytest.mark.parametrize("primitive", ["O_NOFOLLOW", "O_NONBLOCK"])
def test_cli_fails_closed_when_path_safety_primitives_are_unavailable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    primitive: str,
) -> None:
    if not hasattr(os, primitive):
        pytest.skip(f"platform does not expose {primitive}")
    source, salt = _write_cli_inputs(tmp_path)
    monkeypatch.delattr(os, primitive)

    exit_code = cli_module.main(_cli_args(source, salt, tmp_path / "output"))

    _assert_closed_cli_error(
        capsys,
        expected_category="path-safety",
        exit_code=exit_code,
    )
    assert exit_code == 4


def test_cli_rejects_source_directory_without_opening_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.json"
    source.mkdir()
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _, salt = _write_cli_inputs(inputs)

    exit_code = cli_module.main(_cli_args(source, salt, tmp_path / "output"))

    _assert_closed_cli_error(
        capsys,
        expected_category="path-safety",
        exit_code=exit_code,
        sensitive_fragments=(str(source),),
    )
    assert exit_code == 4


def test_cli_rejects_source_and_salt_symlinks(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, salt = _write_cli_inputs(tmp_path)
    source_link = tmp_path / "source-link.json"
    salt_link = tmp_path / "salt-link.txt"
    try:
        source_link.symlink_to(source)
        salt_link.symlink_to(salt)
    except (NotImplementedError, OSError):
        pytest.skip("platform cannot create file symlinks")

    source_exit = cli_module.main(
        _cli_args(source_link, salt, tmp_path / "source-output"),
    )
    _assert_closed_cli_error(
        capsys,
        expected_category="path-safety",
        exit_code=source_exit,
        sensitive_fragments=(str(source_link),),
    )
    assert source_exit == 4

    salt_exit = cli_module.main(
        _cli_args(source, salt_link, tmp_path / "salt-output"),
    )
    _assert_closed_cli_error(
        capsys,
        expected_category="path-safety",
        exit_code=salt_exit,
        sensitive_fragments=(str(salt_link),),
    )
    assert salt_exit == 4


def test_cli_rejects_fifo_without_hanging(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("platform cannot create FIFOs")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _, salt = _write_cli_inputs(inputs)
    source = tmp_path / "source.json"
    try:
        os.mkfifo(source)
    except (NotImplementedError, OSError):
        pytest.skip("platform cannot create FIFOs")

    exit_code = cli_module.main(_cli_args(source, salt, tmp_path / "output"))

    _assert_closed_cli_error(
        capsys,
        expected_category="path-safety",
        exit_code=exit_code,
        sensitive_fragments=(str(source),),
    )
    assert exit_code == 4


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_cli_rejects_existing_output_root_as_output_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    kind: str,
) -> None:
    source, salt = _write_cli_inputs(tmp_path)
    output_root = tmp_path / "output"
    if kind == "file":
        output_root.write_text("occupied", encoding="utf-8")
    elif kind == "directory":
        output_root.mkdir()
    else:
        target = tmp_path / "target"
        target.mkdir()
        try:
            output_root.symlink_to(target, target_is_directory=True)
        except (NotImplementedError, OSError):
            pytest.skip("platform cannot create directory symlinks")

    exit_code = cli_module.main(_cli_args(source, salt, output_root))

    _assert_closed_cli_error(
        capsys,
        expected_category="output",
        exit_code=exit_code,
        sensitive_fragments=(str(output_root),),
    )
    assert exit_code == 5


def test_cli_rejects_symlinked_output_parent_as_path_safety_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, salt = _write_cli_inputs(tmp_path)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    try:
        linked_parent.symlink_to(real_parent, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("platform cannot create directory symlinks")

    exit_code = cli_module.main(
        _cli_args(source, salt, linked_parent / "output"),
    )

    _assert_closed_cli_error(
        capsys,
        expected_category="path-safety",
        exit_code=exit_code,
        sensitive_fragments=(str(linked_parent),),
    )
    assert exit_code == 4


def test_cli_rejects_file_output_parent_as_path_safety_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, salt = _write_cli_inputs(tmp_path)
    parent = tmp_path / "not-a-directory"
    parent.write_text("occupied", encoding="utf-8")

    exit_code = cli_module.main(_cli_args(source, salt, parent / "output"))

    _assert_closed_cli_error(
        capsys,
        expected_category="path-safety",
        exit_code=exit_code,
        sensitive_fragments=(str(parent),),
    )
    assert exit_code == 4


def test_duplicate_organisation_is_fail_closed_and_emits_no_artifacts(
    tmp_path: Path,
) -> None:
    payload = _source_payload()
    payload["organisations"].append(copy.deepcopy(_first_organisation(payload)))

    _, report = _run(tmp_path, payload)

    assert report.status.value == "failed"
    assert any(gap.code is AdapterCode.DUPLICATE_ORGANISATION_ID for gap in report.gaps)
    assert all(outcome.status.value == "failed" for outcome in report.outcomes)
    assert _all_artifacts(report) == ()


def test_partial_success_keeps_success_artifacts_and_reports_failure(
    tmp_path: Path,
) -> None:
    payload = _source_payload()
    invalid = _duplicate_organisation(
        payload,
        organisation_id="fictional-canary-unmapped",
    )
    invalid["services"][0]["service_type"] = "unsupported"

    output_root, report = _run(tmp_path, payload)

    assert report.status.value == "failed"
    assert report.error_code is AdapterCode.ORGANISATION_FAILURES_PRESENT
    assert {outcome.status.value for outcome in report.outcomes} == {
        "compiled",
        "failed",
    }
    assert len(_all_artifacts(report)) == 5
    for artifact in _all_artifacts(report):
        assert (output_root / artifact.path).is_file()


def test_zero_success_without_outcomes_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EmptySource:
        organisations: tuple[()] = ()

    monkeypatch.setattr(
        adapter_module, "parse_source", lambda _payload, _vintage: _EmptySource()
    )

    _, report = _run(tmp_path, {"organisations": []})

    assert report.status.value == "failed"
    assert report.error_code is AdapterCode.NO_ORGANISATIONS_COMPILED
    assert report.outcomes == ()
    assert _all_artifacts(report) == ()


@pytest.mark.parametrize(
    ("collection", "expected_code"),
    [
        ("domains", AdapterCode.DUPLICATE_DOMAIN_ID),
        ("regions", AdapterCode.DUPLICATE_REGION_ID),
        ("services", AdapterCode.DUPLICATE_SERVICE_ID),
        ("teams", AdapterCode.DUPLICATE_TEAM_ID),
    ],
)
def test_duplicate_mapping_records_fail_the_organisation(
    tmp_path: Path,
    collection: str,
    expected_code: AdapterCode,
) -> None:
    payload = _source_payload()
    records = _first_organisation(payload)[collection]
    records.append(copy.deepcopy(records[0]))

    _, report = _run(tmp_path, payload)

    assert report.status.value == "failed"
    assert any(gap.code is expected_code for gap in report.gaps)
    assert _all_artifacts(report) == ()


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("industry", "unsupported", AdapterCode.UNKNOWN_INDUSTRY),
        ("scale", "unsupported", AdapterCode.UNKNOWN_SCALE),
    ],
)
def test_unknown_organisation_mapping_values_fail_closed(
    tmp_path: Path,
    field: str,
    value: str,
    expected_code: AdapterCode,
) -> None:
    payload = _source_payload()
    _first_organisation(payload)[field] = value

    _, report = _run(tmp_path, payload)

    assert report.status.value == "failed"
    assert any(gap.code is expected_code for gap in report.gaps)


@pytest.mark.parametrize(
    ("collection", "field", "value", "expected_code"),
    [
        ("teams", "team_type", "unsupported", AdapterCode.UNKNOWN_TEAM_TYPE),
        (
            "services",
            "service_type",
            "unsupported",
            AdapterCode.UNMAPPED_SERVICE_TYPE,
        ),
    ],
)
def test_unknown_record_mapping_values_fail_closed(
    tmp_path: Path,
    collection: str,
    field: str,
    value: str,
    expected_code: AdapterCode,
) -> None:
    payload = _source_payload()
    _first_organisation(payload)[collection][0][field] = value

    _, report = _run(tmp_path, payload)

    assert report.status.value == "failed"
    assert any(gap.code is expected_code for gap in report.gaps)


def test_artifact_inventories_are_exact_typed_and_byte_bound(tmp_path: Path) -> None:
    output_root, report = _run(tmp_path, _source_payload())

    assert report.artifact_set_digest_profile == "path-bound-artifact-records-v1"
    assert len(report.private_artifacts) == 1
    assert len(report.public_artifacts) == 2
    assert len(report.evaluator_artifacts) == 2
    assert {record.kind for record in report.private_artifacts} == {
        ArtifactKind.PRIVATE_IMPORT,
    }
    assert {record.kind for record in report.public_artifacts} == {
        ArtifactKind.PUBLIC_INPUT,
        ArtifactKind.PUBLIC_MANIFEST,
    }
    assert {record.kind for record in report.evaluator_artifacts} == {
        ArtifactKind.EVALUATOR_MANIFEST,
        ArtifactKind.EVALUATOR_TRUTH,
    }
    assert all(
        record.visibility is ArtifactVisibility.PRIVATE
        for record in report.private_artifacts
    )
    assert all(
        record.visibility is ArtifactVisibility.PUBLIC
        for record in report.public_artifacts
    )
    assert all(
        record.visibility is ArtifactVisibility.EVALUATOR
        for record in report.evaluator_artifacts
    )

    inventory_paths = {record.path for record in _all_artifacts(report)}
    disk_paths = set(_tree_bytes(output_root))
    assert disk_paths == inventory_paths | {REPORT_RELATIVE_PATH.as_posix()}
    assert REPORT_RELATIVE_PATH.as_posix() not in inventory_paths
    for record in _all_artifacts(report):
        payload = (output_root / record.path).read_bytes()
        assert record.byte_size == len(payload)
        assert record.sha256 == hashlib.sha256(payload).hexdigest()

    assert report.artifact_set_digest == adapter_module._artifact_set_digest(
        _all_artifacts(report),
    )
    first = _all_artifacts(report)[0]
    moved = first.model_copy(update={"path": f"moved/{first.path}"})
    assert (
        adapter_module._artifact_set_digest(
            (moved, *_all_artifacts(report)[1:]),
        )
        != report.artifact_set_digest
    )


def test_all_json_artifacts_are_canonical_lf_with_one_trailing_newline(
    tmp_path: Path,
) -> None:
    output_root, _ = _run(tmp_path, _source_payload())

    for relative_path, payload in _tree_bytes(output_root).items():
        assert payload.endswith(b"\n"), relative_path
        assert not payload.endswith(b"\n\n"), relative_path
        assert b"\r" not in payload, relative_path
        assert payload == _canonical_json_bytes(json.loads(payload)), relative_path


def test_public_tree_has_no_recursive_evaluator_or_private_leakage(
    tmp_path: Path,
) -> None:
    output_root, report = _run(tmp_path, _source_payload())
    source_payload = _source_payload()
    source_tokens = {
        value
        for value in _walk_json(source_payload)
        if isinstance(value, str) and value.startswith("fictional-canary")
    }
    forbidden_keys = {
        "adapter_config_digest",
        "canonical_binding",
        "canonical_source_payload_digest",
        "expected",
        "gap",
        "namespace_salt",
        "source_truth",
    }

    for record in report.public_artifacts:
        value = json.loads((output_root / record.path).read_bytes())
        for item in _walk_json(value):
            if isinstance(item, str):
                assert item not in source_tokens
                assert item not in {"evaluator", "private"}
        for key in _walk_json_keys(value):
            assert key not in forbidden_keys
            assert "truth" not in key


def _walk_json(value: object) -> Iterator[object]:
    yield value
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def _walk_json_keys(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_json_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json_keys(item)


def test_public_loader_is_independent_of_private_and_evaluator_trees(
    tmp_path: Path,
) -> None:
    output_root, report = _run(tmp_path, _source_payload())
    public_input = next(
        record
        for record in report.public_artifacts
        if record.kind is ArtifactKind.PUBLIC_INPUT
    )
    source_public = (output_root / public_input.path).parent
    public_only_root = tmp_path / "public-only"
    shutil.copytree(source_public, public_only_root / "public")

    universe = load_public_enterprise_identity_access_universe(public_only_root)

    assert universe.synthetic is True
    assert not (public_only_root / "evaluator").exists()
    assert not (public_only_root / "private").exists()


def test_report_rejects_noncanonical_duplicate_gaps(tmp_path: Path) -> None:
    payload = _source_payload()
    _first_organisation(payload)["industry"] = "unsupported"
    _, report = _run(tmp_path, payload)
    assert len(report.gaps) >= 2

    unordered = _validation_payload(report)
    unordered["gaps"] = tuple(reversed(unordered["gaps"]))
    with pytest.raises(ValidationError, match="adapter_gaps_not_canonical"):
        AdapterRunReport.model_validate(unordered, strict=True)

    duplicate = _validation_payload(report)
    duplicate["gaps"] = (duplicate["gaps"][0], duplicate["gaps"][0])
    with pytest.raises(ValidationError, match="duplicate_adapter_gap"):
        AdapterRunReport.model_validate(duplicate, strict=True)


def test_report_rejects_noncanonical_duplicate_outcomes(tmp_path: Path) -> None:
    payload = _source_payload()
    _duplicate_organisation(payload, organisation_id="fictional-canary-second")
    _, report = _run(tmp_path, payload)
    assert len(report.outcomes) == 2

    unordered = _validation_payload(report)
    unordered["outcomes"] = tuple(
        reversed(unordered["outcomes"]),
    )
    with pytest.raises(ValidationError, match="organisation_outcomes_not_canonical"):
        AdapterRunReport.model_validate(unordered, strict=True)

    duplicate = _validation_payload(report)
    duplicate["outcomes"] = (
        duplicate["outcomes"][0],
        duplicate["outcomes"][0],
    )
    with pytest.raises(ValidationError, match="duplicate_organisation_outcome"):
        AdapterRunReport.model_validate(duplicate, strict=True)


def test_report_rejects_inventory_order_duplicates_and_digest_drift(
    tmp_path: Path,
) -> None:
    _, report = _run(tmp_path, _source_payload())

    unordered = _validation_payload(report)
    unordered["public_artifacts"] = tuple(reversed(unordered["public_artifacts"]))
    with pytest.raises(ValidationError, match="canonical"):
        AdapterRunReport.model_validate(unordered, strict=True)

    duplicate = _validation_payload(report)
    duplicate["public_artifacts"] = (
        duplicate["public_artifacts"][0],
        duplicate["public_artifacts"][0],
    )
    with pytest.raises(ValidationError, match="duplicate"):
        AdapterRunReport.model_validate(duplicate, strict=True)

    digest_drift = _validation_payload(report)
    digest_drift["artifact_set_digest"] = "0" * 64
    with pytest.raises(ValidationError, match="artifact_set_digest"):
        AdapterRunReport.model_validate(digest_drift, strict=True)


def test_report_rejects_status_and_inventory_consistency_drift(
    tmp_path: Path,
) -> None:
    _, report = _run(tmp_path, _source_payload())

    succeeded_with_error = _validation_payload(report)
    succeeded_with_error["error_code"] = AdapterCode.SOURCE_VALIDATION_FAILED
    with pytest.raises(ValidationError, match="successful"):
        AdapterRunReport.model_validate(succeeded_with_error, strict=True)

    failed_without_error = _validation_payload(report)
    failed_without_error["status"] = adapter_module.RunStatus.FAILED
    with pytest.raises(ValidationError, match="failed"):
        AdapterRunReport.model_validate(failed_without_error, strict=True)

    missing_inventory = _validation_payload(report)
    missing_inventory["public_artifacts"] = ()
    with pytest.raises(ValidationError, match="inventor"):
        AdapterRunReport.model_validate(missing_inventory, strict=True)


@pytest.mark.parametrize(
    ("path", "visibility", "kind"),
    [
        (
            "../public/input.json",
            ArtifactVisibility.PUBLIC,
            ArtifactKind.PUBLIC_INPUT,
        ),
        (
            "/public/input.json",
            ArtifactVisibility.PUBLIC,
            ArtifactKind.PUBLIC_INPUT,
        ),
        (
            "artifacts/org/evaluator/truth.json",
            ArtifactVisibility.PUBLIC,
            ArtifactKind.PUBLIC_INPUT,
        ),
        (
            "private/import.json",
            ArtifactVisibility.EVALUATOR,
            ArtifactKind.EVALUATOR_TRUTH,
        ),
    ],
)
def test_artifact_record_rejects_unsafe_or_cross_visibility_paths(
    path: str,
    visibility: ArtifactVisibility,
    kind: ArtifactKind,
) -> None:
    with pytest.raises(ValidationError):
        ArtifactRecord(
            byte_size=1,
            kind=kind,
            path=path,
            sha256="0" * 64,
            visibility=visibility,
        )


def test_repeated_runs_are_byte_identical(tmp_path: Path) -> None:
    first_root, first_report = _run(tmp_path, _source_payload(), name="first")
    second_root, second_report = _run(tmp_path, _source_payload(), name="second")

    assert first_report == second_report
    assert _tree_bytes(first_root) == _tree_bytes(second_root)


def test_mapping_key_order_does_not_change_source_digest_or_output_bytes(
    tmp_path: Path,
) -> None:
    original = _source_payload()
    reordered = _reverse_mapping_order(original)
    assert isinstance(reordered, dict)

    first_root, first_report = _run(tmp_path, original, name="first")
    second_root, second_report = _run(tmp_path, reordered, name="second")

    assert first_report.canonical_source_payload_digest == (
        second_report.canonical_source_payload_digest
    )
    assert _tree_bytes(first_root) == _tree_bytes(second_root)


def test_source_collection_order_is_bound_but_generated_artifacts_are_stable(
    tmp_path: Path,
) -> None:
    original = _source_payload()
    _duplicate_organisation(original, organisation_id="fictional-canary-second")
    reordered = _reverse_source_collections(original)
    assert isinstance(reordered, dict)

    first_root, first_report = _run(tmp_path, original, name="first")
    second_root, second_report = _run(tmp_path, reordered, name="second")

    assert first_report.canonical_source_payload_digest != (
        second_report.canonical_source_payload_digest
    )
    assert _tree_bytes(first_root, include_report=False) == _tree_bytes(
        second_root,
        include_report=False,
    )
