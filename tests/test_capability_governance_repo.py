"""Repository wiring checks for the curated capability catalog."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from tools.generate_capabilities import discover_routes

ROOT = Path(__file__).resolve().parents[1]
CURATED_PATH = ROOT / "docs" / "_data" / "capabilities.curated.json"
REQUIRED_CAPABILITY_KEYS = {
    "id",
    "title",
    "summary",
    "maturity",
    "support",
    "since",
    "journey_route",
    "roadmap_routes",
    "notes",
    "related_surface_ids",
    "interfaces",
}
REQUIRED_INTERFACE_KEYS = {"coverage", "surface_ids", "subset_note"}
FORBIDDEN_CAPABILITY_KEYS = {
    "artifact_kind",
    "benchmark_lifecycle",
    "benchmark_publication_lifecycle",
    "evaluator_sensitivity",
    "evaluator_secrecy",
    "lifecycle",
    "publication_status",
    "publication",
    "publication_lifecycle",
    "published",
    "sensitivity",
}
RELEASE_PATTERN = re.compile(r"\d+\.\d+\.\d+")
CLI_SURFACE_PATTERN = re.compile(r"cli:synthworld(?: [a-z0-9][a-z0-9-]*)+")
PYTHON_SURFACE_PATTERN = re.compile(
    r"python:synthworld\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
)


def _catalog() -> dict[str, object]:
    catalog = json.loads(CURATED_PATH.read_text(encoding="utf-8"))
    assert isinstance(catalog, dict)
    return cast(dict[str, object], catalog)


def _assert_anchored_route(route: object) -> None:
    assert isinstance(route, str)
    assert route.startswith("route:")
    relative_path, separator, anchor = route.removeprefix("route:").partition("#")
    assert separator == "#"
    assert relative_path
    assert anchor
    assert re.fullmatch(r"[A-Za-z0-9_./-]+", relative_path)
    document = ROOT / relative_path
    assert document.is_file()
    route_ids = {item["id"] for item in discover_routes(ROOT, [relative_path])}
    assert route in route_ids


def test_curated_capability_catalog_has_the_committed_policy_shape() -> None:
    catalog = _catalog()

    assert set(catalog) == {"schema_version", "capabilities"}
    assert catalog["schema_version"] == "1.0.0"
    capabilities = catalog["capabilities"]
    assert isinstance(capabilities, list)
    assert capabilities

    capability_ids: list[str] = []
    assigned_surface_ids: list[str] = []
    related_surface_ids: list[str] = []
    root_python_ids: list[str] = []
    subpackage_python_ids: list[str] = []
    for capability in capabilities:
        assert isinstance(capability, dict)
        assert set(capability) == REQUIRED_CAPABILITY_KEYS
        assert not (set(capability) & FORBIDDEN_CAPABILITY_KEYS)
        assert capability["maturity"] in {
            "experimental",
            "preview",
            "stable",
            "planned",
        }
        assert capability["since"] == "unreleased" or RELEASE_PATTERN.fullmatch(
            str(capability["since"])
        )
        _assert_anchored_route(capability["journey_route"])
        roadmap_routes = capability["roadmap_routes"]
        assert isinstance(roadmap_routes, list)
        assert roadmap_routes
        for route in roadmap_routes:
            _assert_anchored_route(route)
            assert str(route).startswith("route:ROADMAP.md#")

        related_ids = capability["related_surface_ids"]
        assert isinstance(related_ids, list)
        assert all(
            related_id.startswith(("contract:", "schema:"))
            for related_id in related_ids
        )
        assert all(
            not any(token in related_id for token in ("*", "?", "[", "]"))
            for related_id in related_ids
        )
        related_surface_ids.extend(related_ids)

        capability_ids.append(str(capability["id"]))
        interfaces = capability["interfaces"]
        assert isinstance(interfaces, dict)
        assert set(interfaces) == {"cli", "python"}
        for interface_name, interface in interfaces.items():
            assert isinstance(interface, dict)
            assert set(interface) == REQUIRED_INTERFACE_KEYS
            assert interface["coverage"] in {"none", "partial", "full"}
            surface_ids = interface["surface_ids"]
            assert isinstance(surface_ids, list)
            if interface_name == "cli":
                assert all(
                    CLI_SURFACE_PATTERN.fullmatch(surface_id)
                    for surface_id in surface_ids
                )
            else:
                assert all(
                    PYTHON_SURFACE_PATTERN.fullmatch(surface_id)
                    for surface_id in surface_ids
                )
                root_python_ids.extend(
                    surface_id
                    for surface_id in surface_ids
                    if surface_id.count(".") == 1
                )
                subpackage_python_ids.extend(
                    surface_id
                    for surface_id in surface_ids
                    if surface_id.count(".") > 1
                )
            assigned_surface_ids.extend(surface_ids)

            if interface["coverage"] == "none":
                assert surface_ids == []
                assert interface["subset_note"] is None
            elif interface["coverage"] == "partial":
                assert surface_ids
                assert isinstance(interface["subset_note"], str)
                assert interface["subset_note"]
            else:
                assert surface_ids
                assert interface["subset_note"] is None

        if capability["maturity"] == "planned":
            assert capability["since"] == "unreleased"
            assert all(
                interface["surface_ids"] == []
                for interface in interfaces.values()
                if isinstance(interface, dict)
            )
        if capability["maturity"] == "stable":
            assert capability["since"] != "unreleased"

    assert len(capability_ids) == len(set(capability_ids))
    assert len(assigned_surface_ids) == len(set(assigned_surface_ids))
    assert len(related_surface_ids) == len(set(related_surface_ids))
    assert root_python_ids
    assert subpackage_python_ids


def test_capability_governance_is_wired_into_local_and_ci_gates() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

    assert (
        "capabilities:\n\t$(UV) run python tools/generate_capabilities.py" in makefile
    )
    assert (
        "capabilities-check:\n\t$(UV) run python tools/generate_capabilities.py --check"
        in makefile
    )
    local_tag_check = (
        "capabilities-check:\n"
        "\t$(UV) run python tools/generate_capabilities.py --check --require-tags"
    )
    assert local_tag_check not in makefile
    assert "ci: capabilities-check " in makefile
    assert "$(UV) run mypy tools/generate_capabilities.py" not in makefile

    capability_job = workflow.split("  public-boundary:", maxsplit=1)[0]
    assert "capability-governance:" in capability_job
    assert "name: Capability governance" in capability_job
    assert "fetch-depth: 0" in capability_job
    assert (
        "uv run python tools/generate_capabilities.py --check --require-tags"
        in capability_job
    )

    assert "/.github/workflows/** @bluntmachetti" in codeowners
    assert "/.github/workflows/ci.yml @bluntmachetti" not in codeowners
    assert "/docs/_data/capabilities*.json @bluntmachetti" in codeowners
    assert "/docs/_schemas/capabilities*.json @bluntmachetti" in codeowners
    assert "/tools/** @bluntmachetti" in codeowners
    assert "/tests/test_capability_governance*.py @bluntmachetti" in codeowners
