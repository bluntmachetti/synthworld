"""Generate deterministic, submission-only C08 v2 baseline records."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from synthworld.agentic.c08_v2 import (
    C08AsteriaBenchmarkV2,
    C08AsteriaSubmissionV2,
    C08SubmissionRowV2,
    evaluate_c08_submission,
    generate_c08_asteria_v2,
    reference_c08_submission,
)
from synthworld.agentic.enterprise.c08_v2 import (
    C08EvidenceObservationV2,
    C08ReferenceBundleV2,
    C08SubmissionV2,
    evaluate_c08,
    generate_c08_reference,
    reference_submission_from_public,
)

DEFAULT_SEED = 20260809
SCHEMA_VERSION = "2.0.0"
ASTERIA_CASES = (
    "exact",
    "missing",
    "fabricated",
    "wrong_action",
    "extra",
    "discarded",
)
ENTERPRISE_CASES = ("exact", "missing", "fabricated", "wrong_action", "extra")


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _replace_asteria_row(
    submission: C08AsteriaSubmissionV2,
    action_event_id: str,
    retained_observation_ids: tuple[str, ...],
) -> C08AsteriaSubmissionV2:
    rows = tuple(
        row
        if row.action_event_id != action_event_id
        else C08SubmissionRowV2(
            action_event_id=action_event_id,
            retained_observation_ids=retained_observation_ids,
        )
        for row in submission.rows
    )
    return submission.model_copy(update={"rows": rows})


def _asteria_submission(
    benchmark: C08AsteriaBenchmarkV2, case: str
) -> C08AsteriaSubmissionV2:
    reference = reference_c08_submission(benchmark)
    if case == "exact":
        return reference
    binding = next(
        item for item in benchmark.evaluator.bindings if item.scenario_kind.value == case
    )
    row = next(
        item for item in reference.rows if item.action_event_id == binding.action_event_id
    )
    if case in {"missing", "discarded"}:
        return _replace_asteria_row(
            reference,
            binding.action_event_id,
            row.retained_observation_ids[:-1],
        )
    if case == "fabricated":
        return _replace_asteria_row(
            reference,
            binding.action_event_id,
            (*row.retained_observation_ids, "fabricated-observation"),
        )
    if case == "wrong_action":
        other_observation_id = next(
            item.observation_id
            for item in benchmark.public.evidence_observations
            if item.action_event_id != binding.action_event_id
        )
        return _replace_asteria_row(
            reference, binding.action_event_id, (other_observation_id,)
        )
    if case == "extra":
        extra_observation_id = next(
            item.observation_id
            for item in benchmark.public.evidence_observations
            if item.action_event_id == binding.action_event_id
            and item.observation_id not in row.retained_observation_ids
        )
        return _replace_asteria_row(
            reference,
            binding.action_event_id,
            (*row.retained_observation_ids, extra_observation_id),
        )
    raise ValueError(f"unsupported Asteria C08 baseline case: {case}")


def _renumber_enterprise(
    submission: C08SubmissionV2,
    observations: Sequence[C08EvidenceObservationV2],
) -> C08SubmissionV2:
    return submission.model_copy(
        update={
            "observations": tuple(
                observation.model_copy(update={"sequence": index})
                for index, observation in enumerate(observations)
            )
        }
    )


def _enterprise_submission(bundle: C08ReferenceBundleV2, case: str) -> C08SubmissionV2:
    reference = reference_submission_from_public(bundle.public)
    if case == "exact":
        return reference
    actions_by_name = {action.action: action for action in bundle.public.actions}
    target_name = {
        "missing": "write",
        "fabricated": "delete",
        "wrong_action": "write",
        "extra": "delete",
    }.get(case)
    if target_name is None:
        raise ValueError(f"unsupported enterprise C08 baseline case: {case}")
    target = actions_by_name[target_name]
    observations = list(reference.observations)
    target_indexes = [
        index
        for index, observation in enumerate(observations)
        if observation.action_id == target.action_id
    ]
    if case == "missing":
        observations.pop(target_indexes[-1])
    elif case == "fabricated":
        observations.append(
            C08EvidenceObservationV2(
                observation_id="baseline-fabricated-observation",
                sequence=0,
                action_id=target.action_id,
                tenant_id=target.tenant_id,
                evidence_id="baseline-fabricated-evidence",
            )
        )
    elif case == "wrong_action":
        other_evidence_id = next(
            event.evidence_id
            for event in bundle.public.evidence_events
            if event.action_id != target.action_id
        )
        observations.append(
            C08EvidenceObservationV2(
                observation_id="baseline-wrong-action-observation",
                sequence=0,
                action_id=target.action_id,
                tenant_id=target.tenant_id,
                evidence_id=other_evidence_id,
            )
        )
    else:
        extra_evidence_id = next(
            event.evidence_id
            for event in bundle.public.evidence_events
            if event.action_id == target.action_id
            and event.evidence_id
            not in {
                observation.evidence_id
                for observation in reference.observations
                if observation.action_id == target.action_id
            }
        )
        observations.append(
            C08EvidenceObservationV2(
                observation_id="baseline-extra-observation",
                sequence=0,
                action_id=target.action_id,
                tenant_id=target.tenant_id,
                evidence_id=extra_evidence_id,
            )
        )
    return _renumber_enterprise(reference, observations)


def _envelope(
    *,
    lineage: str,
    case: str,
    seed: int,
    submission: Any,
    result: Any,
) -> bytes:
    return _canonical_json_bytes(
        {
            "baseline_id": f"{lineage}-c08-v2-{case}",
            "case": case,
            "lineage": lineage,
            "schema_version": SCHEMA_VERSION,
            "seed": seed,
            "submission": submission.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
    )


def _expected_files() -> set[str]:
    return {
        *(f"asteria/{case}.json" for case in ASTERIA_CASES),
        *(f"enterprise/{case}.json" for case in ENTERPRISE_CASES),
    }


def _assert_inventory(root: Path) -> None:
    expected = _expected_files()
    allowed_directories = {"asteria", "enterprise"}
    if root.exists() and not root.is_dir():
        raise RuntimeError(f"C08 baseline root is not a directory: {root}")
    if not root.exists():
        root.mkdir(parents=True)
        return
    unexpected: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            unexpected.append(relative)
        elif path.is_dir() and relative in allowed_directories:
            continue
        elif path.is_file() and relative in expected:
            continue
        else:
            unexpected.append(relative)
    if unexpected:
        raise RuntimeError(
            "unexpected C08 baseline fixture entries: " + ", ".join(sorted(unexpected))
        )


def write_baselines(root: Path, seed: int = DEFAULT_SEED) -> None:
    """Write all expected baseline files without accepting unknown entries."""

    _assert_inventory(root)
    (root / "asteria").mkdir(exist_ok=True)
    (root / "enterprise").mkdir(exist_ok=True)

    asteria = generate_c08_asteria_v2(seed)
    for case in ASTERIA_CASES:
        submission = _asteria_submission(asteria, case)
        result = evaluate_c08_submission(asteria, submission)
        (root / "asteria" / f"{case}.json").write_bytes(
            _envelope(
                lineage="asteria",
                case=case,
                seed=seed,
                submission=submission,
                result=result,
            )
        )

    enterprise = generate_c08_reference(seed)
    for case in ENTERPRISE_CASES:
        submission = _enterprise_submission(enterprise, case)
        result = evaluate_c08(
            public=enterprise.public,
            evaluator=enterprise.evaluator,
            submission=submission,
        )
        (root / "enterprise" / f"{case}.json").write_bytes(
            _envelope(
                lineage="enterprise",
                case=case,
                seed=seed,
                submission=submission,
                result=result,
            )
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tests/fixtures/c08_v2",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    write_baselines(args.output, seed=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
