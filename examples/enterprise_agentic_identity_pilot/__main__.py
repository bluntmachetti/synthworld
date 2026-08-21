"""Three-process CLI for the enterprise-agentic identity policy pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from examples.enterprise_agentic_identity_pilot.policies import build_policy_traces
from examples.enterprise_agentic_identity_pilot.rendering import (
    write_evaluator_report_html,
)
from synthworld.agentic import trace_submission_from_jsonl, trace_submission_to_jsonl
from synthworld.agentic.enterprise import (
    EnterpriseAgenticGeneratedBenchmarkV1,
    EnterpriseAgenticGenerationConfigV1,
    evaluate_generated_enterprise_agentic_trace,
    export_generated_enterprise_agentic_benchmark,
    generate_enterprise_agentic_world,
    generated_enterprise_agentic_artifact_checksums,
    generated_enterprise_agentic_public_artifact_set_sha256,
    load_generated_enterprise_agentic_benchmark,
    load_generated_enterprise_agentic_public_tree,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
)
from synthworld.evaluation import EvaluationReport
from synthworld.explorer import write_generated_enterprise_agentic_html

DEFAULT_SEED = 20_260_821
_STRATEGIES = ("rbac", "abac", "rebac", "combined")
_POLICY_OVERLAY = Path(__file__).with_name("policy-overlay.json")
_POLICY_IMPLEMENTATION = Path(__file__).with_name("policies.py")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _policy_source_binding() -> dict[str, str]:
    return {
        "implementation_sha256": _sha256(_POLICY_IMPLEMENTATION.read_bytes()),
        "overlay_sha256": _sha256(_POLICY_OVERLAY.read_bytes()),
    }


def _verified_submission_payloads(
    submissions: Path,
    *,
    expected_benchmark_identity: dict[str, object],
    expected_public_artifact_set_sha256: str,
) -> tuple[dict[str, bytes], bytes]:
    expected_files = {"manifest.json"} | {f"{name}.jsonl" for name in _STRATEGIES}
    try:
        actual_files = {item.name for item in submissions.iterdir()}
    except OSError as error:
        raise ValueError("submission directory is unavailable") from error
    if actual_files != expected_files:
        raise ValueError("submission directory has an unexpected file inventory")

    manifest_payload = (submissions / "manifest.json").read_bytes()
    manifest_value: object = json.loads(manifest_payload)
    if not isinstance(manifest_value, dict):
        raise ValueError("submission manifest must be a JSON object")
    if canonical_json_value_bytes(manifest_value) != manifest_payload:
        raise ValueError("submission manifest must use canonical JSON")
    if set(manifest_value) != {
        "benchmark_identity",
        "derived_from_public_only",
        "policy_sources",
        "public_artifact_set_sha256",
        "strategies",
        "synthetic",
    }:
        raise ValueError("submission manifest has an unexpected field inventory")
    if manifest_value.get("derived_from_public_only") is not True:
        raise ValueError("submission manifest must declare public-only derivation")
    if manifest_value.get("synthetic") is not True:
        raise ValueError("submission manifest must be marked synthetic")
    if (
        manifest_value.get("public_artifact_set_sha256")
        != expected_public_artifact_set_sha256
    ):
        raise ValueError("submission public artifact set does not match benchmark")
    if manifest_value.get("benchmark_identity") != expected_benchmark_identity:
        raise ValueError("submission benchmark identity does not match benchmark")
    if manifest_value.get("policy_sources") != _policy_source_binding():
        raise ValueError("submission policy sources do not match this pilot")
    entries = manifest_value.get("strategies")
    if not isinstance(entries, list) or len(entries) != len(_STRATEGIES):
        raise ValueError("submission manifest has an unexpected strategy inventory")

    payloads: dict[str, bytes] = {}
    for expected_name, entry in zip(_STRATEGIES, entries, strict=True):
        if (
            not isinstance(entry, dict)
            or set(entry) != {"name", "sha256"}
            or entry.get("name") != expected_name
        ):
            raise ValueError("submission manifest strategies are not canonical")
        expected_digest = entry.get("sha256")
        if not isinstance(expected_digest, str):
            raise ValueError("submission manifest digest must be a string")
        payload = (submissions / f"{expected_name}.jsonl").read_bytes()
        if _sha256(payload) != expected_digest:
            raise ValueError(f"submission digest mismatch for {expected_name}")
        payloads[expected_name] = payload
    return payloads, manifest_payload


def _generate(args: argparse.Namespace) -> int:
    output = cast(Path, args.output)
    if output.exists():
        raise FileExistsError(f"pilot output already exists: {output}")
    generated = generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=cast(int, args.seed))
    )
    benchmark_root = output / "benchmark"
    export_generated_enterprise_agentic_benchmark(benchmark_root, generated)

    overlay: object = json.loads(_POLICY_OVERLAY.read_text(encoding="utf-8"))
    _write_new(
        output / "experiment" / "policy-overlay.json",
        canonical_json_value_bytes(overlay),
    )
    _write_new(
        output / "experiment" / "world-summary.json",
        canonical_json_value_bytes(_world_summary_from_generated(generated)),
    )
    public_html = output / "visuals" / "world-public.html"
    public_html.parent.mkdir(parents=True, exist_ok=True)
    write_generated_enterprise_agentic_html(
        public_html,
        public_package=benchmark_root / "public",
    )
    print(
        "Generated public/evaluator benchmark split and public Explorer HTML -> "
        f"{output}"
    )
    return 0


def _world_summary_from_generated(
    generated: EnterpriseAgenticGeneratedBenchmarkV1,
) -> dict[str, int | str]:
    snapshot = generated.public.snapshot
    return {
        "action_cases": len(generated.public.scenario.action_event_ids),
        "departments": len(snapshot.departments),
        "events": len(generated.public.events),
        "logical_agents": len(snapshot.agents),
        "organisations": len(snapshot.organisations),
        "principals": len(snapshot.principals),
        "resources": len(snapshot.resources),
        "seed": generated.identity.seed,
        "world_id": generated.identity.world_id,
    }


def _run_policies(args: argparse.Namespace) -> int:
    public_package = cast(Path, args.public_package)
    output = cast(Path, args.output)
    if output.exists():
        raise FileExistsError(f"submission output already exists: {output}")
    public = load_generated_enterprise_agentic_public_tree(public_package)
    digests: dict[str, str] = {}
    for name, submission in build_policy_traces(public.benchmark):
        payload = trace_submission_to_jsonl(submission).encode("utf-8")
        _write_new(output / f"{name}.jsonl", payload)
        digests[name] = _sha256(payload)
    _write_new(
        output / "manifest.json",
        canonical_json_value_bytes(
            {
                "benchmark_identity": public.identity.model_dump(mode="json"),
                "derived_from_public_only": True,
                "policy_sources": _policy_source_binding(),
                "public_artifact_set_sha256": (
                    generated_enterprise_agentic_public_artifact_set_sha256(public)
                ),
                "strategies": [
                    {"name": name, "sha256": digests[name]} for name in _STRATEGIES
                ],
                "synthetic": True,
            }
        ),
    )
    print(f"Ran four decision-only policy views from public artifacts -> {output}")
    return 0


def _score(args: argparse.Namespace) -> int:
    benchmark_root = cast(Path, args.benchmark_root)
    submissions = cast(Path, args.submissions)
    output = cast(Path, args.output)
    if output.exists():
        raise FileExistsError(f"evaluator output already exists: {output}")
    generated = load_generated_enterprise_agentic_benchmark(benchmark_root)
    benchmark_checksums = dict(
        generated_enterprise_agentic_artifact_checksums(generated)
    )
    submission_payloads, submission_manifest_payload = _verified_submission_payloads(
        submissions,
        expected_benchmark_identity=generated.identity.model_dump(mode="json"),
        expected_public_artifact_set_sha256=benchmark_checksums["public"],
    )
    reports: list[tuple[str, EvaluationReport]] = []
    report_digests: dict[str, str] = {}
    for name in _STRATEGIES:
        submission = trace_submission_from_jsonl(
            submission_payloads[name].decode("utf-8")
        )
        report = evaluate_generated_enterprise_agentic_trace(submission, generated)
        payload = canonical_json_bytes(report)
        _write_new(output / "reports" / f"{name}.json", payload)
        report_digests[name] = _sha256(payload)
        reports.append((name, report))

    comparison_html = output / "policy-comparison.html"
    write_evaluator_report_html(
        comparison_html,
        world_summary=_world_summary_from_generated(generated),
        strategy_reports=tuple(reports),
    )
    evaluator_html = output / "world-evaluator.html"
    write_generated_enterprise_agentic_html(
        evaluator_html,
        public_package=benchmark_root / "public",
        evaluator_package=benchmark_root / "evaluator",
    )
    _write_new(
        output / "manifest.json",
        canonical_json_value_bytes(
            {
                "contains_reference_truth": True,
                "html": [
                    {
                        "name": comparison_html.name,
                        "sha256": _sha256(comparison_html.read_bytes()),
                    },
                    {
                        "name": evaluator_html.name,
                        "sha256": _sha256(evaluator_html.read_bytes()),
                    },
                ],
                "reports": [
                    {"name": name, "sha256": report_digests[name]}
                    for name in _STRATEGIES
                ],
                "source": {
                    "benchmark_identity": generated.identity.model_dump(mode="json"),
                    "evaluator_artifact_set_sha256": benchmark_checksums["evaluator"],
                    "policy_sources": _policy_source_binding(),
                    "public_artifact_set_sha256": benchmark_checksums["public"],
                    "submission_manifest_sha256": _sha256(submission_manifest_payload),
                },
                "submissions": [
                    {"name": name, "sha256": _sha256(submission_payloads[name])}
                    for name in _STRATEGIES
                ],
                "synthetic": True,
            }
        ),
    )
    print(f"Scored policy views and wrote watermarked evaluator HTML -> {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an experiment-owned RBAC/ABAC/ReBAC comparison over one "
            "generated enterprise-agentic SynthWorld package."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="generate the split world")
    generate.add_argument("--seed", type=int, default=DEFAULT_SEED)
    generate.add_argument("--output", type=Path, required=True)
    generate.set_defaults(handler=_generate)

    run = commands.add_parser(
        "run-policies", help="run decision-only policies from a public tree"
    )
    run.add_argument("--public-package", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.set_defaults(handler=_run_policies)

    score = commands.add_parser(
        "score", help="score submissions in a separate evaluator process"
    )
    score.add_argument("--benchmark-root", type=Path, required=True)
    score.add_argument("--submissions", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    score.set_defaults(handler=_score)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = cast(Callable[[argparse.Namespace], int], args.handler)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
