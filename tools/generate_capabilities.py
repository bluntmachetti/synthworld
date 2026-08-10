"""Generate and validate SynthWorld capability-governance data.

The generator deliberately treats repository facts and editorial capability
claims as separate inputs.  It only reads tracked paths and never records host,
Git-status, timestamp, or filesystem-order information.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

GENERATED_PATH = Path("docs/_data/capabilities.generated.json")
CURATED_PATH = Path("docs/_data/capabilities.curated.json")
RESOLVED_PATH = Path("docs/_data/capabilities.resolved.json")
SCHEMA_PATHS = (
    Path("docs/_schemas/capabilities-generated.schema.json"),
    Path("docs/_schemas/capabilities-curated.schema.json"),
    Path("docs/_schemas/capabilities-resolved.schema.json"),
)
SCHEMA_VERSION = "1.0.0"
MATURITIES = frozenset({"experimental", "preview", "stable", "planned"})
COVERAGES = frozenset({"none", "partial", "full"})


class CapabilityError(ValueError):
    """A concise, user-correctable capability-governance error."""


def fail(message: str) -> NoReturn:
    raise CapabilityError(message)


def canonical_json(value: object) -> bytes:
    """Return the one canonical serialization used for every committed output."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("ascii")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> object:
    """Load JSON while rejecting duplicate object keys at every depth."""

    try:
        with path.open("r", encoding="utf-8", newline=None) as handle:
            return json.load(handle, object_pairs_hook=_no_duplicate_keys)
    except FileNotFoundError:
        fail(f"missing required file: {path.as_posix()}")
    except UnicodeDecodeError:
        fail(f"invalid UTF-8 in {path.as_posix()}")
    except json.JSONDecodeError as error:
        fail(f"invalid JSON in {path.as_posix()}: {error.msg}")
    except OSError as error:
        fail(f"unable to read {path.as_posix()}: {error}")


def require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        fail(f"{label} must be an array")
    return value


