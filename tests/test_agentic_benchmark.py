from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from importlib.resources import files
from itertools import pairwise
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.agentic import (
    generate_asteria_agentic_v1,
    load_golden_agentic_benchmark,
    materialize_agentic_world,
)
from synthworld.agentic.models import (
    ActionAttempted,
    AgenticCase,
    AgenticCaseKind,
    AgenticEvent,
    AuditPerformed,
    AuthorityFailureReason,
    CredentialIssued,
    Decision,
    DelegationGranted,
    RuntimeSpawned,
)
from synthworld.agentic.replay import AgenticReplayError
from synthworld.agentic.serialization import (
    AgenticArtifactError,
    agentic_evaluator_artifacts,
    agentic_public_artifacts,
    artifact_set_digest,
    export_agentic_benchmark,
    load_agentic_benchmark,
)


def test_frozen_agentic_artifacts_match_generation_byte_for_byte() -> None:
    benchmark = generate_asteria_agentic_v1()
    assert load_golden_agentic_benchmark() == benchmark

    root = files("synthworld.benchmarks").joinpath("asteria-agentic-v1")
    for package, artifacts in (
        ("public", agentic_public_artifacts(benchmark.public)),
        ("evaluator", agentic_evaluator_artifacts(benchmark)),
    ):
        for relative_path, content in artifacts.items():
            assert root.joinpath(package, relative_path).read_bytes() == content


def test_public_agentic_package_is_oracle_free_and_self_describing() -> None:
    benchmark = generate_asteria_agentic_v1()
    artifacts = agentic_public_artifacts(benchmark.public)
    joined = b"".join(artifacts.values()).lower()
    forbidden = (
        b"authority_truth",
        b"canonical_binding",
        b"decision_at_action",
        b"expected_side_effect",
        b"failure_reasons",
        b"reconstructable_at_audit",
    )
    assert all(term not in joined for term in forbidden)
    manifest = json.loads(artifacts["manifest.json"])
    base = {
        path: content for path, content in artifacts.items() if path != "manifest.json"
    }
    assert manifest["oracle_free"] is True
    assert manifest["artifact_set_digest"] == artifact_set_digest(base)
    assert manifest["artifact_set_digest"] == (
        "9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594"
    )
    checksums = json.loads(agentic_evaluator_artifacts(benchmark)["checksums.json"])
    assert "public_artifacts" not in checksums
    assert checksums["public_artifact_set_digest"] == manifest["artifact_set_digest"]
    assert checksums["evaluator_artifact_set_digest"] == (
        "3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f"
    )
    assert b"password" not in joined
    assert b"private_key" not in joined
    assert b"client_secret" not in joined
    assert b"@" not in joined
    assert len(benchmark.public.snapshot.departments) == 4
    assert len(benchmark.public.snapshot.resources) == 9
    assert len(benchmark.public.events) == 24


def test_procurement_cases_have_reviewed_action_and_audit_outcomes() -> None:
    benchmark = generate_asteria_agentic_v1()
    truth = {
        case.kind: next(
            item
            for item in benchmark.evaluator.authority_truth
            if item.action_event_id == case.action_event_id
        )
        for case in benchmark.evaluator.cases
    }
    # Asteria exercises every kind but the two that exist for generated worlds. Naming
    # them keeps this a guard rather than a tautology: a kind added with no case must be
    # declared unexercised here, which is the moment to ask why it has no case.
    unexercised = {
        AgenticCaseKind.CREDENTIAL_INVALID,
        AgenticCaseKind.POLICY_VERSION_MISMATCH,
    }
    assert set(truth) == set(AgenticCaseKind) - unexercised
    assert truth[AgenticCaseKind.AUTHORISED_ACTION].decision_at_action is Decision.ALLOW
    assert (
        truth[AgenticCaseKind.VALID_THEN_REVOKED].decision_at_action is Decision.ALLOW
    )
    assert truth[AgenticCaseKind.VALID_THEN_REVOKED].decision_at_audit is Decision.DENY
    assert (
        truth[AgenticCaseKind.INVALID_THEN_LATER_GRANTED].decision_at_action
        is Decision.DENY
    )
    assert (
        truth[AgenticCaseKind.INVALID_THEN_LATER_GRANTED].decision_at_audit
        is Decision.ALLOW
    )
    assert (
        AuthorityFailureReason.WRONG_RUNTIME
        in truth[AgenticCaseKind.WRONG_RUNTIME].failure_reasons_at_action
    )
    assert (
        AuthorityFailureReason.OVERPRIVILEGED_SUBDELEGATION
        in truth[AgenticCaseKind.OVERPRIVILEGED_SUBDELEGATION].failure_reasons_at_action
    )
    assert truth[
        AgenticCaseKind.OVERPRIVILEGED_SUBDELEGATION
    ].failure_reasons_at_audit == (AuthorityFailureReason.DELEGATION_REVOKED,)
    assert truth[AgenticCaseKind.POST_REVOCATION_ACTION].failure_reasons_at_action == (
        AuthorityFailureReason.DELEGATION_REVOKED,
    )
    assert (
        truth[AgenticCaseKind.MISSING_RETAINED_EVIDENCE].reconstructable_at_audit
        is False
    )


