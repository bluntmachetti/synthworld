"""Claude LLM adapter for SynthWorld public benchmarks.

This example integrates a real LLM system (Claude, via the Anthropic API)
against two SynthWorld tasks using only product-safe public inputs:

- ``agentic`` judges every Asteria Agentic v1 action event from the public
  package and writes an ``ObservedActionTrace`` JSONL submission.
- ``extraction`` extracts exact PII spans from the public extraction corpus
  and writes an ``ExtractionPredictionSet`` JSON submission.

The agentic public directory is verified before anything is sent to the
model: its ``manifest.json`` must be present and declare ``oracle_free:
true``; every listed artifact name must be a normalized relative path that
stays beneath the public directory without crossing symlinks; every listed
artifact must match its recorded SHA-256 and the artifact-set digest;
unlisted files are rejected; and both the model context and the scenario
action list are built from the verified artifact bytes only. Passing the
benchmark root instead of its ``public/`` subdirectory therefore fails
loudly instead of leaking evaluator truth.

Every model response is cached under a responses directory inside a
validated envelope, stored under a SHA-256-derived filename so
benchmark-controlled unit IDs never become filesystem paths. The envelope
records its unit ID, a fingerprint over the adapter version, requested
model, generation configuration (fallback mode, output budget, beta
headers), instructions, response schema, and exact input bytes, plus
provenance metadata: requested and served model, stop reason, fallback
occurrence, response ID, and SDK version. Cached and freshly returned
outputs are validated against the task's response contract, and a cached
envelope whose unit ID, fingerprint, provenance, or output shape does not
match the current run is rejected rather than silently reused. Each run
writes a ``run-manifest.json`` binding the evidence it describes: prompt,
schema, and input digests, per-unit fingerprints, an artifact-set digest
over the response envelopes, and the output file's SHA-256. Score the
outputs with ``synthworld evaluate agentic`` and ``synthworld evaluate
extraction``.

Uncached calls require the Anthropic SDK plus API credentials (run via
``uv run --with anthropic``). Server-side refusal fallbacks are disabled by
default so results stay attributable to one requested model; pass
``--fallbacks`` to opt in, in which case the served model per response is
recorded in the cache envelopes. The adapter reads only public artifacts;
keep ``asteria-agentic-v1/evaluator/`` and every answer key away from this
process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from importlib import import_module
from pathlib import Path, PureWindowsPath
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from synthworld.agentic import trace_submission_from_jsonl
from synthworld.evaluation import ExtractionPredictionSet

ADAPTER_VERSION = "2.2.0"
DEFAULT_MODEL = "claude-opus-5"
MAX_OUTPUT_TOKENS = 16000
FALLBACK_BETAS = ("server-side-fallback-2026-07-01",)

EXTRACTION_DATA_CLASSES = (
    "email",
    "username",
    "phone",
    "address",
    "date_of_birth",
    "employer",
    "education",
    "national_id",
)

EXTRACTION_INSTRUCTIONS = """\
You are a PII extraction system under evaluation. Each user message is the
full text of one synthetic public page. Find every occurrence of a personal
data value belonging to one of these classes: email, username, phone,
address, date_of_birth, employer, education, national_id.

Report each value as its data class plus the exact verbatim substring as it
appears in the page: character for character, keeping punctuation that is
part of the value, and excluding surrounding labels, prefixes, and
whitespace. Report a value even when it is obviously synthetic. Do not
report values for any other class, and do not report a class label whose
value is absent from the page.
"""

AGENTIC_INSTRUCTIONS = """\
You are the system under test for the SynthWorld Asteria Agentic v1
benchmark: an agent-identity, delegated-authority, and audit-provenance
observability system. Your context contains the complete public package of
one frozen world. Each user message names one action_attempted event; emit
exactly one observation for that event as JSON.

Replay semantics:
- Event indices are contiguous and one-based. Grants, credential issues,
  runtime spawns, revocations, and evidence discards become effective at
  their own index.
- The action-time decision evaluates the attempt against the world state
  immediately before the action's own event index.
- The audit-time decision re-evaluates the same attempt against the state at
  the final audit event, so later revocations or later grants change it.
