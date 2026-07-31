"""Executable conformance check for the failure-reason precedence spec.

Mirrors agent-authority-contract/docs/failure-reason-precedence.md: each
spec clause is transcribed here as an independent predicate over delegation
configurations, every configuration profile is enumerated deterministically,
and the oracle must agree with the clause outcome on all of them - including
the ambiguity rejection, the derived effective policy version, and the
published chain on a mismatch denial. The named tests pin the spec's
lettered consequences individually.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import pytest

from synthworld.agentic.models import (
    ActionAttempt,
    AgenticWorldSnapshot,
    AgenticWorldState,
    AuthorityFailureReason,
    CanonicalBinding,
    Capability,
    Credential,
    Decision,
    Delegation,
    LogicalAgent,
    Organisation,
    PolicyVersion,
    Principal,
    PrincipalKind,
    Resource,
    Runtime,
)
from synthworld.agentic.replay import AgenticReplayError, evaluate_action_authority

_T = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
_DAY = timedelta(days=1)

_ORG_ID = "org-harness"
_OWNER_ID = "p-owner"
_RUNTIME_PRINCIPAL_ID = "p-runtime"
_AGENT_ID = "agent-1"
_CHILD_AGENT_ID = "agent-2"
_RESOURCE_ID = "res-1"
_RUNTIME_ID = "rt-1"
_CREDENTIAL_ID = "cred-1"


class _Temporal(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    FUTURE = "future"


_WINDOWS: dict[_Temporal, tuple[datetime, datetime]] = {
    _Temporal.VALID: (_T - 30 * _DAY, _T + 30 * _DAY),
    _Temporal.EXPIRED: (_T - 60 * _DAY, _T - 30 * _DAY),
    _Temporal.FUTURE: (_T + 30 * _DAY, _T + 60 * _DAY),
}


@dataclass(frozen=True)
class _DelegationConfig:
    policy_match: bool
    capability_sufficient: bool
    temporal: _Temporal
    revoked: bool

    @property
    def label(self) -> str:
        return (
            f"pm{int(self.policy_match)}"
            f"-cs{int(self.capability_sufficient)}"
            f"-{self.temporal.value}"
            f"-rv{int(self.revoked)}"
        )


_CONFIGS: tuple[_DelegationConfig, ...] = tuple(
    _DelegationConfig(
        policy_match=policy_match,
        capability_sufficient=capability_sufficient,
        temporal=temporal,
        revoked=revoked,
    )
    for policy_match in (True, False)
    for capability_sufficient in (True, False)
    for temporal in _Temporal
    for revoked in (False, True)
)
_CAPABLE = _DelegationConfig(
    policy_match=True,
    capability_sufficient=True,
    temporal=_Temporal.VALID,
    revoked=False,
)
_MISMATCHED_CAPABLE = _DelegationConfig(
    policy_match=False,
    capability_sufficient=True,
    temporal=_Temporal.VALID,
    revoked=False,
)
_REVOKED_CAPABLE = _DelegationConfig(
    policy_match=True,
    capability_sufficient=True,
    temporal=_Temporal.VALID,
    revoked=True,
)

_SUFFICIENT_CAPABILITY = Capability(
    resource_ids=(_RESOURCE_ID,),
    actions=("read",),
    scopes=("scope:read",),
    purpose="procurement",
)
_INSUFFICIENT_CAPABILITY = Capability(
    resource_ids=(_RESOURCE_ID,),
    actions=("read",),
    scopes=("scope:other",),
    purpose="procurement",
)
_DELEGABLE_CAPABILITY = Capability(
    resource_ids=(_RESOURCE_ID,),
    actions=("read",),
    scopes=("scope:read",),
    purpose="procurement",
    may_delegate=True,
)

_SNAPSHOT = AgenticWorldSnapshot(
    world_id="precedence-harness",
    world_version="1.0.0",
    seed=0,
    organisations=(
        Organisation(
            id=_ORG_ID,
            display_name="Precedence Harness",
            tenant_id="tenant-harness",
        ),
    ),
    departments=(),
    principals=(
        Principal(
            id=_OWNER_ID,
            kind=PrincipalKind.HUMAN,
            display_name="Owner",
            organisation_id=_ORG_ID,
        ),
        Principal(
            id=_RUNTIME_PRINCIPAL_ID,
            kind=PrincipalKind.WORKLOAD,
            display_name="Runtime principal",
            organisation_id=_ORG_ID,
            owner_principal_id=_OWNER_ID,
        ),
    ),
    agents=(
        LogicalAgent(
            id=_AGENT_ID,
            display_name="Agent",
            organisation_id=_ORG_ID,
            owner_principal_id=_OWNER_ID,
        ),
        LogicalAgent(
            id=_CHILD_AGENT_ID,
            display_name="Child agent",
            organisation_id=_ORG_ID,
            owner_principal_id=_OWNER_ID,
            parent_agent_id=_AGENT_ID,
        ),
    ),
    resources=(
        Resource(
            id=_RESOURCE_ID,
            display_name="Ledger",
            organisation_id=_ORG_ID,
            owner_principal_id=_OWNER_ID,
            actions=("read",),
        ),
    ),
    policies=(
        PolicyVersion(id="policy-1", version="v1"),
        PolicyVersion(id="policy-2", version="v2"),
    ),
    initial_evidence_refs=(),
)

_RUNTIME = Runtime(
    id=_RUNTIME_ID,
    logical_agent_id=_AGENT_ID,
    runtime_principal_id=_RUNTIME_PRINCIPAL_ID,
    owner_principal_id=_OWNER_ID,
    organisation_id=_ORG_ID,
)
_CREDENTIAL = Credential(
    id=_CREDENTIAL_ID,
    issuer_principal_id=_OWNER_ID,
    subject_principal_id=_RUNTIME_PRINCIPAL_ID,
    allowed_runtime_principal_ids=(_RUNTIME_PRINCIPAL_ID,),
    valid_from=_T - 30 * _DAY,
    expires_at=_T + 30 * _DAY,
)
_BINDING = CanonicalBinding(
    action_event_id="evt-harness",
    originating_principal_id=_OWNER_ID,
    logical_agent_id=_AGENT_ID,
    runtime_id=_RUNTIME_ID,
    runtime_principal_id=_RUNTIME_PRINCIPAL_ID,
    credential_subject_id=_RUNTIME_PRINCIPAL_ID,
    attributed_actor_id=_OWNER_ID,
    accountable_owner_chain=(_OWNER_ID,),
)
_ATTEMPT = ActionAttempt(
    originating_principal_claim=None,
    logical_agent_claim=None,
    runtime_principal_claim=None,
    attributed_actor_claim=None,
    presented_credential_id=_CREDENTIAL_ID,
    resource_id=_RESOURCE_ID,
    action="read",
    requested_scope=("scope:read",),
    purpose="procurement",
    policy_version="v1",
    evidence_refs=(),
)

_DELEGATION_FAMILY = frozenset(
    {
        AuthorityFailureReason.POLICY_VERSION_MISMATCH,
        AuthorityFailureReason.DELEGATION_REVOKED,
        AuthorityFailureReason.CAPABILITY_EXCEEDED,
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
    }
)


def _delegation(config: _DelegationConfig, delegation_id: str) -> Delegation:
    valid_from, expires_at = _WINDOWS[config.temporal]
    capability = (
        _SUFFICIENT_CAPABILITY
        if config.capability_sufficient
        else _INSUFFICIENT_CAPABILITY
    )
    return Delegation(
        id=delegation_id,
        originating_principal_id=_OWNER_ID,
        delegator_principal_id=_OWNER_ID,
        grantee_agent_id=_AGENT_ID,
        capability=capability,
        policy_version="v1" if config.policy_match else "v2",
        valid_from=valid_from,
        expires_at=expires_at,
    )


_DELEGATIONS: dict[_DelegationConfig, Delegation] = {
    config: _delegation(config, f"del-{config.label}") for config in _CONFIGS
}


def _state(
    delegations: tuple[Delegation, ...],
    revoked: tuple[str, ...],
) -> AgenticWorldState:
    return AgenticWorldState(
        snapshot=_SNAPSHOT,
        through_event_index=0,
        as_of=None,
        runtimes=(_RUNTIME,),
        credentials=(_CREDENTIAL,),
        delegations=delegations,
        revoked_delegation_ids=revoked,
        retained_evidence_refs=(),
        action_event_ids=(),
        audit_event_ids=(),
    )


def _capability_allows(capability: Capability, attempt: ActionAttempt) -> bool:
    """CapabilityAllows from the spec: the conjunction of four containments."""
    return (
        attempt.resource_id in capability.resource_ids
        and attempt.action in capability.actions
        and set(attempt.requested_scope) <= set(capability.scopes)
        and attempt.purpose == capability.purpose
    )


@dataclass(frozen=True)
class _SpecOutcome:
    chain: tuple[str, ...]
    reason: AuthorityFailureReason | None
    effective_policy_version: str


def _spec_outcome(
    delegations: tuple[Delegation, ...],
    revoked: frozenset[str],
) -> _SpecOutcome | None:
    """Clauses of the precedence spec, transcribed from the document.

    Returns None where the spec declares the world ambiguous (capable
    delegations disagreeing on policy version), which the oracle rejects.
    """
    candidates = [
        item
        for item in delegations
        if item.grantee_agent_id == _BINDING.logical_agent_id
        and item.originating_principal_id == _BINDING.originating_principal_id
    ]
    time_valid = [
        item for item in candidates if item.valid_from <= _T < item.expires_at
    ]
    active = [item for item in time_valid if item.id not in revoked]
    capable = [item for item in active if _capability_allows(item.capability, _ATTEMPT)]
    if capable:
        if len({item.policy_version for item in capable}) > 1:
            return None
        selected = min(capable, key=lambda item: item.id)
        assert selected.parent_delegation_id is None
        chain = (selected.id,)
        if selected.policy_version != _ATTEMPT.policy_version:
            return _SpecOutcome(
                chain,
                AuthorityFailureReason.POLICY_VERSION_MISMATCH,
                selected.policy_version,
            )
        return _SpecOutcome(chain, None, selected.policy_version)
    if any(
        _capability_allows(item.capability, _ATTEMPT) and item.id in revoked
        for item in time_valid
    ):
        return _SpecOutcome(
            (), AuthorityFailureReason.DELEGATION_REVOKED, _ATTEMPT.policy_version
        )
    if active:
        return _SpecOutcome(
            (), AuthorityFailureReason.CAPABILITY_EXCEEDED, _ATTEMPT.policy_version
        )
    return _SpecOutcome(
        (), AuthorityFailureReason.NO_ACTIVE_DELEGATION, _ATTEMPT.policy_version
    )


def _assert_matches_spec(
    items: tuple[tuple[_DelegationConfig, Delegation], ...],
) -> None:
    delegations = tuple(item for _, item in items)
    revoked = tuple(sorted(item.id for config, item in items if config.revoked))
    label = ", ".join(item.id for item in delegations) or "<empty>"
    state = _state(delegations, revoked)
    outcome = _spec_outcome(delegations, frozenset(revoked))
    if outcome is None:
        with pytest.raises(AgenticReplayError, match="disagree on policy version"):
            evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
        return
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert set(result.failure_reasons) <= _DELEGATION_FAMILY, label
    family = tuple(
        item for item in result.failure_reasons if item in _DELEGATION_FAMILY
    )
    assert result.delegation_chain_ids == outcome.chain, label
    assert result.effective_policy_version == outcome.effective_policy_version, label
    expected_policy_evidence = f"evidence:policy:{outcome.effective_policy_version}"
    assert expected_policy_evidence in result.required_evidence_refs, label
    delegation_evidence = {
        item
        for item in result.required_evidence_refs
        if item.startswith("evidence:delegation:")
    }
    assert delegation_evidence == {
        f"evidence:delegation:{item}" for item in outcome.chain
    }, label
    if outcome.reason is None:
        assert result.decision is Decision.ALLOW, label
        assert family == (), label
        assert result.expected_side_effect == "read_recorded", label
    else:
        assert result.decision is Decision.DENY, label
        assert family == (outcome.reason,), label
        assert result.expected_side_effect == "none", label


@pytest.mark.parametrize("config", _CONFIGS, ids=[config.label for config in _CONFIGS])
def test_each_single_delegation_profile_matches_its_spec_clause(
    config: _DelegationConfig,
) -> None:
    _assert_matches_spec(((config, _DELEGATIONS[config]),))


def test_every_ordered_pair_of_profiles_matches_its_spec_clause() -> None:
    for first, second in itertools.product(_CONFIGS, repeat=2):
        primary = _DELEGATIONS[first]
        secondary = _DELEGATIONS[second].model_copy(
            update={"id": f"{_DELEGATIONS[second].id}-b"}
        )
        _assert_matches_spec(((first, primary), (second, secondary)))


def test_no_delegations_at_all_yields_no_active_delegation() -> None:
    _assert_matches_spec(())


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("grantee_agent_id", _CHILD_AGENT_ID),
        ("originating_principal_id", "p-other"),
    ),
)
def test_delegations_for_other_bindings_are_invisible(field: str, value: str) -> None:
    """Candidate filtering keys on the binding, not on any attempt claim."""
    foreign = _DELEGATIONS[_CAPABLE].model_copy(update={field: value})
    _assert_matches_spec(((_CAPABLE, foreign),))


def test_attempt_claims_do_not_override_the_binding() -> None:
    """A claim naming the foreign grantee does not make it visible."""
    foreign = _DELEGATIONS[_CAPABLE].model_copy(
        update={"grantee_agent_id": _CHILD_AGENT_ID}
    )
    attempt = _ATTEMPT.model_copy(update={"logical_agent_claim": _CHILD_AGENT_ID})
    result = evaluate_action_authority(
        _state((foreign,), ()), attempt, _BINDING, decision_time=_T
    )
    assert result.failure_reasons == (AuthorityFailureReason.NO_ACTIVE_DELEGATION,)


@pytest.mark.parametrize(
    "update",
    (
        {"resource_ids": ("res-other",)},
        {"actions": ("write",)},
        {"scopes": ("scope:other",)},
        {"purpose": "unrelated-purpose"},
    ),
    ids=("resource", "action", "scope", "purpose"),
)
def test_each_capability_clause_alone_defeats_sufficiency(
    update: dict[str, object],
) -> None:
    """CapabilityAllows is a conjunction; each clause alone breaks it."""
    capability = _SUFFICIENT_CAPABILITY.model_copy(update=update)
    item = _DELEGATIONS[_CAPABLE].model_copy(update={"capability": capability})
    _assert_matches_spec(((_CAPABLE, item),))


@pytest.mark.parametrize("temporal", (_Temporal.EXPIRED, _Temporal.FUTURE))
def test_expired_or_future_delegation_yields_no_active_delegation(
    temporal: _Temporal,
) -> None:
    """Spec consequence (a): there is no temporal member of the family."""
    config = _DelegationConfig(
        policy_match=True,
        capability_sufficient=True,
        temporal=temporal,
        revoked=False,
    )
    state = _state((_DELEGATIONS[config],), ())
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.failure_reasons == (AuthorityFailureReason.NO_ACTIVE_DELEGATION,)


def test_revoked_under_superseded_policy_is_still_delegation_revoked() -> None:
    """Spec consequence (b): the revoked probe is version-blind, so a revoked
    capability-sufficient delegation is reported as revoked whatever policy
    version it was granted under."""
    config = _DelegationConfig(
        policy_match=False,
        capability_sufficient=True,
        temporal=_Temporal.VALID,
        revoked=True,
    )
    item = _DELEGATIONS[config]
    state = _state((item,), (item.id,))
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.failure_reasons == (AuthorityFailureReason.DELEGATION_REVOKED,)
    assert result.delegation_chain_ids == ()


def test_a_covering_mismatched_delegation_outranks_delegation_revoked() -> None:
    """Spec consequence (c): a delegation that covers the capability is
    selected version-blind, so its version mismatch explains the denial and
    the revoked probe is never consulted. The chain is published."""
    mismatched = _DELEGATIONS[_MISMATCHED_CAPABLE]
    revoked_item = _DELEGATIONS[_REVOKED_CAPABLE]
    state = _state((mismatched, revoked_item), (revoked_item.id,))
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.failure_reasons == (AuthorityFailureReason.POLICY_VERSION_MISMATCH,)
    assert result.delegation_chain_ids == (mismatched.id,)
    assert result.effective_policy_version == "v2"


def test_delegation_revoked_outranks_no_active_delegation() -> None:
    """Spec consequence (d): the revoked probe fires with nothing active."""
    item = _DELEGATIONS[_REVOKED_CAPABLE]
    state = _state((item,), (item.id,))
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.failure_reasons == (AuthorityFailureReason.DELEGATION_REVOKED,)


def test_wrong_policy_and_insufficient_capability_is_capability_exceeded() -> None:
    """Spec consequence (e): capability_exceeded is the residual, covering
    active delegations that are simultaneously wrong-policy and
    capability-insufficient."""
    config = _DelegationConfig(
        policy_match=False,
        capability_sufficient=False,
        temporal=_Temporal.VALID,
        revoked=False,
    )
    state = _state((_DELEGATIONS[config],), ())
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.failure_reasons == (AuthorityFailureReason.CAPABILITY_EXCEEDED,)


def test_capable_delegations_disagreeing_on_version_reject_the_world() -> None:
    """Spec clause A: a capable set spanning two policy versions is an
    ambiguous world, rejected rather than decided."""
    state = _state((_DELEGATIONS[_CAPABLE], _DELEGATIONS[_MISMATCHED_CAPABLE]), ())
    with pytest.raises(AgenticReplayError, match="disagree on policy version"):
        evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)


def test_mismatch_denial_derives_the_effective_policy_version() -> None:
    """The effective version is the covering delegation's, not the attempt's,
    and policy evidence names the governing version."""
    mismatched = _DELEGATIONS[_MISMATCHED_CAPABLE]
    state = _state((mismatched,), ())
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.decision is Decision.DENY
    assert result.failure_reasons == (AuthorityFailureReason.POLICY_VERSION_MISMATCH,)
    assert result.delegation_chain_ids == (mismatched.id,)
    assert result.effective_policy_version == "v2"
    assert "evidence:policy:v2" in result.required_evidence_refs
    assert "evidence:policy:v1" not in result.required_evidence_refs


def test_unknown_policy_version_collapses_with_the_chain_mismatch() -> None:
    """Both policy_version_mismatch sources fire and collapse in the set:
    the attempted version is absent from the snapshot and differs from the
    covering delegation's."""
    attempt = _ATTEMPT.model_copy(update={"policy_version": "v3"})
    capable = _DELEGATIONS[_CAPABLE]
    result = evaluate_action_authority(
        _state((capable,), ()), attempt, _BINDING, decision_time=_T
    )
    assert result.failure_reasons == (AuthorityFailureReason.POLICY_VERSION_MISMATCH,)
    assert result.delegation_chain_ids == (capable.id,)
    assert result.effective_policy_version == "v1"