def test_normalized_records_resolve_the_full_authority_provenance_join() -> None:
    benchmark = generate_asteria_agentic_v1()
    snapshot = benchmark.public.snapshot
    principals = {item.id for item in snapshot.principals}
    agents = {item.id for item in snapshot.agents}
    resources = {item.id: item for item in snapshot.resources}
    runtimes = {
        event.payload.runtime.id: event.payload.runtime
        for event in benchmark.public.events
        if isinstance(event.payload, RuntimeSpawned)
    }
    credentials = {
        event.payload.credential.id: event.payload.credential
        for event in benchmark.public.events
        if isinstance(event.payload, CredentialIssued)
    }
    delegations = {
        event.payload.delegation.id: event.payload.delegation
        for event in benchmark.public.events
        if isinstance(event.payload, DelegationGranted)
    }
    events = {event.id: event for event in benchmark.public.events}

    for binding, truth in zip(
        benchmark.evaluator.bindings,
        benchmark.evaluator.authority_truth,
        strict=True,
    ):
        event = events[binding.action_event_id]
        assert isinstance(event.payload, ActionAttempted)
        attempt = event.payload.attempt
        runtime = runtimes[binding.runtime_id]
        credential = credentials[attempt.presented_credential_id]
        chain = tuple(delegations[item] for item in truth.delegation_chain_ids)

        assert binding.originating_principal_id in principals
        assert binding.logical_agent_id in agents
        assert runtime.runtime_principal_id == binding.runtime_principal_id
        assert credential.subject_principal_id == binding.credential_subject_id
        assert credential.issuer_principal_id in principals
        assert all(item.delegator_principal_id in principals for item in chain)
        assert all(item.grantee_agent_id in agents for item in chain)
        assert tuple(item.parent_delegation_id for item in chain[1:]) == tuple(
            item.id for item in chain[:-1]
        )
        assert truth.expected_policy_version == attempt.policy_version
        assert attempt.action in resources[attempt.resource_id].actions
        assert set(truth.required_evidence_refs) == {
            f"evidence:policy:{attempt.policy_version}",
            f"evidence:credential:{credential.id}",
            f"evidence:runtime:{runtime.id}",
            *(f"evidence:delegation:{item.id}" for item in chain),
        }


def test_replay_uses_one_based_indices_and_action_pre_state() -> None:
    benchmark = generate_asteria_agentic_v1()
    snapshot = benchmark.public.snapshot
    events = benchmark.public.events
    initial = materialize_agentic_world(snapshot, events, at_event_index=0)
    first = materialize_agentic_world(snapshot, events, at_event_index=1)
    through_time = materialize_agentic_world(
        snapshot, events, at_timestamp=events[8].occurred_at
    )
    full = materialize_agentic_world(snapshot, events)

    assert initial.as_of is None
    assert not initial.delegations
    assert len(first.delegations) == 1
    assert through_time.through_event_index == 9
    assert full.through_event_index == 24
    assert full.action_event_ids == benchmark.public.scenario.action_event_ids
    assert full.audit_event_ids == (benchmark.public.scenario.audit_event_id,)
    assert "delegation-comparison-child-001" in full.revoked_delegation_ids


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        (
            {
                "at_event_index": 1,
                "at_timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            },
            "either",
        ),
        ({"at_event_index": -1}, "negative"),
        ({"at_event_index": 25}, "outside"),
        ({"at_timestamp": datetime(2026, 1, 1)}, "UTC"),
    ),
)
def test_replay_rejects_invalid_cursors(
    kwargs: dict[str, object], message: str
) -> None:
    benchmark = generate_asteria_agentic_v1()
    with pytest.raises(AgenticReplayError, match=message):
        materialize_agentic_world(
            benchmark.public.snapshot,
            benchmark.public.events,
            **kwargs,  # type: ignore[arg-type]
        )


