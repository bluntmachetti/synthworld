"""Discriminating tests for the repository-independent capability engine."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tools import generate_capabilities as tool


def _surface(surface_id: str, required: bool = True) -> dict[str, object]:
    kind = "cli_command"
    if surface_id.startswith("contract:"):
        kind = "contract"
    elif surface_id.startswith("schema:"):
        kind = "schema"
    elif surface_id.startswith("benchmark:"):
        kind = "benchmark"
    elif surface_id.startswith("python:"):
        kind = "python_export"
    source = "src/synthworld/cli.py"
    name = surface_id
    if kind == "python_export":
        qualified = surface_id.removeprefix("python:")
        module, name = qualified.rsplit(".", 1)
        source = "src/" + module.replace(".", "/") + "/__init__.py"
    return {
        "assignment_required": required,
        "id": surface_id,
        "kind": kind,
        "name": name,
        "source": source,
        "visibility": "public" if required else "structural",
    }


def _generated(*surface_ids: str) -> dict[str, object]:
    return {
        "package": {
            "distribution": "example",
            "scripts": [{"name": "synthworld", "target": "synthworld.cli:main"}],
            "version": "1.0.0",
        },
        "releases": [
            {"heading": "[1.0.0]", "id": "changelog:1.0.0", "version": "1.0.0"}
        ],
        "routes": [
            {
                "anchor": "guide",
                "heading": "Guide",
                "id": "route:GUIDE.md#guide",
                "path": "GUIDE.md",
            },
            {
                "anchor": "roadmap",
                "heading": "Roadmap",
                "id": "route:ROADMAP.md#roadmap",
                "path": "ROADMAP.md",
            },
        ],
        "schema_version": "1.0.0",
        "surfaces": [_surface(surface_id) for surface_id in surface_ids],
    }


def _interface(
    coverage: str, ids: list[str], note: str | None = None
) -> dict[str, object]:
    return {"coverage": coverage, "subset_note": note, "surface_ids": ids}


def _capability(
    surface_ids: list[str],
    *,
    capability_id: str = "core",
    maturity: str = "stable",
    since: str = "1.0.0",
    cli: dict[str, object] | None = None,
    related_surface_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": capability_id,
        "interfaces": {
            "cli": cli or _interface("full", surface_ids),
            "python": _interface("none", []),
        },
        "journey_route": "route:GUIDE.md#guide",
        "maturity": maturity,
        "notes": "",
        "related_surface_ids": related_surface_ids or [],
        "roadmap_routes": ["route:ROADMAP.md#roadmap"],
        "since": since,
        "summary": "summary",
        "support": "supported",
        "title": "Core",
    }


def _curated(*capabilities: dict[str, object]) -> dict[str, object]:
    return {"capabilities": list(capabilities), "schema_version": "1.0.0"}


def test_strict_value_helpers_and_repository_root() -> None:
    with pytest.raises(tool.CapabilityError, match="must be an object"):
        tool.require_mapping([], "value")
    with pytest.raises(tool.CapabilityError, match="must be an array"):
        tool.require_list({}, "value")
    for empty_value in (None, ""):
        with pytest.raises(tool.CapabilityError, match="must be a non-empty string"):
            tool.require_string(empty_value, "value")
    assert tool.require_string("", "value", allow_empty=True) == ""
    for value, message in (
        ({"extra": 1}, "missing wanted, extra extra"),
        ({}, "missing wanted"),
        ({"wanted": 1, "extra": 2}, "extra extra"),
    ):
        with pytest.raises(tool.CapabilityError, match=message):
            tool.require_exact_keys(value, {"wanted"}, "value")
    assert tool.repository_root() == Path(__file__).parents[1]


def test_cli_discovery_includes_nested_and_evaluate_variants_not_option_choices() -> (
    None
):
    parser = argparse.ArgumentParser(prog="synthworld")
    commands = parser.add_subparsers(required=True)
    validate = commands.add_parser("validate")
    validate.add_subparsers(required=True).add_parser("trace")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("task", choices=["risk", "agentic"])
    evaluate.add_argument("--tier", choices=["smoke", "held_out"])
    mixed = commands.add_parser("mixed")
    mixed.add_argument("mode", choices=["one", "two"])
    mixed.add_subparsers().add_parser("child")

    ids = [item["id"] for item in tool.discover_cli(parser)]

    assert ids == [
        "cli:synthworld evaluate",
        "cli:synthworld evaluate agentic",
        "cli:synthworld evaluate risk",
        "cli:synthworld mixed",
        "cli:synthworld mixed child",
        "cli:synthworld mixed one",
        "cli:synthworld mixed two",
        "cli:synthworld validate",
        "cli:synthworld validate trace",
    ]


def test_python_exports_are_exact_top_level_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "src" / "synthworld"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "__all__ = ('two', 'one')\none = 1\ntwo = object()\n", encoding="ascii"
    )
    monkeypatch.delitem(__import__("sys").modules, "synthworld", raising=False)

    surfaces = tool.discover_python_exports(tmp_path, ("src/synthworld/__init__.py",))

    assert [surface["id"] for surface in surfaces] == [
        "python:synthworld.one",
        "python:synthworld.two",
    ]
    assert all(surface["implementation_module"] == "synthworld" for surface in surfaces)


def test_python_exports_include_declared_subpackages_without_promotion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "src" / "synthworld"
    child = package / "enterprise"
    child.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "__all__ = ('root_name',)\nroot_name = 1\n", encoding="ascii"
    )
    (child / "__init__.py").write_text(
        "__all__: tuple[str, ...] = ('child_name',)\nchild_name = 2\n",
        encoding="ascii",
    )
    for name in tuple(sys.modules):
        if name == "synthworld" or name.startswith("synthworld."):
            monkeypatch.delitem(sys.modules, name, raising=False)

    surfaces = tool.discover_python_exports(
        tmp_path,
        (
            "src/synthworld/__init__.py",
            "src/synthworld/enterprise/__init__.py",
        ),
    )

    assert [(surface["id"], surface["visibility"]) for surface in surfaces] == [
        ("python:synthworld.enterprise.child_name", "subpackage"),
        ("python:synthworld.root_name", "public"),
    ]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ('{"x": 1, "x": 2}', "duplicate JSON key"),
        ("not-json", "invalid JSON"),
    ],
)
def test_load_json_rejects_duplicate_keys_and_invalid_json(
    tmp_path: Path, value: str, message: str
) -> None:
    path = tmp_path / "input.json"
    path.write_text(value, encoding="ascii")
    with pytest.raises(tool.CapabilityError, match=message):
        tool.load_json(path)


def test_load_json_and_tracked_file_failures_are_concise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(tool.CapabilityError, match="missing required file"):
        tool.load_json(tmp_path / "missing.json")

    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(tool.CapabilityError, match="git is unavailable"):
        tool.tracked_files(tmp_path)

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            ["git"], 0, b"../escape\0", b""
        ),
    )
    with pytest.raises(tool.CapabilityError, match="non-repository-relative"):
        tool.tracked_files(tmp_path)

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(["git"], 0, b"z\0a\0", b""),
    )
    assert tool.tracked_files(tmp_path) == ("a", "z")

    def fail_git(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, ["git"])

    monkeypatch.setattr(subprocess, "run", fail_git)
    with pytest.raises(tool.CapabilityError, match="unable to enumerate tracked files"):
        tool.tracked_files(tmp_path)

    with pytest.raises(tool.CapabilityError, match="tracked source is missing"):
        tool._source_path(tmp_path, "missing.txt")

    target = tmp_path / "target.txt"
    target.write_text("content", encoding="utf-8")
    (tmp_path / "linked.txt").symlink_to(target)
    with pytest.raises(tool.CapabilityError, match="not a regular file"):
        tool._source_path(tmp_path, "linked.txt")


@pytest.mark.parametrize(
    ("curated", "message"),
    [
        (
            _curated(_capability(["cli:one"]), _capability(["cli:two"])),
            "duplicate capability ID",
        ),
        (
            _curated(_capability(["cli:one", "cli:one"])),
            "assigns a surface more than once",
        ),
        (_curated(_capability(["cli:unknown"])), "assigns unknown surface"),
        (
            _curated(_capability([], cli=_interface("none", []))),
            "unassigned generated surfaces",
        ),
    ],
)
def test_validate_curated_rejects_duplicate_and_orphan_assignments(
    curated: dict[str, object], message: str
) -> None:
    with pytest.raises(tool.CapabilityError, match=message):
        tool.validate_curated(curated, _generated("cli:one"))


@pytest.mark.parametrize(
    ("curated", "message"),
    [
        (
            _curated(
                _capability(["cli:one"], related_surface_ids=["contract:core"]),
                _capability(
                    [],
                    capability_id="other",
                    cli=_interface("none", []),
                    related_surface_ids=["contract:core"],
                ),
            ),
            "assigned by both",
        ),
        (
            _curated(_capability(["cli:one"], related_surface_ids=["schema:unknown"])),
            "assigns unknown surface",
        ),
        (
            _curated(_capability(["cli:one"], related_surface_ids=["cli:one"])),
            "assigns interface surface as related",
        ),
    ],
)
def test_validate_curated_rejects_related_surface_assignment_errors(
    curated: dict[str, object], message: str
) -> None:
    with pytest.raises(tool.CapabilityError, match=message):
        tool.validate_curated(curated, _generated("cli:one", "contract:core"))


@pytest.mark.parametrize(
    ("capability", "message"),
    [
        (
            _capability(["cli:one"], cli=_interface("unknown", ["cli:one"])),
            "coverage is unsupported",
        ),
        (
            _capability(["cli:one"], cli=_interface("partial", ["cli:one"])),
            "requires surfaces and a subset note",
        ),
        (
            _capability(["cli:one"], cli=_interface("none", ["cli:one"])),
            "coverage none",
        ),
        (
            _capability([], cli=_interface("full", [])),
            "coverage full requires surfaces and no subset note",
        ),
        (
            _capability(
                ["cli:one"], cli=_interface("full", ["cli:one"], "not allowed")
            ),
            "coverage full requires surfaces and no subset note",
        ),
        (
            _capability(["cli:one"], maturity="stable", since="unreleased"),
            "cannot be unreleased",
        ),
        (
            _capability(["cli:one"], maturity="planned", since="unreleased"),
            "must be unreleased with no surfaces",
        ),
        (_capability(["cli:one"], since="2.0.0"), "no CHANGELOG release evidence"),
    ],
)
def test_validate_curated_rejects_interface_and_release_violations(
    capability: dict[str, object], message: str
) -> None:
    with pytest.raises(tool.CapabilityError, match=message):
        tool.validate_curated(_curated(capability), _generated("cli:one"))


def test_validate_curated_accepts_unreleased_preview_and_routes() -> None:
    capability = _capability(
        ["cli:one"],
        maturity="preview",
        since="unreleased",
        cli=_interface("partial", ["cli:one"], "only the command-line interface"),
    )
    assert (
        tool.validate_curated(_curated(capability), _generated("cli:one"))[0]["id"]
        == "core"
    )


def test_validate_curated_rejects_missing_route_anchor() -> None:
    capability = _capability(["cli:one"])
    capability["journey_route"] = "route:GUIDE.md#missing"
    with pytest.raises(tool.CapabilityError, match="unknown journey route"):
        tool.validate_curated(_curated(capability), _generated("cli:one"))


def test_validate_curated_requires_anchored_journey_for_implemented_interface() -> None:
    capability = _capability(["cli:one"])
    capability["journey_route"] = "route:GUIDE.md"
    generated = _generated("cli:one")
    routes = generated["routes"]
    assert isinstance(routes, list)
    routes.append(
        {"anchor": "", "heading": "", "id": "route:GUIDE.md", "path": "GUIDE.md"}
    )
    with pytest.raises(tool.CapabilityError, match="requires an anchored journey"):
        tool.validate_curated(_curated(capability), generated)


def test_resolve_sorts_and_leaves_structural_benchmarks_unassigned() -> None:
    generated = _generated("cli:z", "cli:a")
    surfaces = generated["surfaces"]
    assert isinstance(surfaces, list)
    surfaces.append(_surface("benchmark:golden/SHA256SUMS", False))
    curated = _curated(
        _capability(["cli:z"], capability_id="zeta"),
        _capability(["cli:a"], capability_id="alpha"),
    )

    resolved = tool.resolve_capabilities(generated, curated)

    capabilities = resolved["capabilities"]
    assert isinstance(capabilities, list)
    assert [item["id"] for item in capabilities if isinstance(item, dict)] == [
        "alpha",
        "zeta",
    ]
    benchmark = surfaces[-1]
    assert set(benchmark) == {
        "assignment_required",
        "id",
        "kind",
        "name",
        "source",
        "visibility",
    }
    assert tool.canonical_json(resolved) == tool.canonical_json(resolved)


def test_discover_routes_includes_file_routes_and_duplicate_heading_suffixes(
    tmp_path: Path,
) -> None:
    (tmp_path / "GUIDE.md").write_text(
        "# Intro\n## Intro\n## Intro 1\n## under_score--kept\n"
        "```md\n# Not a route\n```\n",
        encoding="ascii",
    )

    routes = tool.discover_routes(tmp_path, ("GUIDE.md",))

    assert [route["id"] for route in routes] == [
        "route:GUIDE.md",
        "route:GUIDE.md#intro",
        "route:GUIDE.md#intro-1",
        "route:GUIDE.md#intro-1-1",
        "route:GUIDE.md#under_score--kept",
    ]


def test_check_outputs_reports_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tool, "_load_schemas", lambda root: ({}, {}, {}))
    monkeypatch.setattr(tool, "validate_schema_instance", lambda *args: None)
    curated = _curated(_capability(["cli:one"]))
    path = tmp_path / tool.CURATED_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tool.canonical_json(curated))
    monkeypatch.setattr(tool, "discover_generated", lambda root: _generated("cli:one"))
    (tmp_path / tool.GENERATED_PATH).write_text("{}\n", encoding="ascii")
    (tmp_path / tool.RESOLVED_PATH).write_text("{}\n", encoding="ascii")

    with pytest.raises(tool.CapabilityError, match="generated output drift"):
        tool.check_outputs(tmp_path)


def test_canonical_curated_bytes_are_the_resolved_digest(tmp_path: Path) -> None:
    curated = _curated(_capability(["cli:one"]))
    generated = _generated("cli:one")
    curated_bytes = tool.canonical_json(curated)
    generated_bytes = tool.canonical_json(generated)

    resolved = tool.resolve_capabilities(
        generated,
        curated,
        curated_bytes=curated_bytes,
        generated_bytes=generated_bytes,
    )

    digests = resolved["input_digests"]
    assert isinstance(digests, dict)
    assert digests == {
        "curated_sha256": hashlib.sha256(curated_bytes).hexdigest(),
        "generated_sha256": hashlib.sha256(generated_bytes).hexdigest(),
    }

    path = tmp_path / tool.CURATED_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(curated), encoding="ascii")
    with pytest.raises(tool.CapabilityError, match="non-canonical committed input"):
        tool._load_canonical_curated(tmp_path, normalize=False)
    loaded, normalized = tool._load_canonical_curated(tmp_path, normalize=True)
    assert loaded == curated
    assert path.read_bytes() == normalized == curated_bytes


def test_contract_and_benchmark_discovery_are_disjoint_and_ordered() -> None:
    files = (
        "z-contract/manifest.json",
        "z-contract/schemas/z.schema.json",
        "golden/case.json",
        "benchmarks/SHA256SUMS",
        "ordinary/manifest.json",
        "src/synthworld/benchmarks/__init__.py",
        "fixtures/golden/example.py",
    )

    contracts = tool.discover_contract_surfaces(files)
    benchmarks = tool.discover_benchmark_surfaces(files)

    assert [item["id"] for item in contracts] == [
        "contract:z-contract",
        "schema:z-contract/schemas/z.schema.json",
    ]
    assert [item["id"] for item in benchmarks] == [
        "benchmark:benchmarks/SHA256SUMS",
        "benchmark:golden/case.json",
    ]
    assert not {item["source"] for item in contracts} & {
        item["source"] for item in benchmarks
    }
    assert all("sensitivity" not in item for item in benchmarks)


def test_package_release_and_route_discovery_from_repository_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="example"\nversion="2.0.0"\n'
        '[project.scripts]\nz="z:main"\na="a:main"\n',
        encoding="ascii",
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "## [1.0.0] - first\n## [2.0.0] - second\n", encoding="ascii"
    )

    assert tool.discover_package(tmp_path)["scripts"] == [
        {"name": "a", "target": "a:main"},
        {"name": "z", "target": "z:main"},
    ]
    assert [item["version"] for item in tool.discover_releases(tmp_path)] == [
        "2.0.0",
        "1.0.0",
    ]

    (tmp_path / "CHANGELOG.md").write_text("## [1.0.0]\n## [1.0.0]\n", encoding="ascii")
    with pytest.raises(tool.CapabilityError, match="duplicate CHANGELOG release"):
        tool.discover_releases(tmp_path)

    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="ascii")
    with pytest.raises(tool.CapabilityError, match="invalid TOML"):
        tool.discover_package(tmp_path)


def test_schema_validation_is_strict_and_reports_first_instance_error(
    tmp_path: Path,
) -> None:
    open_schema = tmp_path / "open.json"
    open_schema.write_text('{"type":"object"}\n', encoding="ascii")
    with pytest.raises(tool.CapabilityError, match="schema object is not closed"):
        tool.validate_schema_strict(open_schema)

    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "type": "object",
    }
    with pytest.raises(tool.CapabilityError, match="schema violation at name"):
        tool.validate_schema_instance({"name": 3}, schema, "fixture")
    tool.validate_schema_instance({"name": "valid"}, schema, "fixture")
    with pytest.raises(tool.CapabilityError, match="invalid fixture schema"):
        tool.validate_schema_instance({}, {"type": "not-a-type"}, "fixture")


@pytest.mark.parametrize(
    ("exports", "attribute", "message"),
    [
        ("'not-a-sequence'", "", "must be a list or tuple"),
        ("('same', 'same')", "same = 1\n", "contains duplicate names"),
        ("('missing',)", "", "exports missing name"),
    ],
)
def test_python_export_discovery_rejects_invalid_all(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    exports: str,
    attribute: str,
    message: str,
) -> None:
    package = tmp_path / "src" / "synthworld"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        f"__all__ = {exports}\n{attribute}", encoding="ascii"
    )
    monkeypatch.delitem(sys.modules, "synthworld", raising=False)
    with pytest.raises(tool.CapabilityError, match=message):
        tool.discover_python_exports(tmp_path, ("src/synthworld/__init__.py",))


def test_python_export_discovery_rejects_invalid_initializer(tmp_path: Path) -> None:
    package = tmp_path / "src" / "synthworld"
    package.mkdir(parents=True)
    initializer = package / "__init__.py"
    initializer.write_text("__all__ = (\n", encoding="ascii")
    with pytest.raises(
        tool.CapabilityError, match="invalid Python package initializer"
    ):
        tool._declares_all(initializer)


def test_discover_generated_composes_and_rejects_duplicate_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "src" / "synthworld").mkdir(parents=True)
    parser = argparse.ArgumentParser(prog="synthworld")
    fake_cli = type("Cli", (), {"_parser": staticmethod(lambda: parser)})
    monkeypatch.setattr(
        tool,
        "tracked_files",
        lambda root: ("src/synthworld/cli.py", "src/synthworld/__init__.py"),
    )
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: fake_cli if name == "synthworld.cli" else object(),
    )
    monkeypatch.setattr(tool, "discover_python_exports", lambda root, files: [])
    monkeypatch.setattr(tool, "discover_package", lambda root: _generated()["package"])
    monkeypatch.setattr(
        tool, "discover_releases", lambda root: _generated()["releases"]
    )
    monkeypatch.setattr(
        tool, "discover_routes", lambda root, files: _generated()["routes"]
    )

    generated = tool.discover_generated(tmp_path)
    assert generated["surfaces"] == []

    duplicate = _surface("cli:duplicate")
    monkeypatch.setattr(tool, "discover_cli", lambda parser: [duplicate])
    monkeypatch.setattr(
        tool, "discover_contract_surfaces", lambda files: [dict(duplicate)]
    )
    with pytest.raises(tool.CapabilityError, match="duplicate surface IDs"):
        tool.discover_generated(tmp_path)


def test_build_write_and_check_use_canonical_bytes_and_all_schemas(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    curated = _curated(_capability(["cli:one"]))
    curated_path = tmp_path / tool.CURATED_PATH
    curated_path.parent.mkdir(parents=True)
    curated_path.write_text(json.dumps(curated), encoding="ascii")
    monkeypatch.setattr(tool, "_load_schemas", lambda root: ({}, {}, {}))
    labels: list[str] = []
    monkeypatch.setattr(
        tool,
        "validate_schema_instance",
        lambda instance, schema, label: labels.append(label),
    )
    monkeypatch.setattr(tool, "discover_generated", lambda root: _generated("cli:one"))

    tool.write_outputs(tmp_path)

    assert curated_path.read_bytes() == tool.canonical_json(curated)
    assert (tmp_path / tool.GENERATED_PATH).read_bytes() == tool.canonical_json(
        _generated("cli:one")
    )
    assert labels == [
        "generated capability data",
        "curated capability data",
        "resolved capability data",
    ]
    tool.check_outputs(tmp_path)

    (tmp_path / tool.RESOLVED_PATH).write_text("{}\n", encoding="ascii")
    with pytest.raises(tool.CapabilityError, match=r"capabilities\.resolved\.json"):
        tool.check_outputs(tmp_path)


def _completed(
    arguments: list[str], *, stdout: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments, returncode, stdout, "")


def test_release_tag_validation_requires_historical_tags_and_changelog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    generated = _generated("cli:one")
    released = _curated(_capability(["cli:one"]))
    monkeypatch.setattr(
        tool,
        "_run_git",
        lambda root, arguments, check=True: _completed(
            list(arguments), stdout="v1.0.0\n"
        ),
    )
    monkeypatch.setattr(tool, "_surface_present_at_tag", lambda *args: True)
    tool.validate_release_tags(tmp_path, generated, released)

    preview = _curated(_capability(["cli:one"], maturity="preview", since="unreleased"))
    monkeypatch.setattr(tool, "_surface_present_at_tag", lambda *args: True)
    with pytest.raises(tool.CapabilityError, match="earliest owned surface release"):
        tool.validate_release_tags(tmp_path, generated, preview)

    missing_release = _curated(_capability(["cli:one"], since="0.9.0"))
    with pytest.raises(tool.CapabilityError, match=r"requires missing tag v0\.9\.0"):
        tool.validate_release_tags(tmp_path, generated, missing_release)

    generated["releases"] = []
    with pytest.raises(tool.CapabilityError, match="missing from CHANGELOG"):
        tool.validate_release_tags(tmp_path, generated, released)


@pytest.mark.parametrize(
    ("kind", "stdout", "returncode", "expected"),
    [
        ("python_export", "__all__ = ('thing',)\n", 0, True),
        ("python_export", "__all__ = ()\n", 0, False),
        (
            "cli_command",
            "def _parser():\n"
            " p = argparse.ArgumentParser()\n"
            " s = p.add_subparsers()\n"
            " s.add_parser('thing')\n",
            0,
            True,
        ),
        ("cli_command", "def _parser():\n pass\n", 0, False),
        ("schema", "{}\n", 0, True),
        ("schema", "", 1, False),
        ("unknown", "thing\n", 0, False),
    ],
)
def test_tagged_surface_presence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    stdout: str,
    returncode: int,
    expected: bool,
) -> None:
    surface = _surface("cli:thing")
    surface["kind"] = kind
    surface["name"] = "synthworld thing" if kind == "cli_command" else "thing"
    surface["source"] = (
        "src/synthworld/__init__.py"
        if kind == "python_export"
        else "src/synthworld/cli.py"
    )
    monkeypatch.setattr(
        tool,
        "_run_git",
        lambda root, arguments, check=True: _completed(
            list(arguments), stdout=stdout, returncode=returncode
        ),
    )
    assert tool._surface_present_at_tag(tmp_path, "v1.0.0", surface) is expected


def test_tagged_contract_presence_uses_tracked_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    surface = _surface("contract:example-contract")
    surface["source"] = "example-contract"
    monkeypatch.setattr(
        tool,
        "_run_git",
        lambda root, arguments, check=True: _completed(
            list(arguments), stdout="example-contract/README.md\n"
        ),
    )
    assert tool._surface_present_at_tag(tmp_path, "v1.0.0", surface)


def test_run_git_reports_missing_binary_and_command_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(tool.CapabilityError, match="git is unavailable"):
        tool._run_git(tmp_path, ["tag", "--list"])

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _completed(["git"], returncode=1),
    )
    with pytest.raises(tool.CapabilityError, match="Git command failed"):
        tool._run_git(tmp_path, ["tag", "--list"])

    def raise_oserror(*args: object, **kwargs: object) -> None:
        raise OSError

    monkeypatch.setattr(subprocess, "run", raise_oserror)
    with pytest.raises(tool.CapabilityError, match="Git execution failed"):
        tool._run_git(tmp_path, ["tag", "--list"])


def test_main_routes_write_check_tags_and_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tool, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(tool, "write_outputs", lambda root: calls.append("write"))
    monkeypatch.setattr(tool, "check_outputs", lambda root: calls.append("check"))
    monkeypatch.setattr(tool, "discover_generated", lambda root: _generated())
    monkeypatch.setattr(tool, "load_json", lambda path: _curated())
    monkeypatch.setattr(
        tool,
        "validate_release_tags",
        lambda root, generated, curated: calls.append("tags"),
    )

    assert tool.main([]) == 0
    assert tool.main(["--check", "--require-tags"]) == 0
    assert calls == ["write", "check", "tags"]

    monkeypatch.setattr(
        tool,
        "write_outputs",
        lambda root: tool.fail("planted failure"),
    )
    assert tool.main([]) == 1
    assert "capability governance: planted failure" in capsys.readouterr().err


def test_release_route_and_initializer_defensive_branches(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text("not a release\n", encoding="ascii")
    with pytest.raises(tool.CapabilityError, match="contains no released versions"):
        tool.discover_releases(tmp_path)

    (tmp_path / "GUIDE.md").write_text(
        "plain text\n# !!!\n````md\n# hidden\n```\n# still hidden\n````\n# Visible\n",
        encoding="ascii",
    )
    assert [route["id"] for route in tool.discover_routes(tmp_path, ("GUIDE.md",))] == [
        "route:GUIDE.md",
        "route:GUIDE.md#visible",
    ]

    initializer = tmp_path / "__init__.py"
    initializer.write_text("value = 1\n", encoding="ascii")
    assert not tool._declares_all(initializer)


def test_python_export_discovery_handles_import_and_module_anomalies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "src" / "synthworld"
    child = package / "child"
    child.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "__all__ = ('value',)\nvalue = 1\n", encoding="ascii"
    )
    (child / "__init__.py").write_text(
        "__all__ = ('value',)\nvalue = 1\n", encoding="ascii"
    )
    files = (
        "src/synthworld/__init__.py",
        "src/synthworld/child/__init__.py",
    )

    monkeypatch.setattr(tool, "tracked_files", lambda root: files)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("planted")),
    )
    source_root = str(tmp_path / "src")
    sys.path.insert(0, source_root)
    try:
        with pytest.raises(
            tool.CapabilityError, match="unable to import public package"
        ):
            tool.discover_python_exports(tmp_path)
    finally:
        sys.path.remove(source_root)

    value = type("Value", (), {"__module__": None})()
    module = type("Module", (), {"__all__": ("value",), "value": value})()
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    monkeypatch.setattr(tool, "_module_name", lambda relative: "synthworld")
    with pytest.raises(tool.CapabilityError, match="duplicate surface IDs"):
        tool.discover_python_exports(tmp_path, files)

    surfaces = tool.discover_python_exports(tmp_path, ("src/synthworld/__init__.py",))
    assert surfaces[0]["implementation_module"] == "synthworld"

    value = type("Value", (), {"__module__": "pathlib._local"})()
    module = type("Module", (), {"__all__": ("value",), "value": value})()
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    surfaces = tool.discover_python_exports(tmp_path, ("src/synthworld/__init__.py",))
    assert surfaces[0]["implementation_module"] == "pathlib"

    module = type("Module", (), {"__all__": ("value",), "value": int | str})()
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    surfaces = tool.discover_python_exports(tmp_path, ("src/synthworld/__init__.py",))
    assert surfaces[0]["implementation_module"] == "typing"


def test_contract_discovery_ignores_noncontract_schema() -> None:
    assert (
        tool.discover_contract_surfaces(
            ("ordinary/schemas/not-a-contract.schema.json",)
        )
        == []
    )


def test_discover_generated_rejects_incomplete_cli_and_missing_parser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tool, "tracked_files", lambda root: ())
    with pytest.raises(tool.CapabilityError, match="CLI sources are incomplete"):
        tool.discover_generated(tmp_path)

    (tmp_path / "src" / "synthworld").mkdir(parents=True)
    monkeypatch.setattr(tool, "tracked_files", lambda root: ("src/synthworld/cli.py",))
    monkeypatch.setattr(importlib, "import_module", lambda name: object())
    with pytest.raises(tool.CapabilityError, match="_parser is unavailable"):
        tool.discover_generated(tmp_path)


def test_additional_curated_semantic_failures() -> None:
    generated = _generated("cli:one")
    wrong_version = _curated()
    wrong_version["schema_version"] = "2.0.0"
    with pytest.raises(tool.CapabilityError, match="unsupported schema_version"):
        tool.validate_curated(wrong_version, generated)

    duplicated_generated = _generated("cli:one")
    duplicated_generated["surfaces"] = [
        _surface("cli:one"),
        _surface("cli:one"),
    ]
    with pytest.raises(tool.CapabilityError, match="duplicate generated surface ID"):
        tool.validate_curated(_curated(_capability(["cli:one"])), duplicated_generated)

    for field, value, message in (
        ("notes", None, "notes must be a string"),
        ("maturity", "unknown", "unsupported maturity"),
        ("roadmap_routes", ["route:missing"], "unknown roadmap route"),
    ):
        capability = _capability(["cli:one"])
        capability[field] = value
        with pytest.raises(tool.CapabilityError, match=message):
            tool.validate_curated(_curated(capability), generated)

    capability = _capability(
        ["python:synthworld.value"],
        cli=_interface("full", ["python:synthworld.value"]),
    )
    with pytest.raises(tool.CapabilityError, match="non-CLI surface"):
        tool.validate_curated(_curated(capability), generated)

    capability = _capability(["cli:one"])
    capability["interfaces"] = {
        "cli": _interface("none", []),
        "python": _interface("full", ["cli:one"]),
    }
    with pytest.raises(tool.CapabilityError, match="non-Python surface"):
        tool.validate_curated(_curated(capability), generated)


def test_interface_rejects_non_string_subset_note() -> None:
    with pytest.raises(tool.CapabilityError, match="must be a string or null"):
        tool._validate_interface(
            {"coverage": "partial", "subset_note": 3, "surface_ids": ["cli:one"]},
            "interface",
        )


def test_schema_recursion_loading_and_missing_output(tmp_path: Path) -> None:
    strict_schema = tmp_path / "strict.json"
    strict_schema.write_text(
        '{"additionalProperties":false,"examples":[[1]],"type":"object"}\n',
        encoding="ascii",
    )
    tool.validate_schema_strict(strict_schema)

    schema = '{"additionalProperties":false,"type":"object"}\n'
    for relative in tool.SCHEMA_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(schema, encoding="ascii")
    assert len(tool._load_schemas(tmp_path)) == 3

    with pytest.raises(tool.CapabilityError, match="missing committed output"):
        tool.check_outputs(tmp_path / "missing")


def test_run_git_success_and_unreleased_absence_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _completed(["git"], stdout="ok\n"),
    )
    assert tool._run_git(tmp_path, ["tag", "--list"]).stdout == "ok\n"

    generated = _generated("cli:one")
    capability = _capability(["cli:missing"], maturity="preview", since="unreleased")
    monkeypatch.setattr(
        tool,
        "_run_git",
        lambda root, arguments, check=True: _completed(
            list(arguments), stdout="v1.0.0\n"
        ),
    )
    monkeypatch.setattr(
        tool,
        "_surface_present_at_tag",
        lambda *args: pytest.fail("unknown surfaces must not be inspected"),
    )
    tool.validate_release_tags(tmp_path, generated, _curated(capability))

    capability["interfaces"] = {
        "cli": _interface("full", ["cli:one"]),
        "python": _interface("none", []),
    }
    monkeypatch.setattr(tool, "_surface_present_at_tag", lambda *args: False)
    tool.validate_release_tags(tmp_path, generated, _curated(capability))

    capability["since"] = "1.0.0"
    with pytest.raises(tool.CapabilityError, match="no owned surface exists"):
        tool.validate_release_tags(tmp_path, generated, _curated(capability))


def test_python_discovery_rejects_initializer_without_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "src" / "synthworld"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("value = 1\n", encoding="ascii")
    with pytest.raises(tool.CapabilityError, match="must declare __all__"):
        tool.discover_python_exports(tmp_path, ("src/synthworld/__init__.py",))


def _git(repo: Path, *arguments: str) -> str:
    return tool._run_git(repo, arguments).stdout


def _commit_tag(repo: Path, tag: str, message: str) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    _git(repo, "tag", tag)


def test_real_tag_history_finds_exact_earliest_owned_surface(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Capability Test")
    package = tmp_path / "src" / "synthworld"
    package.mkdir(parents=True)
    (package / "models.py").write_text("__all__ = ['imported']\n", encoding="ascii")
    (package / "__init__.py").write_text(
        "from synthworld.models import __all__ as _model_exports\n"
        "_local = ('own',)\n"
        "__all__ = (*_model_exports,) + _local\n",
        encoding="ascii",
    )
    (package / "cli.py").write_text(
        "import argparse\n"
        "def _parser():\n"
        "    parser = argparse.ArgumentParser()\n"
        "    commands = parser.add_subparsers()\n"
        "    evaluate = commands.add_parser('evaluate')\n"
        "    evaluate.add_argument('task', choices=('risk',))\n"
        "    commands.add_parser('riskier')\n"
        "    return parser\n",
        encoding="ascii",
    )
    _commit_tag(tmp_path, "v0.9.0", "initial surfaces")
    (package / "__init__.py").write_text("__all__ = ('new',)\n", encoding="ascii")
    _commit_tag(tmp_path, "v1.0.0", "new surface")

    python_surface = _surface("python:synthworld.imported")
    cli_surface = _surface("cli:synthworld evaluate risk")
    cli_surface["name"] = "synthworld evaluate risk"
    assert tool._surface_present_at_tag(tmp_path, "v0.9.0", python_surface)
    assert tool._surface_present_at_tag(tmp_path, "v0.9.0", cli_surface)
    cli_surface["name"] = "synthworld evaluate riskier"
    assert not tool._surface_present_at_tag(tmp_path, "v0.9.0", cli_surface)

    generated = _generated("python:synthworld.imported")
    generated["package"]["version"] = "1.0.0"  # type: ignore[index]
    generated["releases"] = [
        {"heading": "[1.0.0]", "id": "changelog:1.0.0", "version": "1.0.0"},
        {"heading": "[0.9.0]", "id": "changelog:0.9.0", "version": "0.9.0"},
    ]
    capability = _capability([], since="0.9.0", cli=_interface("none", []))
    capability["interfaces"]["python"] = _interface(  # type: ignore[index]
        "full", ["python:synthworld.imported"]
    )
    tool.validate_release_tags(tmp_path, generated, _curated(capability))
    capability["since"] = "1.0.0"
    with pytest.raises(
        tool.CapabilityError,
        match=r"earliest owned surface release is 0\.9\.0",
    ):
        tool.validate_release_tags(tmp_path, generated, _curated(capability))


def test_real_tag_history_allows_untagged_release_preparation(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Capability Test")
    package = tmp_path / "src" / "synthworld"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__all__ = ()\n", encoding="ascii")
    _commit_tag(tmp_path, "v1.0.0", "previous release")
    _git(tmp_path, "tag", "preview")
    generated = _generated("python:synthworld.future")
    generated["package"]["version"] = "1.1.0"  # type: ignore[index]
    generated["releases"] = [
        {"heading": "[1.1.0]", "id": "changelog:1.1.0", "version": "1.1.0"}
    ]
    capability = _capability([], since="1.1.0", cli=_interface("none", []))
    capability["interfaces"]["python"] = _interface(  # type: ignore[index]
        "full", ["python:synthworld.future"]
    )
    tool.validate_release_tags(tmp_path, generated, _curated(capability))
    capability["since"] = "unreleased"
    tool.validate_release_tags(tmp_path, generated, _curated(capability))


def test_expected_text_decoding_failures_are_concise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_bytes(b"\xff")
    with pytest.raises(tool.CapabilityError, match="invalid UTF-8"):
        tool.load_json(invalid)

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
        ),
    )
    with pytest.raises(tool.CapabilityError, match="Git returned invalid UTF-8"):
        tool._run_git(tmp_path, ["tag", "--list"])

    monkeypatch.setattr(
        tomllib,
        "load",
        lambda handle: (_ for _ in ()).throw(
            tomllib.TOMLDecodeError("invalid", "x", 0)
        ),
    )
    (tmp_path / "pyproject.toml").write_text("x=1\n", encoding="ascii")
    with pytest.raises(tool.CapabilityError, match="invalid TOML"):
        tool.discover_package(tmp_path)


def test_expected_file_and_git_decoding_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(tool.CapabilityError, match="unable to read"):
        tool.load_json(tmp_path)

    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"\xff")
    with pytest.raises(tool.CapabilityError, match="invalid UTF-8"):
        tool._read_utf8(invalid, "invalid.txt")
    with pytest.raises(tool.CapabilityError, match="unable to read"):
        tool._read_utf8(tmp_path, "directory")

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_bytes(b"\xff")
    with pytest.raises(tool.CapabilityError, match="invalid UTF-8"):
        tool.discover_package(tmp_path)

    pyproject.write_text("[project]\n", encoding="ascii")

    def fail_open(*args: object, **kwargs: object) -> object:
        raise OSError("planted")

    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(tool.CapabilityError, match=r"unable to read pyproject\.toml"):
        tool.discover_package(tmp_path)

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(["git"], 0, b"\xff", b""),
    )
    with pytest.raises(tool.CapabilityError, match="Git returned invalid UTF-8"):
        tool.tracked_files(tmp_path)


def _import_from(source: str) -> ast.ImportFrom:
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.ImportFrom)
    return node


def test_tagged_import_and_sequence_helpers_cover_supported_forms(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert (
        tool._imported_module_name(
            "src/synthworld/__init__.py", _import_from("from example import value")
        )
        == "example"
    )
    assert (
        tool._imported_module_name(
            "src/synthworld/child/__init__.py",
            _import_from("from .models import value"),
        )
        == "synthworld.child.models"
    )
    assert (
        tool._imported_module_name(
            "src/synthworld/child/module.py",
            _import_from("from ..models import value"),
        )
        == "synthworld.models"
    )
    assert (
        tool._imported_module_name(
            "src/synthworld/module.py",
            _import_from("from ...models import value"),
        )
        is None
    )

    monkeypatch.setattr(tool, "_git_show", lambda *args: None)
    assert tool._module_source_at_tag(tmp_path, "v1.0.0", "synthworld.none") is None

    assert tool._sequence_value(ast.parse("missing", mode="eval").body, {}) is None
    assert tool._sequence_value(ast.parse("('a',) + ('b',)", mode="eval").body, {}) == (
        "a",
        "b",
    )
    assert tool._sequence_value(ast.parse("(*missing,)", mode="eval").body, {}) is None
    assert tool._sequence_value(ast.parse("make()", mode="eval").body, {}) is None


@pytest.mark.parametrize(
    ("source", "expected", "message"),
    [
        ("__all__: tuple[str, ...] = ('a',)\n", {"a"}, None),
        ("__all__ = ('a',)\n__all__ += ('b',)\n", {"a", "b"}, None),
        ("value = 1\n", set(), None),
        ("holder.value = ('a',)\n", set(), None),
        ("value = 1\nvalue *= 2\n", set(), None),
        ("__all__: tuple[str, ...]\n", None, "unable to resolve"),
        ("__all__ += ('a',)\n", None, "unable to resolve"),
        ("__all__ = ()\n__all__ += make()\n", None, "unable to resolve"),
    ],
)
def test_tagged_python_all_assignment_forms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    source: str,
    expected: set[str] | None,
    message: str | None,
) -> None:
    monkeypatch.setattr(tool, "_git_show", lambda *args: source)
    if message is not None:
        with pytest.raises(tool.CapabilityError, match=message):
            tool._tagged_python_exports(
                tmp_path, "v1.0.0", "src/synthworld/__init__.py"
            )
    else:
        assert expected is not None
        assert tool._tagged_python_exports(
            tmp_path, "v1.0.0", "src/synthworld/__init__.py"
        ) == frozenset(expected)


def test_tagged_python_all_rejects_cycle_and_invalid_syntax(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tool, "_git_show", lambda *args: "from . import __all__\n")
    monkeypatch.setattr(
        tool,
        "_module_source_at_tag",
        lambda *args: "src/synthworld/__init__.py",
    )
    with pytest.raises(tool.CapabilityError, match="cyclic tagged __all__"):
        tool._tagged_python_exports(tmp_path, "v1.0.0", "src/synthworld/__init__.py")

    monkeypatch.setattr(tool, "_git_show", lambda *args: "__all__ = (\n")
    with pytest.raises(tool.CapabilityError, match="invalid tagged Python source"):
        tool._tagged_python_exports(tmp_path, "v1.0.0", "src/synthworld/__init__.py")

    monkeypatch.setattr(tool, "_git_show", lambda *args: None)
    assert (
        tool._tagged_python_exports(tmp_path, "v1.0.0", "src/synthworld/__init__.py")
        == set()
    )

    monkeypatch.setattr(tool, "_git_show", lambda *args: "from example import other\n")
    assert (
        tool._tagged_python_exports(tmp_path, "v1.0.0", "src/synthworld/__init__.py")
        == set()
    )


def test_tagged_cli_parser_defensive_and_annotated_forms() -> None:
    with pytest.raises(tool.CapabilityError, match="invalid tagged Python source"):
        tool._tagged_cli_commands("def _parser(:\n", "v1.0.0", "cli.py")
    assert tool._tagged_cli_commands("value = 1\n", "v1.0.0", "cli.py") == set()

    source = (
        "def _parser():\n"
        "    factory()\n"
        "    parser: object = argparse.ArgumentParser()\n"
        "    groups: object = parser.add_subparsers()\n"
        "    groups.add_parser(dynamic)\n"
        "    child: object = groups.add_parser('child')\n"
        "    child.add_argument('--mode', choices=('ignored',))\n"
        "    child.add_argument()\n"
        "    child.add_argument('plain')\n"
        "    child.add_argument('dynamic', choices=values)\n"
        "    child.add_argument('mode', choices=('a', 'b'))\n"
    )
    assert tool._tagged_cli_commands(source, "v1.0.0", "cli.py") == {
        ("child",),
        ("child", "a"),
        ("child", "b"),
    }


def test_release_tag_validation_skips_surface_free_capability(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        tool,
        "_run_git",
        lambda *args, **kwargs: _completed(["git"], stdout="v1.0.0\nnoise\n"),
    )
    capability = _capability(
        [], maturity="planned", since="unreleased", cli=_interface("none", [])
    )
    tool.validate_release_tags(tmp_path, _generated(), _curated(capability))


def test_generated_discovery_preserves_preexisting_source_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "src" / "synthworld").mkdir(parents=True)
    parser = argparse.ArgumentParser(prog="synthworld")
    fake_cli = type("Cli", (), {"_parser": staticmethod(lambda: parser)})
    monkeypatch.setattr(tool, "tracked_files", lambda root: ("src/synthworld/cli.py",))
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_cli)
    monkeypatch.setattr(tool, "discover_python_exports", lambda root, files: [])
    monkeypatch.setattr(tool, "discover_package", lambda root: _generated()["package"])
    monkeypatch.setattr(
        tool, "discover_releases", lambda root: _generated()["releases"]
    )
    monkeypatch.setattr(
        tool, "discover_routes", lambda root, files: _generated()["routes"]
    )
    source_root = str(tmp_path / "src")
    sys.path.insert(0, source_root)
    try:
        assert tool.discover_generated(tmp_path)["surfaces"] == []
        assert source_root in sys.path
    finally:
        sys.path.remove(source_root)


def test_valid_python_interface_assignment_is_accepted() -> None:
    surface_id = "python:synthworld.value"
    capability = _capability([], cli=_interface("none", []))
    capability["interfaces"] = {
        "cli": _interface("none", []),
        "python": _interface("full", [surface_id]),
    }
    assert (
        tool.validate_curated(_curated(capability), _generated(surface_id))[0]["id"]
        == "core"
    )