def test_overprivileged_subdelegation_requires_an_effective_chain() -> None:
    """Spec consequence (f): without a chain the proposal is not separately
    flagged; with one, the denial still records the chain."""
    capable = _DELEGATIONS[_CAPABLE]
    proposal = capable.model_copy(
        update={"id": "del-proposal", "parent_delegation_id": capable.id}
    )
    attempt = _ATTEMPT.model_copy(update={"proposed_delegation": proposal})

    without_chain = evaluate_action_authority(
        _state((), ()), attempt, _BINDING, decision_time=_T
    )
    assert without_chain.failure_reasons == (
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
    )

    with_chain = evaluate_action_authority(
        _state((capable,), ()), attempt, _BINDING, decision_time=_T
    )
    assert with_chain.decision is Decision.DENY
    assert with_chain.failure_reasons == (
        AuthorityFailureReason.OVERPRIVILEGED_SUBDELEGATION,
    )
    assert with_chain.delegation_chain_ids == (capable.id,)


def test_attenuated_proposal_under_the_selected_leaf_is_allowed() -> None:
    """The proposal is judged against the selected leaf of the chain, not
    its root: an attenuated proposal parented to the leaf is accepted."""
    root = _DELEGATIONS[_CAPABLE].model_copy(
        update={"id": "del-r", "capability": _DELEGABLE_CAPABILITY}
    )
    leaf = root.model_copy(update={"id": "del-a", "parent_delegation_id": "del-r"})
    proposal = Delegation(
        id="del-z-proposal",
        originating_principal_id=_OWNER_ID,
        delegator_principal_id=_OWNER_ID,
        grantee_agent_id=_CHILD_AGENT_ID,
        parent_delegation_id="del-a",
        capability=_SUFFICIENT_CAPABILITY,
        policy_version="v1",
        valid_from=_WINDOWS[_Temporal.VALID][0],
        expires_at=_WINDOWS[_Temporal.VALID][1],
    )
    attempt = _ATTEMPT.model_copy(update={"proposed_delegation": proposal})
    result = evaluate_action_authority(
        _state((root, leaf), ()), attempt, _BINDING, decision_time=_T
    )
    assert result.decision is Decision.ALLOW
    assert result.failure_reasons == ()
    assert result.delegation_chain_ids == ("del-r", "del-a")


