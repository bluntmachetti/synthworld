"""Generate disclosure-safe, deterministic C08 v2 baseline records."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from synthworld.agentic.c08_v2 import (
    C08AsteriaBenchmarkV2,
    C08AsteriaSubmissionV2,
    C08MetricV2,
    C08SubmissionRowV2,
    evaluate_c08_submission,
    generate_c08_asteria_v2,
    semantic_c08_submission,
)
from synthworld.agentic.enterprise.c08_v2 import (
    C08_FROZEN_BENCHMARK_ID,
    C08EvaluationMetricV2,
    C08EvidenceObservationV2,
    C08ReferenceBundleV2,
    C08SubmissionV2,
    evaluate_c08,
    generate_c08_reference,
    reference_submission_from_public,
)
from synthworld.enterprise.canonical import canonical_json_bytes

DEFAULT_SEED = 20260809
ASTERIA_FAILURE_MODES = (
    "exact",
    "missing",
    "fabricated",
    "wrong_action",
    "extra",
    "discarded",
)
ENTERPRISE_FAILURE_MODES = (
    "exact",
    "missing",
    "fabricated",
    "wrong_action",
    "extra",
)
ASTERIA_FILE = "asteria/baseline-records.json"
ENTERPRISE_FILE = "enterprise/baseline-records.json"

Metric = C08MetricV2 | C08EvaluationMetricV2


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
    benchmark: C08AsteriaBenchmarkV2,
    failure_mode: str,
) -> C08AsteriaSubmissionV2:
    reference = semantic_c08_submission(benchmark.public)
    if failure_mode == "exact":
        return reference
    binding = next(
        item
        for item in benchmark.evaluator.bindings
        if item.scenario_kind.value == failure_mode
    )
    row = next(
        item for item in reference.rows if item.action_event_id == binding.action_event_id
    )
    if failure_mode in {"missing", "discarded"}:
        return _replace_asteria_row(
            reference,
            binding.action_event_id,
            row.retained_observation_ids[:-1],
        )
    if failure_mode == "fabricated":
        return _replace_asteria_row(
            reference,
            binding.action_event_id,
            (*row.retained_observation_ids, "fabricated-observation"),
        )
    if failure_mode == "wrong_action":
        other_observation_id = next(
            item.observation_id
            for item in benchmark.public.evidence_observations
            if item.action_event_id != binding.action_event_id
        )
        return _replace_asteria_row(
            reference,
            binding.action_event_id,
            (other_observation_id,),
        )
    if failure_mode == "extra":
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
    raise ValueError(
        f"unsupported Asteria C08 baseline failure mode: {failure_mode}"
    )


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


def _enterprise_submission(
    bundle: C08ReferenceBundleV2,
    failure_mode: str,
) -> C08SubmissionV2:
    reference = reference_submission_from_public(bundle.public)
    if failure_mode == "exact":
        return reference
    actions_by_name = {action.action: action for action in bundle.public.actions}
    target_name = {
        "missing": "write",
        "fabricated": "delete",
        "wrong_action": "write",
        "extra": "delete",
    }.get(failure_mode)
    if target_name is None:
        raise ValueError(
            "unsupported enterprise C08 baseline failure mode: "
            f"{failure_mode}"
        )
    target = actions_by_name[target_name]
    observations = list(reference.observations)
    target_indexes = [
        index
        for index, observation in enumerate(observations)
        if observation.action_id == target.action_id
    ]
    if failure_mode == "missing":
        observations.pop(target_indexes[-1])
    elif failure_mode == "fabricated":
        observations.append(
            C08EvidenceObservationV2(
                observation_id="baseline-fabricated-observation",
                sequence=0,
                action_id=target.action_id,
                tenant_id=target.tenant_id,
                evidence_id="baseline-fabricated-evidence",
            )
        )
    elif failure_mode == "wrong_action":
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
        selected_ids = {
            observation.evidence_id
            for observation in reference.observations
            if observation.action_id == target.action_id
        }
        extra_evidence_id = next(
            event.evidence_id
            for event in bundle.public.evidence_events
            if event.action_id == target.action_id
            and event.evidence_id not in selected_ids
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


def _metric_records(metrics: Sequence[Metric]) -> list[dict[str, object]]:
    return [
        {
            "name": metric.name,
            "numerator": metric.numerator,
            "denominator": metric.denominator,
            "value": metric.value,
            "denominator_meaning": metric.denominator_meaning,
        }
        for metric in metrics
    ]


def _baseline_record(
    failure_mode: str,
    submission: BaseModel,
    metrics: Sequence[Metric],
) -> dict[str, object]:
    return {
        "failure_mode": failure_mode,
        "submission_digest": hashlib.sha256(
            canonical_json_bytes(submission)
        ).hexdigest(),
        "metrics": _metric_records(metrics),
    }


def build_asteria_baseline_records(seed: int = DEFAULT_SEED) -> dict[str, object]:
    benchmark = generate_c08_asteria_v2(seed)
    records: list[dict[str, object]] = []
    for failure_mode in ASTERIA_FAILURE_MODES:
        submission = _asteria_submission(benchmark, failure_mode)
        report = evaluate_c08_submission(benchmark, submission)
        records.append(
            _baseline_record(failure_mode, submission, report.metrics)
        )
    return {
        "benchmark_id": benchmark.benchmark_id,
        "schema_version": benchmark.schema_version,
        "public_input_digest": benchmark.evaluator.public_input_digest,
        "records": records,
    }


def build_enterprise_baseline_records(
    seed: int = DEFAULT_SEED,
) -> dict[str, object]:
    bundle = generate_c08_reference(seed)
    records: list[dict[str, object]] = []
    for failure_mode in ENTERPRISE_FAILURE_MODES:
        submission = _enterprise_submission(bundle, failure_mode)
        report = evaluate_c08(
            public=bundle.public,
            evaluator=bundle.evaluator,
            submission=submission,
        )
        records.append(
            _baseline_record(failure_mode, submission, report.metrics)
        )
    return {
        "benchmark_id": C08_FROZEN_BENCHMARK_ID,
        "schema_version": bundle.public.schema_version,
        "public_input_digest": bundle.evaluator.public_input_digest,
        "records": records,
    }


def _assert_inventory(root: Path) -> None:
    expected_files = {ASTERIA_FILE, ENTERPRISE_FILE}
    allowed_directories = {"asteria", "enterprise"}
    if root.is_symlink():
        raise RuntimeError(f"C08 baseline output root must not be a symlink: {root}")
    if root.exists() and not root.is_dir():
        raise RuntimeError(f"C08 baseline output root is not a directory: {root}")
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
        elif path.is_file() and relative in expected_files:
            continue
        else:
            unexpected.append(relative)
    if unexpected:
        raise RuntimeError(
            "unexpected C08 baseline fixture entries: "
            + ", ".join(sorted(unexpected))
        )


def write_baselines(root: Path, seed: int = DEFAULT_SEED) -> None:
    """Write the two aggregate baseline files with an exact inventory."""

    _assert_inventory(root)
    (root / "asteria").mkdir(exist_ok=True)
    (root / "enterprise").mkdir(exist_ok=True)
    (root / ASTERIA_FILE).write_bytes(
        _canonical_json_bytes(build_asteria_baseline_records(seed))
    )
    (root / ENTERPRISE_FILE).write_bytes(
        _canonical_json_bytes(build_enterprise_baseline_records(seed))
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