- Policy is default-deny and requires an active delegation: the action needs
  an unrevoked delegation chain, valid at the action's timestamp, granted to
  the logical agent that acted, whose capability covers the resource, the
  action, every requested scope, and the purpose.
- The presented credential must be valid at the time, its subject principal
  must be the runtime principal that executed the action, and the runtime
  must belong to the acting logical agent and to the same tenant as the
  resource.
- A proposed delegation must not exceed its parent capability.

Trace conventions (these exact rules are graded):
- delegation_chain_ids records the chain the action-time policy check
  selects. Among the delegations granted to the acting logical agent by the
  originating principal that are time-valid, unrevoked, and match the
  attempt's policy version, keep those whose capability covers the resource,
  the action, every requested scope, and the purpose; take the qualifying
  delegation with the lexicographically smallest ID and expand it through
  its parents, root first. The chain is independent of the final decision:
  an action denied for a credential, runtime, tenant, or sub-delegation
  reason still records its covering chain, while an action whose covering
  delegation is revoked, expired, or not yet granted records an empty chain.
- evidence_refs is the sorted union of exactly four groups: the policy
  (evidence:policy:<version>), the presented credential
  (evidence:credential:<id>), the canonical runtime mapped from the claimed
  runtime principal (evidence:runtime:<runtime id>), and one
  evidence:delegation:<id> entry per member of delegation_chain_ids. Denied
  actions require no delegation references beyond the recorded chain and
  never require revocation references; the runtime reference follows that
  canonical mapping rather than any runtime reference the attempt happened
  to cite.
- reconstructable_from_retained_evidence states whether that required set is
  still retained at the audit event, given every evidence_discarded event.
- side_effect is "none" whenever the action-time decision is deny. For
  allowed actions it is derived from the action: read becomes read_recorded,
  request_quotation becomes quotation_requested, compare becomes
  comparison_recorded, create_draft becomes draft_created,
  create_delegation becomes delegation_created, and any other action becomes
  action_recorded.

Field guidance for the observation:
- event_id: the action event id; timestamp: the event's occurred_at.
- originating_principal_id, logical_agent_id, runtime_principal_id: the
  identities behind the action as recorded for this attempt.
- credential_subject_id: the subject principal of the presented credential.
- attributed_actor_id: keep the recorded actor claim when it lies on the
  action's identity paths — the service account owning the executing runtime
  or the one owning the presented credential's subject runtime principal.
  When the claim lies on neither path, report the principal those paths
  identify; if they identify different principals and the public data cannot
  select one, report null.
- resource_id, action, requested_scope, policy_version: from the attempt.
- decision and decision_at_audit: "allow" or "deny" per the replay
  semantics above.
- Use null only for values that genuinely cannot be determined.
"""

_STRING: dict[str, object] = {"type": "string"}
_NULLABLE_STRING: dict[str, object] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_NULLABLE_STRINGS: dict[str, object] = {
    "anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]
}
_NULLABLE_DECISION: dict[str, object] = {
    "anyOf": [{"type": "string", "enum": ["allow", "deny"]}, {"type": "null"}]
}
_NULLABLE_BOOL: dict[str, object] = {"anyOf": [{"type": "boolean"}, {"type": "null"}]}

AGENTIC_TRACE_FIELDS: dict[str, dict[str, object]] = {
    "event_id": _STRING,
    "timestamp": _NULLABLE_STRING,
    "originating_principal_id": _NULLABLE_STRING,
    "logical_agent_id": _NULLABLE_STRING,
    "runtime_principal_id": _NULLABLE_STRING,
    "credential_subject_id": _NULLABLE_STRING,
    "attributed_actor_id": _NULLABLE_STRING,
    "resource_id": _NULLABLE_STRING,
    "action": _NULLABLE_STRING,
    "requested_scope": _NULLABLE_STRINGS,
    "decision": _NULLABLE_DECISION,
    "decision_at_audit": _NULLABLE_DECISION,
    "side_effect": _NULLABLE_STRING,
    "policy_version": _NULLABLE_STRING,
    "delegation_chain_ids": _NULLABLE_STRINGS,
    "accountable_owner_chain": _NULLABLE_STRINGS,
    "evidence_refs": _NULLABLE_STRINGS,
    "reconstructable_from_retained_evidence": _NULLABLE_BOOL,
}

AGENTIC_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": list(AGENTIC_TRACE_FIELDS),
    "properties": AGENTIC_TRACE_FIELDS,
}

EXTRACTION_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["data_class", "text"],
                "properties": {
                    "data_class": {
                        "type": "string",
                        "enum": list(EXTRACTION_DATA_CLASSES),
                    },
                    "text": {"type": "string"},
                },
            },
        }
    },
}

_Decision = Literal["allow", "deny"]
_ExtractionDataClass = Literal[
    "email",
    "username",
    "phone",
    "address",
    "date_of_birth",
    "employer",
    "education",
    "national_id",
]


class AgenticOutput(BaseModel):
    """The agentic response contract; mirrors ``AGENTIC_RESPONSE_SCHEMA``."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    timestamp: str | None
    originating_principal_id: str | None
    logical_agent_id: str | None
    runtime_principal_id: str | None
    credential_subject_id: str | None
    attributed_actor_id: str | None
    resource_id: str | None
    action: str | None
    requested_scope: list[str] | None
    decision: _Decision | None
    decision_at_audit: _Decision | None
    side_effect: str | None
    policy_version: str | None
    delegation_chain_ids: list[str] | None
    accountable_owner_chain: list[str] | None
    evidence_refs: list[str] | None
    reconstructable_from_retained_evidence: bool | None