def test_proposal_exceeding_the_selected_leaf_is_overprivileged() -> None:
    """Attenuation is a subset check against the selected leaf's capability:
    a proposal inside the root's grant but outside the narrower leaf's is
    over-privileged, so neither the may_delegate flag nor the root can be
    the quantity actually checked."""
    broad = _DELEGABLE_CAPABILITY.model_copy(
        update={"scopes": ("scope:extra", "scope:read")}
    )
    root = _DELEGATIONS[_CAPABLE].model_copy(
        update={"id": "del-b-root", "capability": broad}
    )
    leaf = _DELEGATIONS[_CAPABLE].model_copy(
        update={
            "id": "del-a-leaf",
            "parent_delegation_id": "del-b-root",
            "capability": _DELEGABLE_CAPABILITY,
        }
    )
    proposal = leaf.model_copy(
        update={
            "id": "del-wide",
            "parent_delegation_id": "del-a-leaf",
            "capability": _DELEGABLE_CAPABILITY.model_copy(
                update={"scopes": ("scope:extra",)}
            ),
        }
    )
    attempt = _ATTEMPT.model_copy(update={"proposed_delegation": proposal})
    result = evaluate_action_authority(
        _state((root, leaf), ()), attempt, _BINDING, decision_time=_T
    )
    assert result.failure_reasons == (
        AuthorityFailureReason.OVERPRIVILEGED_SUBDELEGATION,
    )
    assert result.delegation_chain_ids == ("del-b-root", "del-a-leaf")


