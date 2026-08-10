"""Tests for the schema-neutral declared-pattern coverage report."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml

from synthworld.agent_authority.common import CONTROL_ORDER, DeploymentPattern
from synthworld.agent_authority.models import AgentAuthorityRunPlanV1
from synthworld.agent_authority.reference import (
    build_reference_agent_authority_run_receipt,
    reference_plan,
)
from synthworld.assurance.models import EvaluationStatus

_TOOL_PATH = Path("agent-authority-contract/tools/render_pattern_coverage.py")
_CATALOGUE_PATH = Path("agent-authority-contract/control-catalogue.yaml")
_PatternCell = tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]


def _renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_pattern_coverage", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def renderer() -> ModuleType:
    return _renderer()


@pytest.fixture
def reference_receipt(tmp_path: Path) -> Path:
    root = tmp_path / "reference-receipt"
    build_reference_agent_authority_run_receipt(root)
    return root


def _evaluated_manifest(**overrides: object) -> SimpleNamespace:
    provenance: dict[str, object] = {
        "adapter": {"name": "adapter", "source_digest": "adapter-digest"},
        "benchmark": {"benchmark_id": "reference-benchmark", "version": "1.0.0"},
        "build_environment": {"lock_digest": "lock-digest"},
        "digest_algorithm": "sha256",
        "event_schedule": [{"key": "schedule", "value": "1.0.0"}],
        "evidence_claim": {"kind": "reference-declaration"},
        "generator_configuration": [{"key": "seed", "value": "0"}],
        "schema_versions": [{"role": "run_receipt", "version": "2.0.0"}],
        "scoring_formula_versions": [
            {"role": "agent_authority_lab", "version": "1.0.0"}
        ],
        "serialization": {"encoding": "utf-8"},
        "systems_under_test": [
            {"component_id": "reference-sut", "configuration_digest": "config-digest"}
        ],
    }
    provenance.update(overrides)

    def model_dump(*, mode: str, include: set[str]) -> dict[str, object]:
        assert mode == "json"
        return {field: provenance[field] for field in include}

    return SimpleNamespace(
        evaluation_status=EvaluationStatus.EVALUATED,
        model_dump=model_dump,
    )


def _write_plan(root: Path, plan: AgentAuthorityRunPlanV1) -> None:
    (root / "context").mkdir(parents=True)
    (root / "context" / "run-plan.json").write_text(
        json.dumps(plan.model_dump(mode="json")), encoding="utf-8"
    )


def _catalogue_with(
    tmp_path: Path,
    *,
    control_id: str | None = None,
    pattern: str | None = None,
    reverse_patterns: bool = False,
    controls: object | None = None,
) -> Path:
    document = yaml.safe_load(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    if controls is not None:
        document["controls"] = controls
        path = tmp_path / "catalogue.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path
    catalogue_controls = document["controls"]
    assert isinstance(catalogue_controls, list)
    assert isinstance(catalogue_controls[0], dict)
    if control_id is not None:
        catalogue_controls[0]["control_id"] = control_id
    if pattern is not None:
        patterns = catalogue_controls[0]["applicable_patterns"]
        assert isinstance(patterns, list)
        patterns[0] = pattern
    if reverse_patterns:
        for control in catalogue_controls:
            assert isinstance(control, dict)
            patterns = control["applicable_patterns"]
            assert isinstance(patterns, list)
            patterns.reverse()
    path = tmp_path / "catalogue.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_reference_rows_are_canonical_and_have_no_aggregate(
    renderer: ModuleType, reference_receipt: Path
) -> None:
    rows = renderer.pattern_coverage_rows((reference_receipt,))

    assert tuple(row.control_id for row in rows) == CONTROL_ORDER
    assert len(rows) == 24
    default_core_cell = (
        ("proxy-injection", "short-lived-minting", "static-bearer"),
        (),
        ("proxy-injection", "short-lived-minting", "static-bearer"),
    )
    expected: dict[str, _PatternCell] = {
        f"SW-AA-C{number:02d}": default_core_cell
        for number in (*range(1, 11), *range(12, 17))
    }
    expected.update(
        {
            "SW-AA-C11": (
                ("proxy-injection", "short-lived-minting"),
                (),
                ("proxy-injection", "short-lived-minting"),
            ),
            "SW-AA-L01": (
                ("proxy-injection", "short-lived-minting", "static-bearer"),
                ("proxy-injection", "static-bearer"),
                ("short-lived-minting",),
            ),
            "SW-AA-L02": (
                ("short-lived-minting", "static-bearer"),
                ("static-bearer",),
                ("short-lived-minting",),
            ),
            "SW-AA-L03": (("proxy-injection",), ("proxy-injection",), ()),
            "SW-AA-L04": (
                ("proxy-injection", "short-lived-minting"),
                ("proxy-injection",),
                ("short-lived-minting",),
            ),
            "SW-AA-L05": (
                ("proxy-injection", "short-lived-minting", "static-bearer"),
                ("proxy-injection", "static-bearer"),
                ("short-lived-minting",),
            ),
            "SW-AA-L06": (
                ("proxy-injection", "short-lived-minting", "static-bearer"),
                ("proxy-injection", "static-bearer"),
                ("short-lived-minting",),
            ),
            "SW-AA-L07": (
                ("proxy-injection", "short-lived-minting", "static-bearer"),
                ("proxy-injection", "static-bearer"),
                ("short-lived-minting",),
            ),
            "SW-AA-L08": (
                ("proxy-injection", "short-lived-minting"),
                ("proxy-injection",),
                ("short-lived-minting",),
            ),
        }
    )
    assert {
        row.control_id.value: (
            row.applicable_patterns,
            row.declared_compatible_patterns,
            row.undeclared_applicable_patterns,
        )
        for row in rows
    } == expected

    rendered = renderer.render_table(rows)
    assert "percentage" not in rendered
    assert "score" not in rendered
    assert (
        "| control_id | applicable_patterns | declared_compatible_patterns |"
        in rendered
    )


def test_catalogue_and_materially_different_receipt_order_do_not_change_output(
    renderer: ModuleType, tmp_path: Path
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root, patterns in (
        (first, (DeploymentPattern.PROXY_INJECTION, DeploymentPattern.STATIC_BEARER)),
        (
            second,
            (
                DeploymentPattern.PROXY_INJECTION,
                DeploymentPattern.SHORT_LIVED_MINTING,
            ),
        ),
    ):
        plan = reference_plan().model_copy(update={"deployment_patterns": patterns})
        _write_plan(root, plan)
    reordered_catalogue = _catalogue_with(tmp_path, reverse_patterns=True)

    def evaluated_validator(_root: Path) -> SimpleNamespace:
        return _evaluated_manifest()

    expected = renderer.render_table(
        renderer.pattern_coverage_rows((first, second), validator=evaluated_validator)
    )
    actual = renderer.render_table(
        renderer.pattern_coverage_rows(
            (second, first),
            catalogue_path=reordered_catalogue,
            validator=evaluated_validator,
        )
    )

    assert actual == expected


@pytest.mark.parametrize(
    ("provenance_field", "changed_value"),
    [
        (
            "systems_under_test",
            [
                {
                    "component_id": "different-sut",
                    "configuration_digest": "config-digest",
                }
            ],
        ),
        (
            "generator_configuration",
            [{"key": "seed", "value": "1"}],
        ),
    ],
)
def test_heterogeneous_receipt_provenance_fails_before_union(
    renderer: ModuleType,
    tmp_path: Path,
    provenance_field: str,
    changed_value: object,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_plan(first, reference_plan())
    _write_plan(second, reference_plan())
    manifests = {
        first.resolve(): _evaluated_manifest(),
        second.resolve(): _evaluated_manifest(**{provenance_field: changed_value}),
    }

    with pytest.raises(ValueError, match="heterogeneous immutable"):
        renderer.pattern_coverage_rows(
            (first, second),
            validator=lambda root: manifests[root],
        )


def test_selected_control_requires_a_catalogue_compatible_declared_pattern(
    renderer: ModuleType, tmp_path: Path
) -> None:
    root = tmp_path / "incompatible"
    plan = reference_plan().model_copy(
        update={"deployment_patterns": (DeploymentPattern.SHORT_LIVED_MINTING,)}
    )
    _write_plan(root, plan)

    with pytest.raises(ValueError, match=r"SW-AA-L03.*catalogue-compatible"):
        renderer.pattern_coverage_rows(
            (root,),
            validator=lambda _root: _evaluated_manifest(),
        )


@pytest.mark.parametrize(
    ("control_id", "pattern", "message"),
    [
        ("SW-AA-C99", None, "unknown control ID"),
        (None, "unknown-pattern", "unknown deployment pattern"),
    ],
)
def test_unknown_catalogue_values_fail_loudly(
    renderer: ModuleType,
    tmp_path: Path,
    control_id: str | None,
    pattern: str | None,
    message: str,
) -> None:
    catalogue = _catalogue_with(
        tmp_path,
        control_id=control_id,
        pattern=pattern,
    )

    with pytest.raises(ValueError, match=message):
        renderer.load_catalogue(catalogue)


@pytest.mark.parametrize(
    ("controls", "message"),
    [
        ({}, "controls list"),
        (["not-a-mapping"], "entries must be mappings"),
    ],
)
def test_malformed_catalogue_structure_fails_loudly(
    renderer: ModuleType, tmp_path: Path, controls: object, message: str
) -> None:
    catalogue = _catalogue_with(tmp_path, controls=controls)

    with pytest.raises(ValueError, match=message):
        renderer.load_catalogue(catalogue)


def test_non_evaluated_receipts_do_not_count_or_read_plan(
    renderer: ModuleType, tmp_path: Path
) -> None:
    rows = renderer.pattern_coverage_rows(
        (tmp_path / "non-evaluated",),
        validator=lambda _root: SimpleNamespace(
            evaluation_status=EvaluationStatus.NOT_EVALUATED
        ),
    )

    assert all(not row.declared_compatible_patterns for row in rows)


def test_check_detects_and_repairs_a_stale_block(
    renderer: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = tmp_path / "design-intent-assumptions.md"
    document.write_text(
        f"before\n{renderer.BEGIN}\n\nstale\n\n{renderer.END}\nafter\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(renderer, "DOC_PATH", document)

    assert renderer.main(["--check"]) == 1
    assert renderer.main([]) == 0
    assert renderer.main(["--check"]) == 0


@pytest.mark.parametrize(
    "document",
    [
        "no markers\n",
        "\n".join(("before", "{begin}", "one", "{end}", "{begin}", "two", "{end}")),
    ],
)
def test_malformed_generated_markers_fail_loudly(
    renderer: ModuleType, document: str
) -> None:
    rendered = document.format(begin=renderer.BEGIN, end=renderer.END)

    with pytest.raises(ValueError, match="generated block"):
        renderer.replace_block(rendered, "table")


@pytest.mark.parametrize("ending", ("\r\n", "\n\n", ""))
def test_check_rejects_noncanonical_line_endings_and_trailing_newlines(
    renderer: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ending: str
) -> None:
    document = tmp_path / "design-intent-assumptions.md"
    document.write_bytes(
        f"before\n{renderer.BEGIN}\n\nplaceholder\n\n{renderer.END}{ending}".encode()
    )
    monkeypatch.setattr(renderer, "DOC_PATH", document)

    assert renderer.main(["--check"]) == 1