def test_replay_rejects_noncontiguous_duplicate_and_time_reversed_events() -> None:
    benchmark = generate_asteria_agentic_v1()
    events = benchmark.public.events
    bad_index = (events[0].model_copy(update={"event_index": 2}), *events[1:])
    duplicate = (
        events[0],
        events[1].model_copy(update={"id": events[0].id}),
        *events[2:],
    )
    reversed_time = (
        events[0],
        events[1].model_copy(update={"occurred_at": events[0].occurred_at}),
        *events[2:],
    )
    for altered, message in (
        (bad_index, "contiguous"),
        (duplicate, "unique"),
        (reversed_time, "strictly increasing"),
    ):
        with pytest.raises(AgenticReplayError, match=message):
            materialize_agentic_world(benchmark.public.snapshot, altered)


def test_agentic_models_reject_non_utc_and_invalid_audit_event() -> None:
    benchmark = generate_asteria_agentic_v1()
    event = benchmark.public.events[0]
    with pytest.raises(ValidationError, match="UTC"):
        AgenticEvent.model_validate(
            {**event.model_dump(), "occurred_at": datetime(2026, 1, 1)}
        )
    audit = benchmark.public.events[-1]
    assert isinstance(audit.payload, AuditPerformed)
    with pytest.raises(AgenticReplayError, match="must be an audit"):
        from synthworld.agentic.projection import build_agentic_benchmark

        build_agentic_benchmark(
            benchmark.public.snapshot,
            benchmark.public.events,
            benchmark.public.scenario.model_copy(
                update={"audit_event_id": benchmark.public.events[0].id}
            ),
            benchmark.evaluator.bindings,
            benchmark.evaluator.cases,
        )

    with pytest.raises(AgenticReplayError, match="bindings must cover"):
        build_agentic_benchmark(
            benchmark.public.snapshot,
            benchmark.public.events,
            benchmark.public.scenario,
            benchmark.evaluator.bindings[:-1],
            benchmark.evaluator.cases,
        )


def test_exported_artifacts_are_checksum_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synthworld.agentic import serialization

    benchmark = generate_asteria_agentic_v1()
    root = tmp_path / "asteria-agentic-v1"
    export_agentic_benchmark(root, benchmark)
    monkeypatch.setattr(serialization, "files", lambda _package: tmp_path)
    assert serialization.load_golden_agentic_benchmark() == benchmark

    events = root / "public/public_events.jsonl"
    events.write_bytes(events.read_bytes() + b"\n")
    with pytest.raises(AgenticArtifactError, match="checksum"):
        serialization.load_golden_agentic_benchmark()


def test_complete_loader_reads_explicit_separate_export_roots(tmp_path: Path) -> None:
    benchmark = generate_asteria_agentic_v1()
    root = tmp_path / "asteria-agentic-v1"
    export_agentic_benchmark(root, benchmark)

    assert (
        load_agentic_benchmark(
            public_root=root / "public",
            evaluator_root=root / "evaluator",
        )
        == benchmark
    )


def test_frozen_loader_rejects_incomplete_evaluator_and_nonobject_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synthworld.agentic import serialization

    benchmark = generate_asteria_agentic_v1()
    monkeypatch.setattr(serialization, "files", lambda _package: tmp_path)

    root = tmp_path / "asteria-agentic-v1"
    export_agentic_benchmark(root, benchmark)
    manifest_path = root / "public/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].pop("agents.jsonl")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AgenticArtifactError, match="incomplete"):
        serialization.load_golden_agentic_benchmark()

    export_agentic_benchmark(root, benchmark)
    evaluator = root / "evaluator/authority_truth.jsonl"
    evaluator.write_bytes(evaluator.read_bytes() + b"\n")
    with pytest.raises(AgenticArtifactError, match="evaluator checksum"):
        serialization.load_golden_agentic_benchmark()

    export_agentic_benchmark(root, benchmark)
    manifest_path.write_text("[]", encoding="utf-8")
    with pytest.raises(AgenticArtifactError, match="must be an object"):
        serialization.load_golden_agentic_benchmark()

    blank_jsonl = tmp_path / "blank.jsonl"
    blank_jsonl.write_text(
        (
            '{"action_event_id":"evt-one","kind":"authorised_action"}\n\n'
            '{"action_event_id":"evt-two","kind":"outside_capability"}\n'
        ),
        encoding="utf-8",
    )
    rows = serialization._read_jsonl(blank_jsonl, AgenticCase)
    assert len(rows) == 2