def test_overprivileged_and_policy_mismatch_co_fire_on_a_mismatch_row() -> None:
    """A mismatch denial publishes its chain, so the sub-delegation check
    still runs and both reasons appear, lexicographically ordered."""
    mismatched = _DELEGATIONS[_MISMATCHED_CAPABLE]
    proposal = mismatched.model_copy(
        update={"id": "del-proposal", "parent_delegation_id": mismatched.id}
    )
    attempt = _ATTEMPT.model_copy(update={"proposed_delegation": proposal})
    result = evaluate_action_authority(
        _state((mismatched,), ()), attempt, _BINDING, decision_time=_T
    )
    assert result.failure_reasons == (
        AuthorityFailureReason.OVERPRIVILEGED_SUBDELEGATION,
        AuthorityFailureReason.POLICY_VERSION_MISMATCH,
    )
    assert result.delegation_chain_ids == (mismatched.id,)


def test_invalid_credential_suppresses_allowed_runtime_wrong_runtime() -> None:
    """Spec consequence (g): the allowed-runtime source of wrong_runtime is
    only reachable when the credential check passes."""
    expired_disallowing = _CREDENTIAL.model_copy(
        update={
            "valid_from": _T - 60 * _DAY,
            "expires_at": _T - 30 * _DAY,
            "allowed_runtime_principal_ids": ("p-other",),
        }
    )
    state = _state((), ()).model_copy(update={"credentials": (expired_disallowing,)})
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert AuthorityFailureReason.WRONG_RUNTIME not in result.failure_reasons
    assert result.failure_reasons == (
        AuthorityFailureReason.CREDENTIAL_INVALID,
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
    )


