"""Render declared deployment-pattern coverage from validated receipts.

The report joins each selected control in an evaluated agent-authority receipt to
the control catalogue's ``applicable_patterns``. These are run-level declarations
intersected with selected-control applicability, not per-control exercise,
observation, runtime topology, or enforcement proof.

Multiple evaluated receipts may contribute declarations only when their immutable
benchmark, SUT, adapter, configuration, and run-topology provenance is identical.
The renderer fails rather than constructing a support-looking union across
heterogeneous runs.

Usage::

    uv run python agent-authority-contract/tools/render_pattern_coverage.py
    uv run python agent-authority-contract/tools/render_pattern_coverage.py --check
    uv run python agent-authority-contract/tools/render_pattern_coverage.py \
        receipt-a receipt-b
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from synthworld.agent_authority.common import (
    CONTROL_ORDER,
    AgentAuthorityControlId,
    CoverageDisposition,
    DeploymentPattern,
)
from synthworld.agent_authority.models import AgentAuthorityRunPlanV1
from synthworld.agent_authority.reference import (
    build_reference_agent_authority_run_receipt,
)
from synthworld.assurance.agent_authority import (
    RUN_PLAN_PATH,
    validate_agent_authority_run_receipt,
)
from synthworld.assurance.models import EvaluationStatus
from synthworld.assurance.models_v2 import RunReceiptManifestV2

CONTRACT_DIR = Path(__file__).resolve().parent.parent
CATALOGUE_PATH = CONTRACT_DIR / "control-catalogue.yaml"
DOC_PATH = CONTRACT_DIR / "docs" / "design-intent-assumptions.md"

BEGIN = "<!-- BEGIN GENERATED: pattern-coverage (render_pattern_coverage.py) -->"
END = "<!-- END GENERATED: pattern-coverage -->"

_AGGREGATION_PROVENANCE_FIELDS = {
    "adapter",
    "benchmark",
    "build_environment",
    "digest_algorithm",
    "event_schedule",
    "evidence_claim",
    "generator_configuration",
    "schema_versions",
    "scoring_formula_versions",
    "serialization",
    "systems_under_test",
}
_AGGREGATION_TOPOLOGY_FIELDS = {
    "authority_path_component_ids",
    "direct_path_reachability",
    "enforcement_point_ids",
    "isolation_mechanism",
}


@dataclass(frozen=True)
class PatternCoverageRow:
    """One control's applicable and run-level declared deployment patterns."""

    control_id: AgentAuthorityControlId
    applicable_patterns: tuple[str, ...]
    declared_compatible_patterns: tuple[str, ...]

    @property
    def undeclared_applicable_patterns(self) -> tuple[str, ...]:
        """Return applicable patterns absent from selected run-level declarations."""

        return tuple(
            pattern
            for pattern in self.applicable_patterns
            if pattern not in self.declared_compatible_patterns
        )


def _pattern_name(value: DeploymentPattern | str) -> str:
    """Return the catalogue spelling for a deployment pattern or fail loudly."""

    raw = str(value)
    normalized = raw.replace("-", "_")
    try:
        return DeploymentPattern(normalized).value.replace("_", "-")
    except ValueError as error:
        raise ValueError(f"unknown deployment pattern: {raw}") from error


def load_catalogue(
    path: Path = CATALOGUE_PATH,
) -> dict[AgentAuthorityControlId, tuple[str, ...]]:
    """Load every protocol control and its canonically ordered applicability set."""

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("controls"), list):
        raise ValueError("control catalogue must contain a controls list")

    catalogue: dict[AgentAuthorityControlId, tuple[str, ...]] = {}
    for entry in document["controls"]:
        if not isinstance(entry, dict):
            raise ValueError("control catalogue entries must be mappings")
        raw_control_id = entry.get("control_id")
        try:
            control_id = AgentAuthorityControlId(raw_control_id)
        except ValueError as error:
            raise ValueError(f"unknown control ID: {raw_control_id}") from error
        if control_id in catalogue:
            raise ValueError(f"duplicate control ID: {control_id.value}")
        patterns = entry.get("applicable_patterns")
        if not isinstance(patterns, list):
            raise ValueError(f"{control_id.value} applicable_patterns must be a list")
        canonical_patterns = tuple(sorted({_pattern_name(item) for item in patterns}))
        if len(canonical_patterns) != len(patterns):
            raise ValueError(f"duplicate pattern for {control_id.value}")
        catalogue[control_id] = canonical_patterns

    expected = set(CONTROL_ORDER)
    if set(catalogue) != expected:
        missing = sorted(item.value for item in expected - set(catalogue))
        unexpected = sorted(item.value for item in set(catalogue) - expected)
        raise ValueError(
            f"control catalogue IDs differ from protocol: missing={missing}; "
            f"unexpected={unexpected}"
        )
    return catalogue


def _canonical_receipt_roots(receipt_roots: Iterable[Path]) -> tuple[Path, ...]:
    """Deduplicate and canonically order roots without exposing paths in output."""

    return tuple(sorted({Path(root).resolve() for root in receipt_roots}, key=str))


