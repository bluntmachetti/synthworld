"""Deterministic tick-and-event-id replay for the PR6 agentic overlay."""

from __future__ import annotations

from synthworld.agentic.enterprise.errors import EnterpriseAgenticIntegrityError
from synthworld.agentic.enterprise.models import (
    EnterpriseAgenticActionAttemptedV1,
    EnterpriseAgenticCredentialRevokedV1,
    EnterpriseAgenticDelegationRevokedV1,
    EnterpriseAgenticEventV1,
    EnterpriseAgenticEvidenceDiscardedV1,
    EnterpriseAgenticReplayStateV1,
    EnterpriseAgenticSnapshotV1,
)


def materialize_enterprise_agentic_overlay(
    snapshot: EnterpriseAgenticSnapshotV1,
    events: tuple[EnterpriseAgenticEventV1, ...],
    *,
    before_event_id: str | None = None,
) -> EnterpriseAgenticReplayStateV1:
    """Replay the canonical event prefix before ``before_event_id``, or all events."""

    _validate_snapshot_references(snapshot)
    ordered = tuple(sorted(events, key=lambda item: (item.tick, item.id)))
    if events != ordered or len({item.id for item in events}) != len(events):
        raise EnterpriseAgenticIntegrityError(
            "enterprise agentic events must be unique and ordered by tick then id"
        )
    stop = len(events)
    if before_event_id is not None:
        positions = {event.id: index for index, event in enumerate(events)}
        if before_event_id not in positions:
            raise EnterpriseAgenticIntegrityError(
                "enterprise agentic replay boundary event is unknown"
            )
        stop = positions[before_event_id]

    credential_ids = {item.id for item in snapshot.credentials}
    delegation_ids = {item.id for item in snapshot.delegations}
    known_evidence = set(snapshot.initial_evidence_refs)
    revoked_credentials: set[str] = set()
    revoked_delegations: set[str] = set()
    discarded_evidence: set[str] = set()
    action_ids: set[str] = set()
    audit_ids: set[str] = set()
    processed: list[str] = []
    for event in events[:stop]:
        payload = event.payload
        if isinstance(payload, EnterpriseAgenticCredentialRevokedV1):
            if payload.credential_id not in credential_ids:
                raise EnterpriseAgenticIntegrityError(
                    "enterprise agentic event revokes an unknown credential"
                )
            if payload.credential_id in revoked_credentials:
                raise EnterpriseAgenticIntegrityError(
                    "enterprise agentic credential is revoked more than once"
                )
            revoked_credentials.add(payload.credential_id)
        elif isinstance(payload, EnterpriseAgenticDelegationRevokedV1):
            if payload.delegation_id not in delegation_ids:
                raise EnterpriseAgenticIntegrityError(
                    "enterprise agentic event revokes an unknown delegation"
                )
            if payload.delegation_id in revoked_delegations:
                raise EnterpriseAgenticIntegrityError(
                    "enterprise agentic delegation is revoked more than once"
                )
            revoked_delegations.add(payload.delegation_id)
        elif isinstance(payload, EnterpriseAgenticEvidenceDiscardedV1):
            if not set(payload.evidence_refs) <= known_evidence:
                raise EnterpriseAgenticIntegrityError(
                    "enterprise agentic event discards unknown evidence"
                )
            discarded_evidence.update(payload.evidence_refs)
        elif isinstance(payload, EnterpriseAgenticActionAttemptedV1):
            action_ids.add(event.id)
        else:
            audit_ids.add(event.id)
        processed.append(event.id)
    return EnterpriseAgenticReplayStateV1(
        processed_event_ids=tuple(processed),
        revoked_credential_ids=tuple(revoked_credentials),
        revoked_delegation_ids=tuple(revoked_delegations),
        discarded_evidence_refs=tuple(discarded_evidence),
        action_event_ids=tuple(action_ids),
        audit_event_ids=tuple(audit_ids),
    )


def _validate_snapshot_references(snapshot: EnterpriseAgenticSnapshotV1) -> None:
    account_ids = {item.id for item in snapshot.accounts}
    runtime_ids = {item.id for item in snapshot.runtimes}
    capability_ids = {item.id for item in snapshot.capabilities}
    for runtime in snapshot.runtimes:
        if runtime.agent_account_id not in account_ids:
            raise EnterpriseAgenticIntegrityError(
                "enterprise agentic runtime references an unknown account"
            )
    for credential in snapshot.credentials:
        if (
            credential.agent_account_id not in account_ids
            or not set(credential.allowed_runtime_ids) <= runtime_ids
        ):
            raise EnterpriseAgenticIntegrityError(
                "enterprise agentic credential references an unknown account or runtime"
            )
    for delegation in snapshot.delegations:
        if (
            delegation.agent_account_id not in account_ids
            or delegation.capability_id not in capability_ids
        ):
            raise EnterpriseAgenticIntegrityError(
                "enterprise agentic delegation references an unknown account or "
                "capability"
            )


__all__ = ["materialize_enterprise_agentic_overlay"]