def test_credential_bound_runtime_exclusion_is_wrong_runtime() -> None:
    """Spec consequence (g), positive half: a valid credential that does not
    admit the binding's runtime principal fires the allowed-runtime source."""
    disallowing = _CREDENTIAL.model_copy(
        update={"allowed_runtime_principal_ids": ("p-other",)}
    )
    state = _state((), ()).model_copy(update={"credentials": (disallowing,)})
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.failure_reasons == (
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
        AuthorityFailureReason.WRONG_RUNTIME,
    )


def test_min_id_selection_walks_the_chain_root_first() -> None:
    """Spec consequence (h): lexicographically smallest capable id wins and
    the reported chain runs root-first to the selected leaf."""
    parent = _DELEGATIONS[_CAPABLE].model_copy(update={"id": "del-p"})
    child = parent.model_copy(update={"id": "del-c", "parent_delegation_id": "del-p"})
    state = _state((parent, child), ())
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.decision is Decision.ALLOW
    assert result.delegation_chain_ids == ("del-p", "del-c")


def test_chain_walk_rejects_cyclic_parent_links() -> None:
    """Well-formedness precondition: a covering delegation whose parent
    links form a cycle is a corrupt state and is rejected, not walked."""
    looped = _DELEGATIONS[_CAPABLE].model_copy(
        update={"id": "del-loop", "parent_delegation_id": "del-loop"}
    )
    state = _state((looped,), ())
    with pytest.raises(AgenticReplayError, match="contains a cycle"):
        evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)