def require_string(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        fail(f"{label} must be a non-empty string")
    return value


def require_exact_keys(value: Mapping[str, object], keys: set[str], label: str) -> None:
    actual = set(value)
    if actual != keys:
        missing = ", ".join(sorted(keys - actual))
        extra = ", ".join(sorted(actual - keys))
        details = ", ".join(
            item
            for item in (
                f"missing {missing}" if missing else "",
                f"extra {extra}" if extra else "",
            )
            if item
        )
        fail(f"{label} has invalid fields ({details})")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def tracked_files(root: Path) -> tuple[str, ...]:
    """Return lexically sorted, repository-relative tracked paths only."""

    try:
        git = shutil.which("git")
        if git is None:
            fail("unable to enumerate tracked files: git is unavailable")
        result = subprocess.run(  # noqa: S603 - resolved trusted Git executable
            [git, "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        fail(f"unable to enumerate tracked files: {error}")
    try:
        paths = [entry for entry in result.stdout.decode("utf-8").split("\0") if entry]
    except UnicodeDecodeError:
        fail("unable to enumerate tracked files: Git returned invalid UTF-8")
    if any(Path(path).is_absolute() or ".." in Path(path).parts for path in paths):
        fail("Git returned a non-repository-relative tracked path")
    return tuple(sorted(paths))


def _source_path(root: Path, relative: str) -> Path:
    path = root / relative
    if path.is_symlink():
        fail(f"tracked source is not a regular file: {relative}")
    if not path.is_file():
        fail(f"tracked source is missing: {relative}")
    return path


def _read_utf8(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        fail(f"invalid UTF-8 in {label}")
    except OSError as error:
        fail(f"unable to read {label}: {error}")


def discover_package(root: Path) -> dict[str, object]:
    path = _source_path(root, "pyproject.toml")
    try:
        with path.open("rb") as handle:
            pyproject = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        fail(f"invalid TOML in pyproject.toml: {error}")
    except UnicodeDecodeError:
        fail("invalid UTF-8 in pyproject.toml")
    except OSError as error:
        fail(f"unable to read pyproject.toml: {error}")
    project = require_mapping(pyproject.get("project"), "pyproject project")
    scripts = require_mapping(project.get("scripts"), "pyproject project.scripts")
    return {
        "distribution": require_string(project.get("name"), "project.name"),
        "scripts": [
            {
                "name": key,
                "target": require_string(scripts[key], f"project.scripts.{key}"),
            }
            for key in sorted(scripts)
        ],
        "version": require_string(project.get("version"), "project.version"),
    }


_RELEASE_HEADING = re.compile(r"^## \[([0-9]+\.[0-9]+\.[0-9]+)\](?:\s*-\s*(.*))?$")
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def slugify_heading(heading: str) -> str:
    """Return the stable GitHub-style anchor subset used by this repository."""

    normalized = heading.lower().strip()
    normalized = re.sub(r"[^\w -]", "", normalized)
    return normalized.replace(" ", "-")


def discover_releases(root: Path) -> list[dict[str, str]]:
    text = _read_utf8(_source_path(root, "CHANGELOG.md"), "CHANGELOG.md")
    releases: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = _RELEASE_HEADING.match(line)
        if match is None:
            continue
        version = match.group(1)
        if version in seen:
            fail(f"duplicate CHANGELOG release: {version}")
        seen.add(version)
        releases.append(
            {
                "heading": line[3:],
                "id": f"changelog:{version}",
                "version": version,
            }
        )
    if not releases:
        fail("CHANGELOG.md contains no released versions")
    return sorted(
        releases,
        key=lambda release: tuple(int(part) for part in release["version"].split(".")),
        reverse=True,
    )


def discover_routes(root: Path, files: Iterable[str]) -> list[dict[str, str]]:
    routes: list[dict[str, str]] = []
    for relative in sorted(path for path in files if path.endswith(".md")):
        file_route_id = f"route:{relative}"
        routes.append(
            {
                "anchor": "",
                "heading": "",
                "id": file_route_id,
                "path": relative,
            }
        )
        used_anchors: set[str] = set()
        fence_marker: tuple[str, int] | None = None
        for line in _read_utf8(_source_path(root, relative), relative).splitlines():
            fence = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
            if fence is not None:
                marker = fence.group(1)
                if fence_marker is None:
                    fence_marker = (marker[0], len(marker))
                elif marker[0] == fence_marker[0] and len(marker) >= fence_marker[1]:
                    fence_marker = None
                continue
            if fence_marker is not None:
                continue
            match = _MARKDOWN_HEADING.match(line)
            if match is None:
                continue
            heading = match.group(2)
            base_anchor = slugify_heading(heading)
            if not base_anchor:
                continue
            anchor = base_anchor
            suffix = 0
            while anchor in used_anchors:
                suffix += 1
                anchor = f"{base_anchor}-{suffix}"
            used_anchors.add(anchor)
            route_id = f"route:{relative}#{anchor}"
            routes.append(
                {
                    "anchor": anchor,
                    "heading": heading,
                    "id": route_id,
                    "path": relative,
                }
            )
    return sorted(routes, key=lambda route: route["id"])


def _subparser_actions(
    parser: argparse.ArgumentParser,
) -> list[argparse._SubParsersAction[Any]]:
    return [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]


def _choice_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [
        action
        for action in parser._actions
        if not action.option_strings
        and action.choices is not None
        and not isinstance(action, argparse._SubParsersAction)
    ]


def discover_cli(parser: argparse.ArgumentParser) -> list[dict[str, object]]:
    """Discover executable command paths without parsing user-facing help text."""

    result: dict[str, dict[str, object]] = {}

    def add(path: Sequence[str]) -> None:
        command = " ".join(path)
        surface_id = f"cli:{command}"
        result[surface_id] = {
            "assignment_required": True,
            "id": surface_id,
            "kind": "cli_command",
            "name": command,
            "source": "src/synthworld/cli.py",
            "visibility": "public",
        }

    def walk(current: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        subparser_actions = _subparser_actions(current)
        for subparser_action in subparser_actions:
            for name, child in sorted(subparser_action.choices.items()):
                child_path = (*path, name)
                add(child_path)
                walk(child, child_path)
        for choice_action in _choice_actions(current):
            choices = choice_action.choices or ()
            for choice in sorted(str(choice) for choice in choices):
                add((*path, choice))

    walk(parser, (parser.prog,))
    return [result[surface_id] for surface_id in sorted(result)]


def _declares_all(path: Path) -> bool:
    try:
        tree = ast.parse(_read_utf8(path, path.as_posix()), filename=path.as_posix())
    except SyntaxError as error:
        fail(f"invalid Python package initializer {path.as_posix()}: {error.msg}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            return True
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            return True
    return False


def _module_name(relative: str) -> str:
    parts = Path(relative).with_suffix("").parts
    return ".".join(parts[1:-1])


def discover_python_exports(
    root: Path, files: Iterable[str] | None = None
) -> list[dict[str, object]]:
    source_root = str(root / "src")
    tracked = tuple(files) if files is not None else tracked_files(root)
    initializers = [
        relative
        for relative in tracked
        if relative.startswith("src/synthworld/") and relative.endswith("/__init__.py")
    ]
    for relative in initializers:
        if not _declares_all(_source_path(root, relative)):
            fail(f"tracked package initializer must declare __all__: {relative}")
    inserted = source_root not in sys.path
    if inserted:
        sys.path.insert(0, source_root)
    try:
        surfaces: list[dict[str, object]] = []
        for relative in sorted(set(initializers)):
            module_name = _module_name(relative)
            try:
                module = importlib.import_module(module_name)
            except (ImportError, AttributeError) as error:
                fail(f"unable to import public package {module_name}: {error}")
            exports = getattr(module, "__all__", None)
            if not isinstance(exports, (list, tuple)) or not all(
                isinstance(name, str) for name in exports
            ):
                fail(f"{module_name}.__all__ must be a list or tuple of strings")
            if len(exports) != len(set(exports)):
                fail(f"{module_name}.__all__ contains duplicate names")
            for name in sorted(exports):
                try:
                    value = getattr(module, name)
                except AttributeError:
                    fail(f"{module_name}.__all__ exports missing name: {name}")
                surface_id = f"python:{module_name}.{name}"
                implementation_module = getattr(value, "__module__", module_name)
                if not isinstance(implementation_module, str):
                    implementation_module = module_name
                surfaces.append(
                    {
                        "assignment_required": True,
                        "id": surface_id,
                        "implementation_module": implementation_module,
                        "kind": "python_export",
                        "name": name,
                        "source": relative,
                        "visibility": (
                            "public" if module_name == "synthworld" else "subpackage"
                        ),
                    }
                )
        ids = [str(surface["id"]) for surface in surfaces]
        if len(ids) != len(set(ids)):
            fail("Python export discovery produced duplicate surface IDs")
        return sorted(surfaces, key=lambda surface: str(surface["id"]))
    finally:
        if inserted:
            sys.path.remove(source_root)


def _contract_root(relative: str) -> str | None:
    for part in Path(relative).parts:
        if part.endswith("-contract"):
            return part
    return None


def discover_contract_surfaces(files: Iterable[str]) -> list[dict[str, object]]:
    roots = sorted(
        {root for path in files if (root := _contract_root(path)) is not None}
    )
    surfaces: list[dict[str, object]] = []
    for root in roots:
        surfaces.append(
            {
                "assignment_required": True,
                "id": f"contract:{root}",
                "kind": "contract",
                "name": root,
                "source": root,
                "visibility": "public",
            }
        )
    for relative in sorted(
        path for path in files if "/schemas/" in path and path.endswith(".schema.json")
    ):
        root = _contract_root(relative)
        if root is None:
            continue
        surfaces.append(
            {
                "assignment_required": True,
                "id": f"schema:{relative}",
                "kind": "schema",
                "name": Path(relative).name,
                "source": relative,
                "visibility": "public",
            }
        )
    return sorted(surfaces, key=lambda surface: str(surface["id"]))


def _is_benchmark_path(relative: str) -> bool:
    if _contract_root(relative) is not None:
        return False
    path = Path(relative)
    if path.parts[:1] == ("src",) or path.suffix == ".py":
        return False
    parts = {part.lower() for part in path.parts}
    context = bool(parts & {"benchmark", "benchmarks", "golden"})
    return context


def discover_benchmark_surfaces(files: Iterable[str]) -> list[dict[str, object]]:
    return [
        {
            "assignment_required": False,
            "id": f"benchmark:{relative}",
            "kind": "benchmark",
            "name": Path(relative).name,
            "source": relative,
            "visibility": "structural",
        }
        for relative in sorted(path for path in files if _is_benchmark_path(path))
    ]


def discover_generated(root: Path) -> dict[str, object]:
    """Return all deterministic, non-editorial repository facts."""

    files = tracked_files(root)
    source_root = root / "src" / "synthworld"
    if "src/synthworld/cli.py" not in files or not source_root.is_dir():
        fail("tracked SynthWorld CLI sources are incomplete")
    source_path = str(root / "src")
    inserted = source_path not in sys.path
    if inserted:
        sys.path.insert(0, source_path)
    try:
        cli_module = importlib.import_module("synthworld.cli")
        parser_factory = getattr(cli_module, "_parser", None)
        if not callable(parser_factory):
            fail("synthworld.cli._parser is unavailable")
        parser = parser_factory()
    finally:
        if inserted:
            sys.path.remove(source_path)
    surfaces = (
        discover_cli(parser)
        + discover_python_exports(root, files)
        + discover_contract_surfaces(files)
        + discover_benchmark_surfaces(files)
    )
    ids = [
        require_string(surface["id"], "generated surface id") for surface in surfaces
    ]
    if len(ids) != len(set(ids)):
        fail("generated discovery produced duplicate surface IDs")
    return {
        "package": discover_package(root),
        "releases": discover_releases(root),
        "routes": discover_routes(root, files),
        "schema_version": SCHEMA_VERSION,
        "surfaces": sorted(surfaces, key=lambda surface: str(surface["id"])),
    }


def _validate_interface(value: object, label: str) -> tuple[str, list[str]]:
    interface = require_mapping(value, label)
    require_exact_keys(interface, {"coverage", "subset_note", "surface_ids"}, label)
    coverage = require_string(interface["coverage"], f"{label}.coverage")
    if coverage not in COVERAGES:
        fail(f"{label}.coverage is unsupported: {coverage}")
    raw_ids = require_list(interface["surface_ids"], f"{label}.surface_ids")
    surface_ids = [
        require_string(item, f"{label}.surface_ids item") for item in raw_ids
    ]
    note = interface["subset_note"]
    if note is not None and not isinstance(note, str):
        fail(f"{label}.subset_note must be a string or null")
    if coverage == "none":
        if surface_ids or note is not None:
            fail(f"{label} with coverage none must have no surfaces or subset note")
    elif coverage == "partial":
        if not surface_ids or not isinstance(note, str) or not note.strip():
            fail(f"{label} with coverage partial requires surfaces and a subset note")
    elif not surface_ids or note is not None:
        fail(f"{label} with coverage full requires surfaces and no subset note")
    return coverage, surface_ids


def validate_curated(
    curated: object, generated: Mapping[str, object]
) -> list[dict[str, object]]:
    """Validate strict editorial claims and return capabilities in stable order."""

    document = require_mapping(curated, "curated capability document")
    require_exact_keys(
        document, {"capabilities", "schema_version"}, "curated capability document"
    )
    if document["schema_version"] != SCHEMA_VERSION:
        fail("curated capability document has an unsupported schema_version")
    generated_surfaces = require_list(generated.get("surfaces"), "generated surfaces")
    known: dict[str, Mapping[str, object]] = {}
    required: set[str] = set()
    for item in generated_surfaces:
        surface = require_mapping(item, "generated surface")
        surface_id = require_string(surface.get("id"), "generated surface id")
        if surface_id in known:
            fail(f"duplicate generated surface ID: {surface_id}")
        known[surface_id] = surface
        if surface.get("assignment_required") is True:
            required.add(surface_id)
    route_ids = {
        require_string(
            require_mapping(route, "generated route").get("id"), "generated route id"
        )
        for route in require_list(generated.get("routes"), "generated routes")
    }
    release_versions = {
        require_string(
            require_mapping(release, "generated release").get("version"),
            "generated release version",
        )
        for release in require_list(generated.get("releases"), "generated releases")
    }
    capabilities = require_list(document["capabilities"], "curated capabilities")
    capability_ids: set[str] = set()
    assignments: dict[str, str] = {}
    validated: list[dict[str, object]] = []
    expected = {
        "id",
        "interfaces",
        "journey_route",
        "maturity",
        "notes",
        "related_surface_ids",
        "roadmap_routes",
        "since",
        "summary",
        "support",
        "title",
    }
    for index, item in enumerate(capabilities):
        capability = require_mapping(item, f"capability {index}")
        require_exact_keys(capability, expected, f"capability {index}")
        capability_id = require_string(capability["id"], f"capability {index}.id")
        if capability_id in capability_ids:
            fail(f"duplicate capability ID: {capability_id}")
        capability_ids.add(capability_id)
        for field in ("title", "summary", "support"):
            require_string(capability[field], f"capability {capability_id}.{field}")
        if not isinstance(capability["notes"], str):
            fail(f"capability {capability_id}.notes must be a string")
        maturity = require_string(
            capability["maturity"], f"capability {capability_id}.maturity"
        )
        if maturity not in MATURITIES:
            fail(f"capability {capability_id} has unsupported maturity: {maturity}")
        since = require_string(capability["since"], f"capability {capability_id}.since")
        if since != "unreleased" and since not in release_versions:
            fail(
                f"capability {capability_id} has no CHANGELOG release evidence: {since}"
            )
        if maturity == "stable" and since == "unreleased":
            fail(f"stable capability {capability_id} cannot be unreleased")
        journey = require_string(
            capability["journey_route"], f"capability {capability_id}.journey_route"
        )
        if journey not in route_ids:
            fail(
                f"capability {capability_id} references unknown journey route: "
                f"{journey}"
            )
        roadmap = require_list(
            capability["roadmap_routes"], f"capability {capability_id}.roadmap_routes"
        )
        for route in roadmap:
            route_id = require_string(
                route, f"capability {capability_id}.roadmap_routes route"
            )
            if route_id not in route_ids:
                fail(
                    f"capability {capability_id} references unknown roadmap route: "
                    f"{route_id}"
                )
        interfaces = require_mapping(
            capability["interfaces"], f"capability {capability_id}.interfaces"
        )
        require_exact_keys(
            interfaces, {"cli", "python"}, f"capability {capability_id}.interfaces"
        )
        cli_coverage, cli_ids = _validate_interface(
            interfaces["cli"], f"capability {capability_id}.interfaces.cli"
        )
        python_coverage, python_ids = _validate_interface(
            interfaces["python"], f"capability {capability_id}.interfaces.python"
        )
        if (cli_coverage != "none" or python_coverage != "none") and "#" not in journey:
            fail(
                f"implemented capability {capability_id} requires an anchored "
                "journey route"
            )
        related_ids = [
            require_string(item, f"capability {capability_id}.related_surface_ids item")
            for item in require_list(
                capability["related_surface_ids"],
                f"capability {capability_id}.related_surface_ids",
            )
        ]
        for surface_id in cli_ids:
            if not surface_id.startswith("cli:"):
                fail(
                    f"capability {capability_id} assigns non-CLI surface in CLI "
                    f"interface: {surface_id}"
                )
        for surface_id in python_ids:
            if not surface_id.startswith("python:"):
                fail(
                    f"capability {capability_id} assigns non-Python surface in Python "
                    f"interface: {surface_id}"
                )
        for surface_id in related_ids:
            if not surface_id.startswith(("contract:", "schema:")):
                fail(
                    f"capability {capability_id} assigns interface surface as related: "
                    f"{surface_id}"
                )
        surface_ids = cli_ids + python_ids + related_ids
        if len(surface_ids) != len(set(surface_ids)):
            fail(f"capability {capability_id} assigns a surface more than once")
        if maturity == "planned" and (since != "unreleased" or surface_ids):
            fail(
                f"planned capability {capability_id} must be unreleased with no "
                "surfaces"
            )
        for surface_id in surface_ids:
            if surface_id not in known:
                fail(
                    f"capability {capability_id} assigns unknown surface: {surface_id}"
                )
            existing = assignments.get(surface_id)
            if existing is not None:
                fail(
                    f"surface {surface_id} is assigned by both {existing} and "
                    f"{capability_id}"
                )
            assignments[surface_id] = capability_id
        validated.append(dict(capability))
    orphans = sorted(required - set(assignments))
    if orphans:
        fail("unassigned generated surfaces: " + ", ".join(orphans))
    return sorted(validated, key=lambda capability: str(capability["id"]))


def resolve_capabilities(
    generated: Mapping[str, object],
    curated: object,
    *,
    generated_bytes: bytes | None = None,
    curated_bytes: bytes | None = None,
) -> dict[str, object]:
    """Join validated editorial claims to the complete generated surface records."""

    capabilities = validate_curated(curated, generated)
    surfaces = {
        require_string(
            require_mapping(item, "generated surface").get("id"), "generated surface id"
        ): item
        for item in require_list(generated.get("surfaces"), "generated surfaces")
    }
    resolved_capabilities: list[dict[str, object]] = []
    for capability in capabilities:
        interfaces = require_mapping(capability["interfaces"], "capability interfaces")
        resolved_interfaces: dict[str, object] = {}
        for name in ("cli", "python"):
            interface = require_mapping(
                interfaces[name], f"capability interface {name}"
            )
            surface_ids = [
                require_string(item, "surface id")
                for item in require_list(
                    interface["surface_ids"],
                    f"capability interface {name} surfaces",
                )
            ]
            resolved_interfaces[name] = {
                "coverage": interface["coverage"],
                "subset_note": interface["subset_note"],
                "surfaces": [surfaces[item] for item in sorted(surface_ids)],
            }
        resolved_capabilities.append(
            {
                "id": capability["id"],
                "interfaces": resolved_interfaces,
                "journey_route": capability["journey_route"],
                "maturity": capability["maturity"],
                "notes": capability["notes"],
                "related_surfaces": [
                    surfaces[item]
                    for item in sorted(
                        require_string(item, "related surface id")
                        for item in require_list(
                            capability["related_surface_ids"],
                            "capability related surface ids",
                        )
                    )
                ],
                "roadmap_routes": sorted(
                    require_string(item, "capability roadmap route")
                    for item in require_list(
                        capability["roadmap_routes"],
                        "capability roadmap routes",
                    )
                ),
                "since": capability["since"],
                "summary": capability["summary"],
                "support": capability["support"],
                "title": capability["title"],
            }
        )
    return {
        "capabilities": resolved_capabilities,
        "input_digests": {
            "curated_sha256": hashlib.sha256(
                curated_bytes if curated_bytes is not None else canonical_json(curated)
            ).hexdigest(),
            "generated_sha256": hashlib.sha256(
                generated_bytes
                if generated_bytes is not None
                else canonical_json(generated)
            ).hexdigest(),
        },
        "schema_version": SCHEMA_VERSION,
    }


def validate_schema_strict(path: Path) -> None:
    """Ensure committed schemas retain the promised closed-object contract."""

    schema = load_json(path)

    def walk(value: object, label: str) -> None:
        if isinstance(value, dict):
            if (
                value.get("type") == "object"
                and value.get("additionalProperties") is not False
            ):
                fail(f"schema object is not closed: {label}")
            for key, child in value.items():
                walk(child, f"{label}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{label}[{index}]")

    walk(schema, path.as_posix())


def validate_schema_instance(instance: object, schema: object, label: str) -> None:
    """Validate an instance and report the first deterministic schema error."""

    schema_mapping = require_mapping(schema, f"{label} schema")
    try:
        Draft202012Validator.check_schema(schema_mapping)
        errors = sorted(
            Draft202012Validator(schema_mapping).iter_errors(instance),
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                tuple(str(part) for part in error.absolute_schema_path),
                error.message,
            ),
        )
    except SchemaError as schema_error:
        fail(f"invalid {label} schema: {schema_error.message}")
    if errors:
        first_error: ValidationError = errors[0]
        location = ".".join(str(part) for part in first_error.absolute_path) or "<root>"
        fail(f"{label} schema violation at {location}: {first_error.message}")


def _load_schemas(root: Path) -> tuple[object, object, object]:
    schemas: list[object] = []
    for relative in SCHEMA_PATHS:
        path = root / relative
        validate_schema_strict(path)
        schemas.append(load_json(path))
    return schemas[0], schemas[1], schemas[2]


def _load_canonical_curated(root: Path, *, normalize: bool) -> tuple[object, bytes]:
    path = root / CURATED_PATH
    curated = load_json(path)
    canonical = canonical_json(curated)
    committed = path.read_bytes()
    if committed != canonical:
        if not normalize:
            fail(f"non-canonical committed input: {CURATED_PATH.as_posix()}")
        path.write_bytes(canonical)
    return curated, canonical


def build_outputs(
    root: Path,
    *,
    normalize_curated: bool = False,
    generated_digest_bytes: bytes | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    generated_schema, curated_schema, resolved_schema = _load_schemas(root)
    curated, curated_bytes = _load_canonical_curated(root, normalize=normalize_curated)
    generated = discover_generated(root)
    generated_bytes = canonical_json(generated)
    validate_schema_instance(generated, generated_schema, "generated capability data")
    validate_schema_instance(curated, curated_schema, "curated capability data")
    resolved = resolve_capabilities(
        generated,
        curated,
        generated_bytes=(
            generated_digest_bytes
            if generated_digest_bytes is not None
            else generated_bytes
        ),
        curated_bytes=curated_bytes,
    )
    validate_schema_instance(resolved, resolved_schema, "resolved capability data")
    return generated, resolved


def write_outputs(root: Path) -> None:
    generated, resolved = build_outputs(root, normalize_curated=True)
    for relative, value in ((GENERATED_PATH, generated), (RESOLVED_PATH, resolved)):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(canonical_json(value))


def check_outputs(root: Path) -> None:
    committed_outputs: dict[Path, bytes] = {}
    for relative in (GENERATED_PATH, RESOLVED_PATH):
        path = root / relative
        try:
            committed_outputs[relative] = path.read_bytes()
        except FileNotFoundError:
            fail(f"missing committed output: {relative.as_posix()}")
    generated, resolved = build_outputs(
        root, generated_digest_bytes=committed_outputs[GENERATED_PATH]
    )
    for relative, value in ((GENERATED_PATH, generated), (RESOLVED_PATH, resolved)):
        if committed_outputs[relative] != canonical_json(value):
            fail(f"generated output drift: {relative.as_posix()}")


def _run_git(
    root: Path, arguments: Sequence[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    if git is None:
        fail("unable to validate release tags: git is unavailable")
    try:
        result = subprocess.run(  # noqa: S603 - resolved trusted Git executable
            [git, "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            encoding="utf-8",
            text=True,
        )
    except UnicodeDecodeError:
        fail("unable to validate release tags: Git returned invalid UTF-8")
    except OSError:
        fail("unable to validate release tags: Git execution failed")
    if check and result.returncode != 0:
        command = " ".join(arguments[:2])
        fail(f"release-tag Git command failed: {command}")
    return result


def _git_show(root: Path, tag: str, source: str) -> str | None:
    result = _run_git(root, ["show", f"{tag}:{source}"], check=False)
    return result.stdout if result.returncode == 0 else None


def _imported_module_name(source: str, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    package = _module_name(source)
    parts = package.split(".")
    remove = node.level - 1
    if remove > len(parts):
        return None
    prefix = parts[: len(parts) - remove]
    if node.module:
        prefix.extend(node.module.split("."))
    return ".".join(prefix)


def _module_source_at_tag(root: Path, tag: str, module: str) -> str | None:
    base = "src/" + module.replace(".", "/")
    for candidate in (f"{base}/__init__.py", f"{base}.py"):
        if _git_show(root, tag, candidate) is not None:
            return candidate
    return None


def _sequence_value(
    node: ast.expr, bindings: Mapping[str, tuple[str, ...] | None]
) -> tuple[str, ...] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _sequence_value(node.left, bindings)
        right = _sequence_value(node.right, bindings)
        return None if left is None or right is None else (*left, *right)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[str] = []
        for element in node.elts:
            value = _sequence_value(
                element.value if isinstance(element, ast.Starred) else element,
                bindings,
            )
            if value is None:
                return None
            values.extend(value)
        return tuple(values)
    return None


def _tagged_python_exports(
    root: Path,
    tag: str,
    source: str,
    stack: tuple[str, ...] = (),
) -> frozenset[str]:
    if source in stack:
        fail(f"cyclic tagged __all__ imports at {tag}:{source}")
    text = _git_show(root, tag, source)
    if text is None:
        return frozenset()
    try:
        tree = ast.parse(text, filename=f"{tag}:{source}")
    except SyntaxError as error:
        fail(f"invalid tagged Python source {tag}:{source}: {error.msg}")
    bindings: dict[str, tuple[str, ...] | None] = {}
    declared = False
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            module = _imported_module_name(source, node)
            for imported in node.names:
                if imported.name != "__all__" or module is None:
                    continue
                imported_source = _module_source_at_tag(root, tag, module)
                value = (
                    None
                    if imported_source is None
                    else tuple(
                        sorted(
                            _tagged_python_exports(
                                root, tag, imported_source, (*stack, source)
                            )
                        )
                    )
                )
                bindings[imported.asname or imported.name] = value
        elif isinstance(node, ast.Assign):
            value = _sequence_value(node.value, bindings)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = value
                    declared = declared or target.id == "__all__"
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            value = (
                None if node.value is None else _sequence_value(node.value, bindings)
            )
            bindings[node.target.id] = value
            declared = declared or node.target.id == "__all__"
        elif (
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and isinstance(node.op, ast.Add)
        ):
            prior = bindings.get(node.target.id)
            added = _sequence_value(node.value, bindings)
            bindings[node.target.id] = (
                None if prior is None or added is None else (*prior, *added)
            )
            declared = declared or node.target.id == "__all__"
    if not declared:
        return frozenset()
    exports = bindings.get("__all__")
    if exports is None:
        fail(f"unable to resolve tagged __all__ at {tag}:{source}")
    return frozenset(exports)


def _string_literal(node: ast.expr) -> str | None:
    return (
        node.value
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        else None
    )


def _tagged_cli_commands(
    text: str, tag: str, source: str
) -> frozenset[tuple[str, ...]]:
    try:
        tree = ast.parse(text, filename=f"{tag}:{source}")
    except SyntaxError as error:
        fail(f"invalid tagged Python source {tag}:{source}: {error.msg}")
    factory = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_parser"
        ),
        None,
    )
    if factory is None:
        return frozenset()
    parsers: dict[str, tuple[str, ...]] = {}
    subparsers: dict[str, tuple[str, ...]] = {}
    commands: set[tuple[str, ...]] = set()

    def bind(call: ast.Call, names: tuple[str, ...]) -> None:
        if not isinstance(call.func, ast.Attribute):
            return
        owner = call.func.value.id if isinstance(call.func.value, ast.Name) else None
        if call.func.attr == "ArgumentParser":
            for name in names:
                parsers[name] = ()
        elif call.func.attr == "add_subparsers" and owner in parsers:
            for name in names:
                subparsers[name] = parsers[owner]
        elif call.func.attr == "add_parser" and owner in subparsers and call.args:
            command = _string_literal(call.args[0])
            if command is None:
                return
            path = (*subparsers[owner], command)
            commands.add(path)
            for name in names:
                parsers[name] = path
        elif call.func.attr == "add_argument" and owner in parsers and call.args:
            argument = _string_literal(call.args[0])
            if argument is None or argument.startswith("-"):
                return
            choices = next(
                (
                    keyword.value
                    for keyword in call.keywords
                    if keyword.arg == "choices"
                ),
                None,
            )
            if choices is None:
                return
            values = _sequence_value(choices, {})
            if values is not None:
                commands.update((*parsers[owner], value) for value in values)

    for statement in factory.body:
        names: tuple[str, ...] = ()
        call: ast.Call | None = None
        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call):
            names = tuple(
                target.id
                for target in statement.targets
                if isinstance(target, ast.Name)
            )
            call = statement.value
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and isinstance(statement.value, ast.Call)
        ):
            names = (statement.target.id,)
            call = statement.value
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
        if call is not None:
            bind(call, names)
    return frozenset(commands)


def _surface_present_at_tag(
    root: Path, tag: str, surface: Mapping[str, object]
) -> bool:
    source = require_string(surface.get("source"), "tagged surface source")
    kind = require_string(surface.get("kind"), "tagged surface kind")
    if kind == "contract":
        result = _run_git(root, ["ls-tree", "-r", "--name-only", tag, "--", source])
        prefix = source.rstrip("/") + "/"
        return any(
            path == source or path.startswith(prefix)
            for path in result.stdout.splitlines()
        )
    text = _git_show(root, tag, source)
    if text is None:
        return False
    if kind in {"schema", "benchmark"}:
        return True
    name = require_string(surface.get("name"), "tagged surface name")
    if kind == "python_export":
        return name in _tagged_python_exports(root, tag, source)
    if kind == "cli_command":
        parts = tuple(name.split())
        return len(parts) > 1 and parts[1:] in _tagged_cli_commands(text, tag, source)
    return False


_SEMVER_TAG = re.compile(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$")


def _owned_surface_ids(
    capability: Mapping[str, object], capability_id: str
) -> list[str]:
    interfaces = require_mapping(
        capability.get("interfaces"), f"capability {capability_id}.interfaces"
    )
    owned: list[str] = []
    for interface_name in ("cli", "python"):
        interface = require_mapping(
            interfaces.get(interface_name),
            f"capability {capability_id}.interfaces.{interface_name}",
        )
        owned.extend(
            require_string(value, f"capability {capability_id} surface id")
            for value in require_list(
                interface.get("surface_ids"),
                f"capability {capability_id} surface ids",
            )
        )
    owned.extend(
        require_string(value, f"capability {capability_id} related surface id")
        for value in require_list(
            capability.get("related_surface_ids"),
            f"capability {capability_id} related surface ids",
        )
    )
    return sorted(owned)


def validate_release_tags(
    root: Path, generated: Mapping[str, object], curated: object
) -> None:
    """Validate release assertions without changing deterministic output bytes."""

    tags: dict[str, tuple[int, int, int]] = {}
    for tag in _run_git(root, ["tag", "--list"]).stdout.splitlines():
        match = _SEMVER_TAG.fullmatch(tag)
        if match is not None:
            tags[tag] = (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
    package = require_mapping(generated.get("package"), "generated package")
    current_version = require_string(
        package.get("version"), "generated package version"
    )
    current_tag = f"v{current_version}"
    release_versions = {
        require_string(
            require_mapping(item, "generated release").get("version"),
            "generated release version",
        )
        for item in require_list(generated.get("releases"), "generated releases")
    }
    if current_version not in release_versions:
        fail(f"current package version is missing from CHANGELOG: {current_version}")
    surfaces = {
        require_string(
            require_mapping(item, "generated surface").get("id"),
            "generated surface id",
        ): require_mapping(item, "generated surface")
        for item in require_list(generated.get("surfaces"), "generated surfaces")
    }
    document = require_mapping(curated, "curated capability document")
    for item in require_list(document.get("capabilities"), "curated capabilities"):
        capability = require_mapping(item, "curated capability")
        capability_id = require_string(capability.get("id"), "capability id")
        since = require_string(
            capability.get("since"), f"capability {capability_id}.since"
        )
        required_tag = f"v{since}"
        if (
            since != "unreleased"
            and required_tag not in tags
            and not (since == current_version and current_tag not in tags)
        ):
            fail(f"capability {capability_id} requires missing tag {required_tag}")
        owned_ids = _owned_surface_ids(capability, capability_id)
        if not owned_ids:
            continue
        known_surfaces = [
            surfaces[surface_id] for surface_id in owned_ids if surface_id in surfaces
        ]
        if not known_surfaces:
            continue
        earliest: str | None = None
        for tag, _version in sorted(tags.items(), key=lambda item: item[1]):
            if any(
                _surface_present_at_tag(root, tag, surface)
                for surface in known_surfaces
            ):
                earliest = tag[1:]
                break
        if earliest is not None:
            if since != earliest:
                fail(
                    f"capability {capability_id} since is {since}; earliest owned "
                    f"surface release is {earliest}"
                )
        elif since != "unreleased" and not (
            since == current_version and current_tag not in tags
        ):
            fail(
                f"capability {capability_id} since is {since}, but no owned surface "
                "exists in an available release tag"
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify committed outputs")
    parser.add_argument(
        "--require-tags",
        action="store_true",
        help="require release tags and reject false unreleased claims",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.check:
            check_outputs(repository_root())
        else:
            write_outputs(repository_root())
        if arguments.require_tags:
            generated = discover_generated(repository_root())
            curated = load_json(repository_root() / CURATED_PATH)
            validate_release_tags(repository_root(), generated, curated)
    except CapabilityError as error:
        print(f"capability governance: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