class ExtractionFinding(BaseModel):
    """One value the model reports for a page."""

    model_config = ConfigDict(extra="forbid")

    data_class: _ExtractionDataClass
    text: str


class ExtractionOutput(BaseModel):
    """The extraction response contract; mirrors its JSON schema."""

    model_config = ConfigDict(extra="forbid")

    findings: list[ExtractionFinding]


class ResponseMeta(BaseModel):
    """Provenance recorded for one model response."""

    model_config = ConfigDict(extra="forbid")

    requested_model: str
    served_model: str | None
    stop_reason: str | None
    fallbacks_enabled: bool
    fallback_ran: bool
    response_id: str | None = None
    sdk_version: str


class ResponseEnvelope(BaseModel):
    """One cached model response bound to the inputs that produced it."""

    model_config = ConfigDict(extra="forbid")

    unit_id: str
    fingerprint: str
    meta: ResponseMeta
    output: dict[str, object]


class JsonCompleter(Protocol):
    """One schema-constrained completion per benchmark unit."""

    def complete(
        self,
        unit_id: str,
        instructions: str,
        context: str | None,
        user_text: str,
        schema: dict[str, object],
    ) -> dict[str, object]:
        """Return ``{"output": <schema-conforming dict>, "meta": {...}}``."""
        ...