def test_chain_walk_rejects_a_missing_parent() -> None:
    """Well-formedness precondition: a covering delegation citing an absent
    parent is a corrupt state and is rejected, not truncated."""
    dangling = _DELEGATIONS[_CAPABLE].model_copy(
        update={"id": "del-dangling", "parent_delegation_id": "del-ghost"}
    )
    state = _state((dangling,), ())
    with pytest.raises(AgenticReplayError, match="missing parent"):
        evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)


def test_unknown_resource_composes_both_families() -> None:
    """The no_active_delegation second source (unknown entity) composes with
    a genuine family reason from the chain probe."""
    attempt = _ATTEMPT.model_copy(update={"resource_id": "res-ghost"})
    state = _state((_DELEGATIONS[_CAPABLE],), ())
    result = evaluate_action_authority(state, attempt, _BINDING, decision_time=_T)
    assert result.failure_reasons == (
        AuthorityFailureReason.CAPABILITY_EXCEEDED,
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
    )


def test_cross_organisation_resource_adds_tenant_mismatch() -> None:
    """The tenant check is independent of the delegation family."""
    foreign_resource = _SNAPSHOT.resources[0].model_copy(
        update={"organisation_id": "org-other"}
    )
    snapshot = _SNAPSHOT.model_copy(update={"resources": (foreign_resource,)})
    state = _state((), ()).model_copy(update={"snapshot": snapshot})
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.failure_reasons == (
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
        AuthorityFailureReason.TENANT_MISMATCH,
    )


