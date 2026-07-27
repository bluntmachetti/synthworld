"""Canonical JSON/JSONL artifacts for Asteria's public and oracle packages."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from synthworld.agentic.models import (
    AGENTIC_SCHEMA_VERSION,
    ActionAttempted,
    AgenticBenchmark,
    AgenticCase,
    AgenticEvaluatorBundle,
    AgenticEvent,
    AgenticPublicBundle,
    AgenticWorldSnapshot,
    AuthorityTruth,
    CanonicalBinding,
    CredentialIssued,
    DelegationGranted,
    LogicalAgent,
    Principal,
    PublicScenario,
    Resource,
    RuntimeSpawned,
)
from synthworld.models import SyntheticModel

_PUBLIC_BASE_PATHS = (
    "organisation.json",
    "principals.jsonl",
    "agents.jsonl",
    "runtimes.jsonl",
    "resources.jsonl",
    "public_credentials.jsonl",
    "public_delegations.jsonl",
    "public_events.jsonl",
    "tool_schemas/procurement-tools.json",
    "scenarios/procurement-delegation.json",
)
_EVALUATOR_BASE_PATHS = (
    "canonical_bindings.json",
    "authority_truth.jsonl",
    "cases.jsonl",
    "expected_decisions.jsonl",
    "expected_side_effects.jsonl",
    "expected_provenance.jsonl",
    "evidence_epochs.jsonl",
)


class AgenticArtifactError(ValueError):
    """Raised when a frozen artifact set is incomplete or has been changed."""


def agentic_public_artifacts(public: AgenticPublicBundle) -> dict[str, bytes]:
    """Return the complete canonical public artifact set, including manifest."""

    snapshot = public.snapshot
    runtimes = tuple(
        event.payload.runtime
        for event in public.events
        if isinstance(event.payload, RuntimeSpawned)
    )
    credentials = tuple(
        event.payload.credential
        for event in public.events
        if isinstance(event.payload, CredentialIssued)
    )
    delegations = tuple(
        event.payload.delegation
        for event in public.events
        if isinstance(event.payload, DelegationGranted)
    )
    artifacts = {
        "organisation.json": _json_bytes(
            {
                "schema_version": snapshot.schema_version,
                "world_id": snapshot.world_id,
                "world_version": snapshot.world_version,
                "seed": snapshot.seed,
                "organisations": _json_values(snapshot.organisations),
                "departments": _json_values(snapshot.departments),
                "policies": _json_values(snapshot.policies),
                "initial_evidence_refs": list(snapshot.initial_evidence_refs),
            }
        ),
        "principals.jsonl": _jsonl_bytes(snapshot.principals),
        "agents.jsonl": _jsonl_bytes(snapshot.agents),
        "runtimes.jsonl": _jsonl_bytes(runtimes),
        "resources.jsonl": _jsonl_bytes(snapshot.resources),
        "public_credentials.jsonl": _jsonl_bytes(credentials),
        "public_delegations.jsonl": _jsonl_bytes(delegations),
        "public_events.jsonl": _jsonl_bytes(public.events),
        "tool_schemas/procurement-tools.json": _json_bytes(_tool_schemas()),
        "scenarios/procurement-delegation.json": _model_json_bytes(public.scenario),
    }
    manifest = {
        "schema_version": AGENTIC_SCHEMA_VERSION,
        "world_id": snapshot.world_id,
        "world_version": snapshot.world_version,
        "seed": snapshot.seed,
        "artifact_set_digest": artifact_set_digest(artifacts),
        "artifacts": _hash_manifest(artifacts),
        "oracle_free": True,
    }
    return {"manifest.json": _json_bytes(manifest), **artifacts}


def agentic_evaluator_artifacts(
    benchmark: AgenticBenchmark,
) -> dict[str, bytes]:
    """Return the physically separate evaluator-only artifact set."""

    evaluator = benchmark.evaluator
    artifacts = {
        "canonical_bindings.json": _json_bytes(
            {
                "schema_version": evaluator.schema_version,
                "bindings": _json_values(evaluator.bindings),
            }
        ),
        "authority_truth.jsonl": _jsonl_bytes(evaluator.authority_truth),
        "cases.jsonl": _jsonl_bytes(evaluator.cases),
        "expected_decisions.jsonl": _jsonl_dicts(
            tuple(
                {
                    "action_event_id": item.action_event_id,
                    "decision_at_action": item.decision_at_action.value,
                    "decision_at_audit": item.decision_at_audit.value,
                    "failure_reasons_at_action": [
                        reason.value for reason in item.failure_reasons_at_action
                    ],
                    "failure_reasons_at_audit": [
                        reason.value for reason in item.failure_reasons_at_audit
                    ],
                }
                for item in evaluator.authority_truth
            )
        ),
        "expected_side_effects.jsonl": _jsonl_dicts(
            tuple(
                {
                    "action_event_id": item.action_event_id,
                    "expected_side_effect": item.expected_side_effect,
                }
                for item in evaluator.authority_truth
            )
        ),
        "expected_provenance.jsonl": _jsonl_dicts(
            tuple(
                {
                    "action_event_id": item.action_event_id,
                    "delegation_chain_ids": list(item.delegation_chain_ids),
                    "required_evidence_refs": list(item.required_evidence_refs),
                    "reconstructable_at_audit": item.reconstructable_at_audit,
                }
                for item in evaluator.authority_truth
            )
        ),
        "evidence_epochs.jsonl": _evidence_epochs(benchmark),
    }
    public = agentic_public_artifacts(benchmark.public)
    public_base = {path: public[path] for path in _PUBLIC_BASE_PATHS}
    checksums = {
        "schema_version": AGENTIC_SCHEMA_VERSION,
        "checksum_scheme": "sha256-artifact-set-v1",
        "public_artifact_set_digest": artifact_set_digest(public_base),
        "evaluator_artifact_set_digest": artifact_set_digest(artifacts),
        "public_artifacts": _hash_manifest(public_base),
        "evaluator_artifacts": _hash_manifest(artifacts),
    }
    return {**artifacts, "checksums.json": _json_bytes(checksums)}


def artifact_set_digest(artifacts: dict[str, bytes]) -> str:
    """Digest a named set, binding both every relative path and its bytes."""

    digest = hashlib.sha256()
    for path, content in sorted(artifacts.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def agentic_artifact_checksums(
    benchmark: AgenticBenchmark,
) -> tuple[tuple[str, str], ...]:
    """Return public/evaluator set digests suitable for evaluation reports."""

    public = agentic_public_artifacts(benchmark.public)
    evaluator = agentic_evaluator_artifacts(benchmark)
    return (
        (
            "public",
            artifact_set_digest({path: public[path] for path in _PUBLIC_BASE_PATHS}),
        ),
        (
            "evaluator",
            artifact_set_digest(
                {path: evaluator[path] for path in _EVALUATOR_BASE_PATHS}
            ),
        ),
    )


def export_agentic_benchmark(root: Path, benchmark: AgenticBenchmark) -> None:
    """Write public and evaluator trees below an explicit destination."""

    for package_name, artifacts in (
        ("public", agentic_public_artifacts(benchmark.public)),
        ("evaluator", agentic_evaluator_artifacts(benchmark)),
    ):
        for relative_path, content in artifacts.items():
            target = root / package_name / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)


def load_golden_agentic_benchmark() -> AgenticBenchmark:
    """Load and checksum-verify the packaged Asteria Agentic v1 fixture."""

    root = files("synthworld.benchmarks").joinpath("asteria-agentic-v1")
    public_root = root.joinpath("public")
    evaluator_root = root.joinpath("evaluator")
    _verify_artifacts(public_root, "manifest.json", _PUBLIC_BASE_PATHS, "artifacts")
    _verify_evaluator_artifacts(evaluator_root, public_root)

    organisation = _read_json(public_root.joinpath("organisation.json"))
    snapshot = AgenticWorldSnapshot(
        schema_version=organisation["schema_version"],
        world_id=organisation["world_id"],
        world_version=organisation["world_version"],
        seed=organisation["seed"],
        organisations=tuple(organisation["organisations"]),
        departments=tuple(organisation["departments"]),
        principals=_read_jsonl(public_root.joinpath("principals.jsonl"), Principal),
        agents=_read_jsonl(public_root.joinpath("agents.jsonl"), LogicalAgent),
        resources=_read_jsonl(public_root.joinpath("resources.jsonl"), Resource),
        policies=tuple(organisation["policies"]),
        initial_evidence_refs=tuple(organisation["initial_evidence_refs"]),
    )
    public = AgenticPublicBundle(
        snapshot=snapshot,
        events=_read_jsonl(public_root.joinpath("public_events.jsonl"), AgenticEvent),
        scenario=PublicScenario.model_validate_json(
            public_root.joinpath("scenarios/procurement-delegation.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    bindings_doc = _read_json(evaluator_root.joinpath("canonical_bindings.json"))
    evaluator = AgenticEvaluatorBundle(
        world_id=snapshot.world_id,
        world_version=snapshot.world_version,
        seed=snapshot.seed,
        audit_event_id=public.scenario.audit_event_id,
        bindings=TypeAdapter(tuple[CanonicalBinding, ...]).validate_python(
            bindings_doc["bindings"]
        ),
        authority_truth=_read_jsonl(
            evaluator_root.joinpath("authority_truth.jsonl"), AuthorityTruth
        ),
        cases=_read_jsonl(evaluator_root.joinpath("cases.jsonl"), AgenticCase),
    )
    return AgenticBenchmark(public=public, evaluator=evaluator)


def _verify_artifacts(
    root: Traversable,
    manifest_name: str,
    expected_paths: tuple[str, ...],
    hashes_key: str,
) -> None:
    manifest = _read_json(root.joinpath(manifest_name))
    hashes = manifest.get(hashes_key)
    if not isinstance(hashes, dict) or set(hashes) != set(expected_paths):
        raise AgenticArtifactError("agentic artifact manifest is incomplete")
    artifacts = {path: root.joinpath(path).read_bytes() for path in expected_paths}
    if hashes != _hash_manifest(artifacts) or manifest.get(
        "artifact_set_digest"
    ) != artifact_set_digest(artifacts):
        raise AgenticArtifactError("agentic artifact checksum verification failed")


def _verify_evaluator_artifacts(
    evaluator_root: Traversable, public_root: Traversable
) -> None:
    checksums = _read_json(evaluator_root.joinpath("checksums.json"))
    evaluator = {
        path: evaluator_root.joinpath(path).read_bytes()
        for path in _EVALUATOR_BASE_PATHS
    }
    public = {
        path: public_root.joinpath(path).read_bytes() for path in _PUBLIC_BASE_PATHS
    }
    if (
        checksums.get("evaluator_artifacts") != _hash_manifest(evaluator)
        or checksums.get("public_artifacts") != _hash_manifest(public)
        or checksums.get("evaluator_artifact_set_digest")
        != artifact_set_digest(evaluator)
        or checksums.get("public_artifact_set_digest") != artifact_set_digest(public)
    ):
        raise AgenticArtifactError("agentic evaluator checksum verification failed")


def _evidence_epochs(benchmark: AgenticBenchmark) -> bytes:
    action_events = {
        event.id: event
        for event in benchmark.public.events
        if isinstance(event.payload, ActionAttempted)
    }
    return _jsonl_dicts(
        tuple(
            {
                "action_event_id": truth.action_event_id,
                "action_event_index": action_events[truth.action_event_id].event_index,
                "audit_event_id": benchmark.evaluator.audit_event_id,
                "required_evidence_refs": list(truth.required_evidence_refs),
                "reconstructable_at_audit": truth.reconstructable_at_audit,
            }
            for truth in benchmark.evaluator.authority_truth
        )
    )


def _tool_schemas() -> dict[str, Any]:
    return {
        "schema_version": AGENTIC_SCHEMA_VERSION,
        "tools": [
            {
                "name": name,
                "resource_id": resource_id,
                "action": action,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["scope"],
                    "additionalProperties": False,
                },
            }
            for name, resource_id, action in (
                (
                    "read_supplier_directory",
                    "resource-supplier-directory",
                    "read",
                ),
                (
                    "request_supplier_quotation",
                    "resource-quotation-service",
                    "request_quotation",
                ),
                ("read_task_budget", "resource-task-budget", "read"),
                (
                    "compare_quotations",
                    "resource-quotation-comparison",
                    "compare",
                ),
                (
                    "create_draft_recommendation",
                    "resource-draft-recommendation",
                    "create_draft",
                ),
                (
                    "create_attenuated_delegation",
                    "resource-delegation-registry",
                    "create_delegation",
                ),
                (
                    "approve_supplier",
                    "resource-purchase-order",
                    "approve_supplier",
                ),
                ("create_purchase_order", "resource-purchase-order", "create"),
                ("submit_purchase_order", "resource-purchase-order", "submit"),
                ("read_payroll", "resource-payroll", "read"),
                ("read_orion_customer", "resource-orion-customer", "read"),
            )
        ],
    }


def _model_json_bytes(value: SyntheticModel) -> bytes:
    return f"{value.model_dump_json(indent=2)}\n".encode()


def _json_bytes(value: object) -> bytes:
    return f"{json.dumps(value, indent=2, sort_keys=True)}\n".encode()


def _json_values(values: tuple[SyntheticModel, ...]) -> list[Any]:
    return [item.model_dump(mode="json") for item in values]


def _jsonl_bytes(values: tuple[SyntheticModel, ...]) -> bytes:
    return "".join(f"{item.model_dump_json()}\n" for item in values).encode()


def _jsonl_dicts(values: tuple[dict[str, Any], ...]) -> bytes:
    return "".join(
        f"{json.dumps(item, sort_keys=True, separators=(',', ':'))}\n"
        for item in values
    ).encode()


def _hash_manifest(artifacts: dict[str, bytes]) -> dict[str, str]:
    return {
        path: hashlib.sha256(content).hexdigest()
        for path, content in sorted(artifacts.items())
    }


def _read_json(resource: Traversable) -> dict[str, Any]:
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AgenticArtifactError("agentic JSON document must be an object")
    return value


def _read_jsonl[ItemT](resource: Traversable, model: type[ItemT]) -> tuple[ItemT, ...]:
    adapter = TypeAdapter(model)
    return tuple(
        adapter.validate_json(line)
        for line in resource.read_text(encoding="utf-8").splitlines()
        if line
    )


__all__ = [
    "AgenticArtifactError",
    "agentic_artifact_checksums",
    "agentic_evaluator_artifacts",
    "agentic_public_artifacts",
    "artifact_set_digest",
    "export_agentic_benchmark",
    "load_golden_agentic_benchmark",
]