def test_generator_events_are_strict_and_public_claims_can_diverge() -> None:
    benchmark = generate_asteria_agentic_v1()
    events = benchmark.public.events
    assert all(
        current.occurred_at > previous.occurred_at
        for previous, current in pairwise(events)
    )
    grants = [event for event in events if isinstance(event.payload, DelegationGranted)]
    actions = [event for event in events if isinstance(event.payload, ActionAttempted)]
    assert len(grants) == 4
    assert len(actions) == 11
    attribution = next(
        event for event in actions if event.id == "evt-016-incorrect-attribution"
    )
    binding = next(
        item
        for item in benchmark.evaluator.bindings
        if item.action_event_id == attribution.id
    )
    assert isinstance(attribution.payload, ActionAttempted)
    assert (
        attribution.payload.attempt.attributed_actor_claim
        != binding.attributed_actor_id
    )


def test_load_public_agentic_bundle_matches_the_generated_public_tree() -> None:
    from synthworld.agentic.serialization import load_public_agentic_bundle

    assert load_public_agentic_bundle() == generate_asteria_agentic_v1().public


def test_load_public_agentic_bundle_reads_an_exported_tree_and_verifies_it(
    tmp_path: Path,
) -> None:
    from synthworld.agentic.serialization import load_public_agentic_bundle

    benchmark = generate_asteria_agentic_v1()
    root = tmp_path / "asteria-agentic-v1"
    export_agentic_benchmark(root, benchmark)
    public_root = root / "public"

    assert load_public_agentic_bundle(public_root) == benchmark.public

    events = public_root / "public_events.jsonl"
    events.write_bytes(events.read_bytes() + b"\n")
    with pytest.raises(AgenticArtifactError, match="checksum"):
        load_public_agentic_bundle(public_root)


def test_load_public_agentic_bundle_rejects_files_the_manifest_does_not_name(
    tmp_path: Path,
) -> None:
    """Hashing only the named set leaves the tree open at the other end.

    Every expected path can be present and hash correctly while the directory also
    holds a stale artifact from an older run, or one smuggled into a caller-supplied
    ``root``. Nothing enumerated the directory, so such a tree verified clean.
    """

    from synthworld.agentic.serialization import load_public_agentic_bundle

    benchmark = generate_asteria_agentic_v1()
    root = tmp_path / "asteria-agentic-v1"
    export_agentic_benchmark(root, benchmark)
    public_root = root / "public"

    stray = public_root / "leftover.jsonl"
    stray.write_text("{}\n", encoding="utf-8")
    with pytest.raises(AgenticArtifactError, match=re.escape("leftover.jsonl")):
        load_public_agentic_bundle(public_root)
    stray.unlink()

    # Nested, because a subdirectory is where an extra file is least visible - and
    # because a non-recursive check would pass this one.
    nested = public_root / "tool_schemas" / "extra-tools.json"
    nested.write_text("{}\n", encoding="utf-8")
    nested_message = re.escape("tool_schemas/extra-tools.json")
    with pytest.raises(AgenticArtifactError, match=nested_message):
        load_public_agentic_bundle(public_root)
    nested.unlink()

    assert load_public_agentic_bundle(public_root) == benchmark.public


def test_golden_loader_rejects_a_forged_public_artifact_set_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The evaluator cross-binding is what makes the packaged tree trustworthy."""

    import json as _json

    from synthworld.agentic import serialization

    benchmark = generate_asteria_agentic_v1()
    root = tmp_path / "asteria-agentic-v1"
    export_agentic_benchmark(root, benchmark)
    monkeypatch.setattr(serialization, "files", lambda _package: tmp_path)
    assert serialization.load_golden_agentic_benchmark() == benchmark

    checksums_path = root / "evaluator/checksums.json"
    checksums = _json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums["public_artifact_set_digest"] = "0" * 64
    checksums_path.write_text(_json.dumps(checksums), encoding="utf-8")
    with pytest.raises(AgenticArtifactError):
        serialization.load_golden_agentic_benchmark()