def test_credential_subject_mismatch_is_credential_invalid() -> None:
    """The credential subject is checked against the binding."""
    binding = _BINDING.model_copy(update={"credential_subject_id": "p-other"})
    result = evaluate_action_authority(
        _state((), ()), _ATTEMPT, binding, decision_time=_T
    )
    assert result.failure_reasons == (
        AuthorityFailureReason.CREDENTIAL_INVALID,
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
    )


def test_unknown_credential_is_credential_invalid() -> None:
    """A presented credential id absent from the state is invalid on its
    own, before any subject or window comparison exists to fail."""
    attempt = _ATTEMPT.model_copy(update={"presented_credential_id": "cred-ghost"})
    result = evaluate_action_authority(
        _state((), ()), attempt, _BINDING, decision_time=_T
    )
    assert result.failure_reasons == (
        AuthorityFailureReason.CREDENTIAL_INVALID,
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
    )


def test_fallback_effective_version_is_the_attempted_version() -> None:
    """On clauses 2-4 the effective version falls back to the attempted
    version, whatever it is - not to a constant or the snapshot default."""
    attempt = _ATTEMPT.model_copy(update={"policy_version": "v2"})
    result = evaluate_action_authority(
        _state((), ()), attempt, _BINDING, decision_time=_T
    )
    assert result.failure_reasons == (AuthorityFailureReason.NO_ACTIVE_DELEGATION,)
    assert result.effective_policy_version == "v2"
    assert "evidence:policy:v2" in result.required_evidence_refs


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("logical_agent_id", _CHILD_AGENT_ID),
        ("runtime_principal_id", _OWNER_ID),
    ),
)
def test_runtime_binding_disagreement_is_wrong_runtime(field: str, value: str) -> None:
    """wrong_runtime source A fires when either recorded runtime field
    disagrees with the binding, not only on an unknown runtime."""
    foreign_runtime = _RUNTIME.model_copy(update={field: value})
    state = _state((), ()).model_copy(update={"runtimes": (foreign_runtime,)})
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.failure_reasons == (
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
        AuthorityFailureReason.WRONG_RUNTIME,
    )