def _aggregation_provenance(
    manifest: RunReceiptManifestV2,
    plan: AgentAuthorityRunPlanV1,
) -> str:
    """Return canonical immutable provenance for safe declaration aggregation."""

    document = {
        "manifest": manifest.model_dump(
            mode="json",
            include=_AGGREGATION_PROVENANCE_FIELDS,
        ),
        "run_plan_topology": plan.model_dump(
            mode="json",
            include=_AGGREGATION_TOPOLOGY_FIELDS,
        ),
    }
    return json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def pattern_coverage_rows(
    receipt_roots: Iterable[Path],
    *,
    catalogue_path: Path = CATALOGUE_PATH,
    validator: Callable[
        [Path], RunReceiptManifestV2
    ] = validate_agent_authority_run_receipt,
) -> tuple[PatternCoverageRow, ...]:
    """Return per-control declared-pattern observations for validated receipts."""

    catalogue = load_catalogue(catalogue_path)
    declared_compatible: dict[AgentAuthorityControlId, set[str]] = {
        control_id: set() for control_id in CONTROL_ORDER
    }
    aggregation_provenance: str | None = None
    for root in _canonical_receipt_roots(receipt_roots):
        manifest = validator(root)
        if manifest.evaluation_status is EvaluationStatus.NOT_EVALUATED:
            continue
        plan = AgentAuthorityRunPlanV1.model_validate(
            json.loads((root / RUN_PLAN_PATH).read_text(encoding="utf-8"))
        )
        receipt_provenance = _aggregation_provenance(manifest, plan)
        if aggregation_provenance is None:
            aggregation_provenance = receipt_provenance
        elif receipt_provenance != aggregation_provenance:
            raise ValueError(
                "cannot aggregate evaluated receipts with heterogeneous immutable "
                "receipt/SUT/config/topology provenance"
            )
        declared_patterns = {
            _pattern_name(pattern) for pattern in plan.deployment_patterns
        }
        selected_controls = (
            entry.control_id
            for entry in plan.control_coverage
            if entry.disposition is CoverageDisposition.SELECTED
        )
        for control_id in selected_controls:
            compatible_patterns = set(catalogue[control_id]) & declared_patterns
            if not compatible_patterns:
                raise ValueError(
                    f"{control_id.value} is selected but has no "
                    "catalogue-compatible declared deployment pattern"
                )
            declared_compatible[control_id].update(compatible_patterns)

    return tuple(
        PatternCoverageRow(
            control_id=control_id,
            applicable_patterns=catalogue[control_id],
            declared_compatible_patterns=tuple(sorted(declared_compatible[control_id])),
        )
        for control_id in CONTROL_ORDER
    )


def _render_patterns(patterns: tuple[str, ...]) -> str:
    """Render a pattern set without introducing a numerical coverage claim."""

    return "none" if not patterns else ", ".join(f"`{pattern}`" for pattern in patterns)


def render_table(rows: Iterable[PatternCoverageRow]) -> str:
    """Render the deterministic, per-control Markdown table."""

    lines = [
        "| control_id | applicable_patterns | declared_compatible_patterns | "
        "undeclared_applicable_patterns |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"`{row.control_id.value}` | "
            f"{_render_patterns(row.applicable_patterns)} | "
            f"{_render_patterns(row.declared_compatible_patterns)} | "
            f"{_render_patterns(row.undeclared_applicable_patterns)} |"
        )
    return "\n".join(lines)


def replace_block(markdown: str, table: str) -> str:
    """Replace the generated report block or fail instead of silently drifting."""

    pattern = re.compile(f"{re.escape(BEGIN)}.*?{re.escape(END)}", re.DOTALL)
    if (
        markdown.count(BEGIN) != 1
        or markdown.count(END) != 1
        or not pattern.search(markdown)
    ):
        raise ValueError(f"{DOC_PATH} has no pattern-coverage generated block")
    return pattern.sub(f"{BEGIN}\n\n{table}\n\n{END}", markdown)


def _canonical_markdown_bytes(markdown: str) -> bytes:
    """Serialize generated documentation as UTF-8 LF text with one final newline."""

    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    return f"{normalized.rstrip(chr(10))}\n".encode()


def _reference_rows() -> tuple[PatternCoverageRow, ...]:
    """Build the deterministic reference receipt used by the checked-in report."""

    with tempfile.TemporaryDirectory(
        prefix="synthworld-pattern-coverage-"
    ) as directory:
        root = Path(directory) / "reference-receipt"
        build_reference_agent_authority_run_receipt(root)
        return pattern_coverage_rows((root,))


def main(argv: list[str] | None = None) -> int:
    """Render or check the committed block from supplied or reference receipts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "receipt_roots",
        nargs="*",
        type=Path,
        help=(
            "validated agent-authority receipt roots; defaults to the reference receipt"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed report differs from derived coverage",
    )
    args = parser.parse_args(argv)

    rows = (
        pattern_coverage_rows(args.receipt_roots)
        if args.receipt_roots
        else _reference_rows()
    )
    current_bytes = DOC_PATH.read_bytes()
    current = current_bytes.decode("utf-8")
    updated = _canonical_markdown_bytes(replace_block(current, render_table(rows)))
    if args.check:
        if current_bytes != updated:
            print(
                f"STALE: {DOC_PATH} does not match declared receipt patterns",
                file=sys.stderr,
            )
            print("re-run without --check to regenerate", file=sys.stderr)
            return 1
        print("pattern coverage report matches validated receipts")
        return 0
    DOC_PATH.write_bytes(updated)
    print(f"wrote {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