class ClaudeJsonCompleter:
    """Lazily-connected Claude client that returns schema-constrained JSON."""

    def __init__(self, model: str, *, use_fallbacks: bool = False) -> None:
        self._model = model
        self._use_fallbacks = use_fallbacks
        self._client: Any = None
        self._sdk_version = "unknown"

    def complete(
        self,
        unit_id: str,
        instructions: str,
        context: str | None,
        user_text: str,
        schema: dict[str, object],
    ) -> dict[str, object]:
        if self._client is None:
            self._client = cast(Any, self._connect())
        system: list[dict[str, object]] = [{"type": "text", "text": instructions}]
        if context is not None:
            system.append(
                {
                    "type": "text",
                    "text": context,
                    "cache_control": {"type": "ephemeral"},
                }
            )
        request: dict[str, object] = {
            "model": self._model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user_text}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        if self._use_fallbacks:
            response = self._client.beta.messages.create(
                betas=list(FALLBACK_BETAS),
                fallbacks="default",
                **request,
            )
        else:
            response = self._client.messages.create(**request)
        if response.stop_reason == "refusal":
            raise RuntimeError(
                f"the model declined unit {unit_id}; no observation was produced"
            )
        iterations = getattr(response.usage, "iterations", None) or []
        fallback_ran = any(
            getattr(entry, "type", None) == "fallback_message" for entry in iterations
        )
        text = next(block.text for block in response.content if block.type == "text")
        return {
            "output": json.loads(text),
            "meta": {
                "requested_model": self._model,
                "served_model": response.model,
                "stop_reason": response.stop_reason,
                "fallbacks_enabled": self._use_fallbacks,
                "fallback_ran": fallback_ran,
                "response_id": getattr(response, "id", None),
                "sdk_version": self._sdk_version,
            },
        }

    def _connect(self) -> object:
        try:
            anthropic = import_module("anthropic")
        except ModuleNotFoundError as error:
            raise SystemExit(
                "uncached model calls need the Anthropic SDK; run this script "
                "with `uv run --with anthropic`"
            ) from error
        self._sdk_version = str(getattr(anthropic, "__version__", "unknown"))
        return anthropic.Anthropic()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _artifact_set_digest(artifacts: dict[str, bytes]) -> str:
    """Digest a named set, binding both every relative path and its bytes."""

    digest = hashlib.sha256()
    for path, content in sorted(artifacts.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def _generation_config(fallbacks_enabled: bool) -> dict[str, object]:
    return {
        "fallbacks": "default" if fallbacks_enabled else None,
        "betas": list(FALLBACK_BETAS) if fallbacks_enabled else [],
        "max_output_tokens": MAX_OUTPUT_TOKENS,
    }


def _fingerprint(
    model: str,
    fallbacks_enabled: bool,
    instructions: str,
    context: str | None,
    user_text: str,
    schema: dict[str, object],
) -> str:
    return _sha256_text(
        _canonical_json(
            {
                "adapter_version": ADAPTER_VERSION,
                "model": model,
                "generation": _generation_config(fallbacks_enabled),
                "instructions": instructions,
                "context": context,
                "user_text": user_text,
                "schema": schema,
            }
        )
    )


def _cache_file_name(unit_id: str) -> str:
    """A stable cache filename that never uses the unit ID as a path."""

    return _sha256_text(unit_id) + ".json"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(path.name + ".tmp")
    staged.write_text(text, encoding="utf-8")
    os.replace(staged, path)


def _validated_output(
    value: dict[str, object], output_model: type[BaseModel], describe: str
) -> None:
    try:
        output_model.model_validate(value)
    except ValidationError as error:
        raise SystemExit(f"{describe}: {error}") from error


def _load_cached(
    responses_dir: Path,
    unit_id: str,
    fingerprint: str,
    model: str,
    fallbacks_enabled: bool,
    output_model: type[BaseModel],
) -> ResponseEnvelope | None:
    path = responses_dir / _cache_file_name(unit_id)
    if not path.exists():
        return None
    try:
        envelope = ResponseEnvelope.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError as error:
        raise SystemExit(f"invalid response envelope at {path}: {error}") from error
    if envelope.unit_id != unit_id:
        raise SystemExit(
            f"cached response {path} does not belong to unit {unit_id}; move "
            "or delete the responses directory to call the model again"
        )
    if envelope.fingerprint != fingerprint:
        raise SystemExit(
            f"cached response {path} was produced with different adapter "
            "inputs (adapter version, model, generation configuration, "
            "instructions, schema, or benchmark input); move or delete the "
            "responses directory to call the model again"
        )
    if (
        envelope.meta.requested_model != model
        or envelope.meta.fallbacks_enabled != fallbacks_enabled
    ):
        raise SystemExit(
            f"cached response {path} carries provenance metadata that does "
            "not match this run's requested model or fallback configuration; "
            "move or delete the responses directory to call the model again"
        )
    _validated_output(
        envelope.output,
        output_model,
        f"cached response {path} output does not conform to the task schema",
    )
    return envelope


def _resolve_unit(
    completer: JsonCompleter,
    responses_dir: Path,
    unit_id: str,
    model: str,
    fallbacks_enabled: bool,
    instructions: str,
    context: str | None,
    user_text: str,
    schema: dict[str, object],
    output_model: type[BaseModel],
) -> ResponseEnvelope:
    fingerprint = _fingerprint(
        model, fallbacks_enabled, instructions, context, user_text, schema
    )
    envelope = _load_cached(
        responses_dir, unit_id, fingerprint, model, fallbacks_enabled, output_model
    )
    if envelope is None:
        completion = completer.complete(
            unit_id, instructions, context, user_text, schema
        )
        _validated_output(
            cast(dict[str, object], completion["output"]),
            output_model,
            f"completer returned an invalid response for {unit_id}",
        )
        try:
            envelope = ResponseEnvelope.model_validate(
                {
                    "unit_id": unit_id,
                    "fingerprint": fingerprint,
                    "meta": completion["meta"],
                    "output": completion["output"],
                }
            )
        except ValidationError as error:
            raise SystemExit(
                f"completer returned an invalid response for {unit_id}: {error}"
            ) from error
        _atomic_write_text(
            responses_dir / _cache_file_name(unit_id),
            envelope.model_dump_json(indent=2) + "\n",
        )
    return envelope


def _write_run_manifest(
    responses_dir: Path,
    *,
    task: str,
    model: str,
    fallbacks_enabled: bool,
    instructions: str,
    schema: dict[str, object],
    input_digest: str,
    benchmark_digest: str | None,
    unit_ids: list[str],
    envelopes: list[ResponseEnvelope],
    output_path: Path,
) -> None:
    envelope_bytes = {
        _cache_file_name(unit_id): (
            responses_dir / _cache_file_name(unit_id)
        ).read_bytes()
        for unit_id in unit_ids
    }
    stop_reasons: dict[str, int] = {}
    for envelope in envelopes:
        key = str(envelope.meta.stop_reason)
        stop_reasons[key] = stop_reasons.get(key, 0) + 1
    manifest = {
        "adapter_version": ADAPTER_VERSION,
        "task": task,
        "requested_model": model,
        "fallbacks_enabled": fallbacks_enabled,
        "generation": _generation_config(fallbacks_enabled),
        "instructions_sha256": _sha256_text(instructions),
        "schema_sha256": _sha256_text(_canonical_json(schema)),
        "input_sha256": input_digest,
        "benchmark_artifact_set_digest": benchmark_digest,
        "unit_cache_files": {
            unit_id: _cache_file_name(unit_id) for unit_id in unit_ids
        },
        "unit_fingerprints": {
            unit_id: envelope.fingerprint
            for unit_id, envelope in zip(unit_ids, envelopes, strict=True)
        },
        "response_artifact_set_digest": _artifact_set_digest(envelope_bytes),
        "output_sha256": _sha256_bytes(output_path.read_bytes()),
        "served_models": sorted(
            {str(envelope.meta.served_model) for envelope in envelopes}
        ),
        "sdk_versions": sorted({envelope.meta.sdk_version for envelope in envelopes}),
        "stop_reasons": stop_reasons,
        "fallback_ran": any(envelope.meta.fallback_ran for envelope in envelopes),
        "units": len(envelopes),
    }
    _atomic_write_text(
        responses_dir / "run-manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )


def _validated_artifact_name(name: str) -> str:
    """Require a normalized, relative, forward-slash artifact name."""

    parts = name.split("/")
    if (
        "\\" in name
        or name.startswith("/")
        or PureWindowsPath(name).drive
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise SystemExit(
            f"public manifest lists an unsafe artifact name: {name!r}; "
            "artifact names must be normalized relative paths"
        )
    return name


def _verified_artifact_bytes(public_dir: Path, name: str, expected: str) -> bytes:
    root = public_dir.resolve(strict=True)
    path = public_dir / name
    if path.is_symlink() or not path.is_file():
        raise SystemExit(
            f"public artifact {name} is missing from {public_dir} or is a "
            "symlink; refusing to use this package"
        )
    if path.resolve(strict=True) != root / name:
        raise SystemExit(
            f"public artifact {name} escapes the public directory or crosses "
            "a symlink; refusing to use this package"
        )
    data = path.read_bytes()
    if _sha256_bytes(data) != expected:
        raise SystemExit(
            f"public artifact {name} does not match its manifest SHA-256; "
            "refusing to use a modified package"
        )
    return data


def _load_public_package(public_dir: Path) -> tuple[str, str, dict[str, bytes]]:
    """Verify the public manifest boundary and build the model context.

    Returns the context text, the manifest's artifact-set digest, and the
    verified artifact bytes. Refuses to proceed when the manifest is absent,
    the package is not declared oracle-free, an artifact name is unsafe, a
    listed artifact is missing, modified, a symlink, or outside the public
    directory, the artifact-set digest does not match, or unlisted files are
    present.
    """

    manifest_path = public_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(
            f"{public_dir} has no manifest.json; pass the public/ directory "
            "produced by `synthworld generate-agentic`, not the benchmark root"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("oracle_free") is not True:
        raise SystemExit(
            f"{manifest_path} does not declare oracle_free: true; refusing to "
            "send this package to a model"
        )
    listed = cast(dict[str, str], manifest["artifacts"])
    artifact_bytes: dict[str, bytes] = {}
    for name, expected_sha256 in sorted(listed.items()):
        _validated_artifact_name(name)
        artifact_bytes[name] = _verified_artifact_bytes(
            public_dir, name, expected_sha256
        )
    digest = _artifact_set_digest(artifact_bytes)
    if digest != manifest["artifact_set_digest"]:
        raise SystemExit(
            f"{public_dir} does not match its manifest artifact-set digest; "
            "refusing to use a modified package"
        )
    unlisted = sorted(
        path.relative_to(public_dir).as_posix()
        for path in public_dir.rglob("*")
        if path.is_file()
        and path.name != "manifest.json"
        and path.relative_to(public_dir).as_posix() not in listed
    )
    if unlisted:
        raise SystemExit(
            f"{public_dir} contains files not listed in the public manifest: "
            f"{', '.join(unlisted)}; refusing to send unverified content to "
            "a model"
        )
    sections = [
        f"## {name}\n" + artifact_bytes[name].decode("utf-8").rstrip("\n")
        for name in sorted(artifact_bytes)
    ]
    context = "# Asteria Agentic v1 public package\n\n" + "\n\n".join(sections) + "\n"
    return context, str(manifest["artifact_set_digest"]), artifact_bytes


def _scenario_action_event_ids(artifact_bytes: dict[str, bytes]) -> list[str]:
    """Read the action list from already-verified scenario artifact bytes."""

    event_ids: list[str] = []
    for name in sorted(artifact_bytes):
        if not (name.startswith("scenarios/") and name.endswith(".json")):
            continue
        scenario = json.loads(artifact_bytes[name].decode("utf-8"))
        event_ids.extend(scenario["action_event_ids"])
    if not event_ids:
        raise SystemExit("no scenario action events found in the public package")
    return event_ids


def run_agentic(
    args: argparse.Namespace, completer: JsonCompleter | None = None
) -> None:
    public_dir: Path = args.public_dir
    responses_dir: Path = args.responses_dir
    if completer is None:
        completer = ClaudeJsonCompleter(args.model, use_fallbacks=args.fallbacks)
    context, benchmark_digest, artifact_bytes = _load_public_package(public_dir)
    unit_ids = _scenario_action_event_ids(artifact_bytes)
    envelopes: list[ResponseEnvelope] = []
    rows: list[dict[str, object]] = []
    for event_id in unit_ids:
        envelope = _resolve_unit(
            completer,
            responses_dir,
            event_id,
            args.model,
            args.fallbacks,
            AGENTIC_INSTRUCTIONS,
            context,
            f"Emit the observation JSON object for action event {event_id}.",
            AGENTIC_RESPONSE_SCHEMA,
            AgenticOutput,
        )
        envelopes.append(envelope)
        row = {name: envelope.output.get(name) for name in AGENTIC_TRACE_FIELDS}
        row["event_id"] = event_id
        rows.append(row)
    serialized = "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
    trace_submission_from_jsonl(serialized)
    _atomic_write_text(args.output, serialized + "\n")
    _write_run_manifest(
        responses_dir,
        task="agentic",
        model=args.model,
        fallbacks_enabled=args.fallbacks,
        instructions=AGENTIC_INSTRUCTIONS,
        schema=AGENTIC_RESPONSE_SCHEMA,
        input_digest=_sha256_text(context),
        benchmark_digest=benchmark_digest,
        unit_ids=unit_ids,
        envelopes=envelopes,
        output_path=args.output,
    )
    print(f"Wrote {len(rows)} observed actions to {args.output}")


def _finding_spans(
    content: str, findings: list[dict[str, object]]
) -> list[dict[str, object]]:
    located: set[tuple[str, int, int]] = set()
    for finding in findings:
        data_class = str(finding["data_class"])
        text = str(finding["text"])
        if not text:
            continue
        start = content.find(text)
        while start != -1:
            located.add((data_class, start, start + len(text)))
            start = content.find(text, start + 1)
    return [
        {"data_class": data_class, "start": start, "end": end}
        for data_class, start, end in sorted(
            located, key=lambda span: (span[1], span[2], span[0])
        )
    ]


def run_extraction(
    args: argparse.Namespace, completer: JsonCompleter | None = None
) -> None:
    responses_dir: Path = args.responses_dir
    if completer is None:
        completer = ClaudeJsonCompleter(args.model, use_fallbacks=args.fallbacks)
    corpus_text = args.corpus.read_text(encoding="utf-8")
    corpus = json.loads(corpus_text)
    unit_ids: list[str] = []
    envelopes: list[ResponseEnvelope] = []
    predictions: list[dict[str, object]] = []
    for page in corpus["pages"]:
        unit_id = f"{page['source_type']}--{page['source_record_id']}"
        unit_ids.append(unit_id)
        envelope = _resolve_unit(
            completer,
            responses_dir,
            unit_id,
            args.model,
            args.fallbacks,
            EXTRACTION_INSTRUCTIONS,
            None,
            page["content"],
            EXTRACTION_RESPONSE_SCHEMA,
            ExtractionOutput,
        )
        envelopes.append(envelope)
        findings = cast(list[dict[str, object]], envelope.output["findings"])
        predictions.append(
            {
                "source_type": page["source_type"],
                "source_record_id": page["source_record_id"],
                "spans": _finding_spans(page["content"], findings),
            }
        )
    prediction_set = {"schema_version": "0.1.0", "predictions": predictions}
    ExtractionPredictionSet.model_validate(prediction_set)
    _atomic_write_text(args.output, json.dumps(prediction_set, indent=2) + "\n")
    _write_run_manifest(
        responses_dir,
        task="extraction",
        model=args.model,
        fallbacks_enabled=args.fallbacks,
        instructions=EXTRACTION_INSTRUCTIONS,
        schema=EXTRACTION_RESPONSE_SCHEMA,
        input_digest=_sha256_text(corpus_text),
        benchmark_digest=None,
        unit_ids=unit_ids,
        envelopes=envelopes,
        output_path=args.output,
    )
    span_count = sum(len(cast(list[object], page["spans"])) for page in predictions)
    print(
        f"Wrote {span_count} predicted spans over {len(predictions)} pages "
        f"to {args.output}"
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="task", required=True)

    agentic = subparsers.add_parser(
        "agentic", help="judge Asteria Agentic v1 public action events"
    )
    agentic.add_argument(
        "--public-dir",
        type=Path,
        required=True,
        help="asteria-agentic-v1/public directory from generate-agentic",
    )
    agentic.add_argument("--output", type=Path, required=True)

    extraction = subparsers.add_parser(
        "extraction", help="extract PII spans from the public extraction corpus"
    )
    extraction.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="public corpus JSON from generate-public-extraction",
    )
    extraction.add_argument("--output", type=Path, required=True)

    for subparser in (agentic, extraction):
        subparser.add_argument("--model", default=DEFAULT_MODEL)
        subparser.add_argument(
            "--fallbacks",
            action="store_true",
            help="enable server-side refusal fallbacks; the served model per "
            "response is recorded in the cache envelopes",
        )
        subparser.add_argument(
            "--responses-dir",
            type=Path,
            default=None,
            help="cache directory for raw model responses "
            "(default: <output>.responses)",
        )

    args = parser.parse_args(argv)
    if args.responses_dir is None:
        args.responses_dir = args.output.with_name(args.output.name + ".responses")
    return args


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.task == "agentic":
        run_agentic(args)
    else:
        run_extraction(args)


if __name__ == "__main__":
    main()