def test_corruption_off_the_walked_path_is_not_detected() -> None:
    """The well-formedness raises are lazy: a cycle among delegations the
    walk never visits does not surface, and the clean covering delegation
    decides normally."""
    cycle_a = _DELEGATIONS[_CAPABLE].model_copy(
        update={
            "id": "del-cycle-a",
            "parent_delegation_id": "del-cycle-b",
            "capability": _INSUFFICIENT_CAPABILITY,
        }
    )
    cycle_b = cycle_a.model_copy(
        update={"id": "del-cycle-b", "parent_delegation_id": "del-cycle-a"}
    )
    clean = _DELEGATIONS[_CAPABLE]
    state = _state((cycle_a, cycle_b, clean), ())
    result = evaluate_action_authority(state, _ATTEMPT, _BINDING, decision_time=_T)
    assert result.decision is Decision.ALLOW
    assert result.delegation_chain_ids == (clean.id,)


def test_reason_tuple_order_is_lexicographic_not_precedence() -> None:
    """The serialized tuple sorts by enum value string; it does not encode
    the precedence that selected the delegation-family reason."""
    binding = _BINDING.model_copy(update={"runtime_id": "rt-missing"})
    result = evaluate_action_authority(
        _state((), ()), _ATTEMPT, binding, decision_time=_T
    )
    assert result.decision is Decision.DENY
    assert result.failure_reasons == (
        AuthorityFailureReason.NO_ACTIVE_DELEGATION,
        AuthorityFailureReason.WRONG_RUNTIME,
    )
