"""Shared agent-authority graph construction for Explorer projections.

Both the published Asteria adapter and the generated enterprise-agentic
adapter consume the same ``AgenticPublicBundle`` contract, so the node, edge,
timeline, and evaluator-annotation construction lives here once. Adapters own
their world-identity checks, source records, and top-level projection models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid5

from synthworld.agentic.models import (
    ActionAttempted,
    AgenticEvaluatorBundle,
    AgenticPublicBundle,
    AuditPerformed,
    CredentialIssued,
    DelegationGranted,
    DelegationRevoked,
    EvidenceDiscarded,
    RuntimeSpawned,
)
from synthworld.explorer.models import (
    ExplorerEdgeKind,
    ExplorerEdgeV1,
    ExplorerEvaluatorAnnotationV1,
    ExplorerNodeKind,
    ExplorerNodeV1,
    ExplorerPropertyV1,
    ExplorerTimelineEventKind,
    ExplorerTimelineEventV1,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

EXPLORER_NAMESPACE = UUID("8d21366a-84bf-5fa8-87bc-7e36aa36e782")

type PropertyValue = str | tuple[str, ...]


def framed_identifier(domain: str, *parts: str) -> str:
    framed = "".join(f"{len(part.encode())}:{part}" for part in parts)
    uuid_name = f"{domain}\0{framed}"
    return f"{domain}:{uuid5(EXPLORER_NAMESPACE, uuid_name)}"


def build_properties(
    *entries: tuple[str, PropertyValue | None],
) -> tuple[ExplorerPropertyV1, ...]:
    return tuple(
        ExplorerPropertyV1(key=key, value=value)
        for key, value in entries
        if value is not None and value != ()
    )


class ProjectionBuilder:
    def __init__(self) -> None:
        self.nodes: list[ExplorerNodeV1] = []
        self.edges: list[ExplorerEdgeV1] = []
        self.timeline: list[ExplorerTimelineEventV1] = []

    @staticmethod
    def node_id(kind: ExplorerNodeKind, source_id: str) -> str:
        return framed_identifier("node", kind.value, source_id)

    def has_node(self, kind: ExplorerNodeKind, source_id: str) -> bool:
        node_id = self.node_id(kind, source_id)
        return any(item.id == node_id for item in self.nodes)

    def add_node(
        self,
        kind: ExplorerNodeKind,
        source_id: str,
        label: str,
        *,
        parent_node_id: str | None = None,
        properties: tuple[ExplorerPropertyV1, ...] = (),
    ) -> str:
        node_id = self.node_id(kind, source_id)
        self.nodes.append(
            ExplorerNodeV1(
                id=node_id,
                source_id=source_id,
                kind=kind,
                label=label,
                parent_node_id=parent_node_id,
                properties=properties,
            )
        )
        return node_id

    def add_edge(
        self,
        kind: ExplorerEdgeKind,
        source_node_id: str,
        target_node_id: str,
        *,
        qualifier: str,
        label: str,
        properties: tuple[ExplorerPropertyV1, ...] = (),
    ) -> str:
        edge_id = framed_identifier(
            "edge", kind.value, source_node_id, target_node_id, qualifier
        )
        self.edges.append(
            ExplorerEdgeV1(
                id=edge_id,
                kind=kind,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                label=label,
                properties=properties,
            )
        )
        return edge_id


def project_snapshot(builder: ProjectionBuilder, public: AgenticPublicBundle) -> None:
    snapshot = public.snapshot
    for organisation in snapshot.organisations:
        builder.add_node(
            ExplorerNodeKind.ORGANISATION,
            organisation.id,
            organisation.display_name,
            properties=build_properties(("tenant_id", organisation.tenant_id)),
        )
    for department in snapshot.departments:
        organisation_node = builder.node_id(
            ExplorerNodeKind.ORGANISATION, department.organisation_id
        )
        department_node = builder.add_node(
            ExplorerNodeKind.DEPARTMENT,
            department.id,
            department.display_name,
            parent_node_id=organisation_node,
        )
        builder.add_edge(
            ExplorerEdgeKind.CONTAINS,
            organisation_node,
            department_node,
            qualifier=department.id,
            label="contains",
        )
    for principal in snapshot.principals:
        parent_node_id = None
        if principal.department_id is not None:
            parent_node_id = builder.node_id(
                ExplorerNodeKind.DEPARTMENT, principal.department_id
            )
        elif principal.organisation_id is not None:
            parent_node_id = builder.node_id(
                ExplorerNodeKind.ORGANISATION, principal.organisation_id
            )
        principal_node = builder.add_node(
            ExplorerNodeKind.PRINCIPAL,
            principal.id,
            principal.display_name,
            parent_node_id=parent_node_id,
            properties=build_properties(("principal_kind", principal.kind.value)),
        )
        if parent_node_id is not None:
            builder.add_edge(
                ExplorerEdgeKind.CONTAINS,
                parent_node_id,
                principal_node,
                qualifier=principal.id,
                label="contains",
            )
        if principal.owner_principal_id is not None:
            builder.add_edge(
                ExplorerEdgeKind.OWNS,
                builder.node_id(
                    ExplorerNodeKind.PRINCIPAL, principal.owner_principal_id
                ),
                principal_node,
                qualifier=principal.id,
                label="owns",
            )
    for agent in snapshot.agents:
        owner_node = builder.node_id(
            ExplorerNodeKind.PRINCIPAL, agent.owner_principal_id
        )
        agent_node = builder.add_node(
            ExplorerNodeKind.LOGICAL_AGENT,
            agent.id,
            agent.display_name,
            parent_node_id=owner_node,
            properties=build_properties(("organisation_id", agent.organisation_id)),
        )
        builder.add_edge(
            ExplorerEdgeKind.OWNS,
            owner_node,
            agent_node,
            qualifier=agent.id,
            label="owns",
        )
        if agent.parent_agent_id is not None:
            builder.add_edge(
                ExplorerEdgeKind.PARENT_AGENT,
                builder.node_id(ExplorerNodeKind.LOGICAL_AGENT, agent.parent_agent_id),
                agent_node,
                qualifier=agent.id,
                label="parent agent",
            )
    for resource in snapshot.resources:
        owner_node = builder.node_id(
            ExplorerNodeKind.PRINCIPAL, resource.owner_principal_id
        )
        resource_node = builder.add_node(
            ExplorerNodeKind.RESOURCE,
            resource.id,
            resource.display_name,
            parent_node_id=owner_node,
            properties=build_properties(
                ("actions", resource.actions),
                ("organisation_id", resource.organisation_id),
            ),
        )
        builder.add_edge(
            ExplorerEdgeKind.OWNS,
            owner_node,
            resource_node,
            qualifier=resource.id,
            label="owns",
        )


def project_events(builder: ProjectionBuilder, public: AgenticPublicBundle) -> None:
    for event in public.events:
        payload = event.payload
        related_nodes: list[str] = []
        related_edges: list[str] = []
        event_properties = list(
            build_properties(("evidence_refs", event.evidence_refs))
        )
        if isinstance(payload, DelegationGranted):
            delegation = payload.delegation
            delegation_node = builder.add_node(
                ExplorerNodeKind.DELEGATION,
                delegation.id,
                delegation.id,
                parent_node_id=builder.node_id(
                    ExplorerNodeKind.LOGICAL_AGENT, delegation.grantee_agent_id
                ),
                properties=build_properties(
                    ("actions", delegation.capability.actions),
                    (
                        "may_delegate",
                        str(delegation.capability.may_delegate).lower(),
                    ),
                    ("parent_delegation_id", delegation.parent_delegation_id),
                    ("purpose", delegation.capability.purpose),
                    ("scopes", delegation.capability.scopes),
                    ("policy_version", delegation.policy_version),
                    ("valid_from", delegation.valid_from.isoformat()),
                    ("expires_at", delegation.expires_at.isoformat()),
                ),
            )
            related_nodes.append(delegation_node)
            for kind, source_id, label in (
                (
                    ExplorerEdgeKind.ORIGINATES,
                    delegation.originating_principal_id,
                    "originates",
                ),
                (
                    ExplorerEdgeKind.DELEGATES,
                    delegation.delegator_principal_id,
                    "delegates",
                ),
            ):
                related_edges.append(
                    builder.add_edge(
                        kind,
                        builder.node_id(ExplorerNodeKind.PRINCIPAL, source_id),
                        delegation_node,
                        qualifier=event.id,
                        label=label,
                    )
                )
            if delegation.parent_delegation_id is not None:
                related_edges.append(
                    builder.add_edge(
                        ExplorerEdgeKind.PARENT_DELEGATION,
                        builder.node_id(
                            ExplorerNodeKind.DELEGATION,
                            delegation.parent_delegation_id,
                        ),
                        delegation_node,
                        qualifier=event.id,
                        label="parent delegation",
                    )
                )
            related_edges.append(
                builder.add_edge(
                    ExplorerEdgeKind.GRANTS_TO,
                    delegation_node,
                    builder.node_id(
                        ExplorerNodeKind.LOGICAL_AGENT, delegation.grantee_agent_id
                    ),
                    qualifier=event.id,
                    label="grants to",
                )
            )
            for resource_id in delegation.capability.resource_ids:
                related_edges.append(
                    builder.add_edge(
                        ExplorerEdgeKind.TARGETS,
                        delegation_node,
                        builder.node_id(ExplorerNodeKind.RESOURCE, resource_id),
                        qualifier=f"{event.id}:{resource_id}",
                        label="targets",
                    )
                )
        if isinstance(payload, CredentialIssued):
            credential = payload.credential
            credential_node = builder.add_node(
                ExplorerNodeKind.CREDENTIAL,
                credential.id,
                credential.id,
                parent_node_id=builder.node_id(
                    ExplorerNodeKind.PRINCIPAL, credential.subject_principal_id
                ),
                properties=build_properties(
                    ("valid_from", credential.valid_from.isoformat()),
                    ("expires_at", credential.expires_at.isoformat()),
                ),
            )
            related_nodes.append(credential_node)
            for kind, target_id, label in (
                (
                    ExplorerEdgeKind.ISSUES,
                    credential_node,
                    "issues",
                ),
                (
                    ExplorerEdgeKind.SUBJECT,
                    builder.node_id(
                        ExplorerNodeKind.PRINCIPAL,
                        credential.subject_principal_id,
                    ),
                    "subject",
                ),
            ):
                source_node = (
                    builder.node_id(
                        ExplorerNodeKind.PRINCIPAL,
                        credential.issuer_principal_id,
                    )
                    if kind == ExplorerEdgeKind.ISSUES
                    else credential_node
                )
                related_edges.append(
                    builder.add_edge(
                        kind,
                        source_node,
                        target_id,
                        qualifier=event.id,
                        label=label,
                    )
                )
            for runtime_principal_id in credential.allowed_runtime_principal_ids:
                related_edges.append(
                    builder.add_edge(
                        ExplorerEdgeKind.ALLOWS_RUNTIME,
                        credential_node,
                        builder.node_id(
                            ExplorerNodeKind.PRINCIPAL, runtime_principal_id
                        ),
                        qualifier=f"{event.id}:{runtime_principal_id}",
                        label="allows runtime",
                    )
                )
        if isinstance(payload, RuntimeSpawned):
            runtime = payload.runtime
            agent_node = builder.node_id(
                ExplorerNodeKind.LOGICAL_AGENT, runtime.logical_agent_id
            )
            runtime_node = builder.add_node(
                ExplorerNodeKind.RUNTIME,
                runtime.id,
                runtime.id,
                parent_node_id=agent_node,
                properties=build_properties(
                    ("organisation_id", runtime.organisation_id)
                ),
            )
            related_nodes.append(runtime_node)
            for kind, source_node, target_node, label in (
                (
                    ExplorerEdgeKind.EXECUTES_ON,
                    agent_node,
                    runtime_node,
                    "executes on",
                ),
                (
                    ExplorerEdgeKind.RUNS_AS,
                    runtime_node,
                    builder.node_id(
                        ExplorerNodeKind.PRINCIPAL, runtime.runtime_principal_id
                    ),
                    "runs as",
                ),
                (
                    ExplorerEdgeKind.OWNS,
                    builder.node_id(
                        ExplorerNodeKind.PRINCIPAL, runtime.owner_principal_id
                    ),
                    runtime_node,
                    "owns",
                ),
            ):
                related_edges.append(
                    builder.add_edge(
                        kind,
                        source_node,
                        target_node,
                        qualifier=event.id,
                        label=label,
                    )
                )
        if isinstance(payload, ActionAttempted):
            attempt = payload.attempt
            action_node = builder.add_node(
                ExplorerNodeKind.ACTION_ATTEMPT,
                event.id,
                f"{attempt.action} attempt",
                properties=build_properties(
                    ("action", attempt.action),
                    ("purpose", attempt.purpose),
                    ("requested_scope", attempt.requested_scope),
                    ("policy_version", attempt.policy_version),
                    (
                        "originating_principal_claim",
                        attempt.originating_principal_claim,
                    ),
                    ("logical_agent_claim", attempt.logical_agent_claim),
                    ("runtime_principal_claim", attempt.runtime_principal_claim),
                    ("attributed_actor_claim", attempt.attributed_actor_claim),
                    ("presented_credential_id", attempt.presented_credential_id),
                    (
                        "proposed_delegation_id",
                        attempt.proposed_delegation.id
                        if attempt.proposed_delegation is not None
                        else None,
                    ),
                ),
            )
            related_nodes.append(action_node)
            proposed_delegation = attempt.proposed_delegation
            if proposed_delegation is not None:
                proposed_node = builder.add_node(
                    ExplorerNodeKind.PROPOSED_DELEGATION,
                    proposed_delegation.id,
                    proposed_delegation.id,
                    properties=build_properties(
                        (
                            "originating_principal_id",
                            proposed_delegation.originating_principal_id,
                        ),
                        (
                            "delegator_principal_id",
                            proposed_delegation.delegator_principal_id,
                        ),
                        ("grantee_agent_id", proposed_delegation.grantee_agent_id),
                        (
                            "parent_delegation_id",
                            proposed_delegation.parent_delegation_id,
                        ),
                        (
                            "resource_ids",
                            proposed_delegation.capability.resource_ids,
                        ),
                        ("actions", proposed_delegation.capability.actions),
                        ("scopes", proposed_delegation.capability.scopes),
                        ("purpose", proposed_delegation.capability.purpose),
                        (
                            "may_delegate",
                            str(proposed_delegation.capability.may_delegate).lower(),
                        ),
                        ("policy_version", proposed_delegation.policy_version),
                        ("valid_from", proposed_delegation.valid_from.isoformat()),
                        ("expires_at", proposed_delegation.expires_at.isoformat()),
                    ),
                )
                related_nodes.append(proposed_node)
                related_edges.append(
                    builder.add_edge(
                        ExplorerEdgeKind.PROPOSES_DELEGATION,
                        action_node,
                        proposed_node,
                        qualifier=event.id,
                        label="proposes delegation",
                    )
                )
                for kind, source_id, label in (
                    (
                        ExplorerEdgeKind.ORIGINATES,
                        proposed_delegation.originating_principal_id,
                        "originates",
                    ),
                    (
                        ExplorerEdgeKind.DELEGATES,
                        proposed_delegation.delegator_principal_id,
                        "delegates",
                    ),
                ):
                    related_edges.append(
                        builder.add_edge(
                            kind,
                            builder.node_id(ExplorerNodeKind.PRINCIPAL, source_id),
                            proposed_node,
                            qualifier=event.id,
                            label=label,
                        )
                    )
                if proposed_delegation.parent_delegation_id is not None:
                    related_edges.append(
                        builder.add_edge(
                            ExplorerEdgeKind.PARENT_DELEGATION,
                            builder.node_id(
                                ExplorerNodeKind.DELEGATION,
                                proposed_delegation.parent_delegation_id,
                            ),
                            proposed_node,
                            qualifier=event.id,
                            label="parent delegation",
                        )
                    )
                related_edges.append(
                    builder.add_edge(
                        ExplorerEdgeKind.GRANTS_TO,
                        proposed_node,
                        builder.node_id(
                            ExplorerNodeKind.LOGICAL_AGENT,
                            proposed_delegation.grantee_agent_id,
                        ),
                        qualifier=event.id,
                        label="grants to",
                    )
                )
                for resource_id in proposed_delegation.capability.resource_ids:
                    related_edges.append(
                        builder.add_edge(
                            ExplorerEdgeKind.TARGETS,
                            proposed_node,
                            builder.node_id(ExplorerNodeKind.RESOURCE, resource_id),
                            qualifier=f"{event.id}:{resource_id}",
                            label="targets",
                        )
                    )
            for kind, node_kind, claim, label in (
                (
                    ExplorerEdgeKind.CLAIMS_ORIGINATOR,
                    ExplorerNodeKind.PRINCIPAL,
                    attempt.originating_principal_claim,
                    "claims originator",
                ),
                (
                    ExplorerEdgeKind.CLAIMS_AGENT,
                    ExplorerNodeKind.LOGICAL_AGENT,
                    attempt.logical_agent_claim,
                    "claims agent",
                ),
                (
                    ExplorerEdgeKind.CLAIMS_RUNTIME,
                    ExplorerNodeKind.PRINCIPAL,
                    attempt.runtime_principal_claim,
                    "claims runtime",
                ),
            ):
                if claim is not None and builder.has_node(node_kind, claim):
                    related_edges.append(
                        builder.add_edge(
                            kind,
                            builder.node_id(node_kind, claim),
                            action_node,
                            qualifier=event.id,
                            label=label,
                        )
                    )
            related_edges.extend(
                (
                    builder.add_edge(
                        ExplorerEdgeKind.PRESENTS,
                        action_node,
                        builder.node_id(
                            ExplorerNodeKind.CREDENTIAL,
                            attempt.presented_credential_id,
                        ),
                        qualifier=event.id,
                        label="presents",
                    ),
                    builder.add_edge(
                        ExplorerEdgeKind.ATTEMPTS,
                        action_node,
                        builder.node_id(ExplorerNodeKind.RESOURCE, attempt.resource_id),
                        qualifier=event.id,
                        label="attempts",
                        properties=build_properties(("action", attempt.action)),
                    ),
                )
            )
        if isinstance(payload, DelegationRevoked):
            related_nodes.append(
                builder.node_id(ExplorerNodeKind.DELEGATION, payload.delegation_id)
            )
        if isinstance(payload, EvidenceDiscarded):
            event_properties.extend(
                build_properties(("discarded_evidence_refs", payload.evidence_refs))
            )
        if isinstance(payload, AuditPerformed):
            event_properties.extend(build_properties(("audit_id", payload.audit_id)))
        builder.timeline.append(
            ExplorerTimelineEventV1(
                source_event_id=event.id,
                source_event_index=event.event_index,
                occurred_at=event.occurred_at,
                kind=ExplorerTimelineEventKind(payload.event_type),
                related_node_ids=tuple(related_nodes),
                related_edge_ids=tuple(related_edges),
                properties=tuple(event_properties),
            )
        )


def build_evaluator_annotations(
    action_nodes: Mapping[str, str],
    evaluator: AgenticEvaluatorBundle,
    *,
    subject: str,
) -> tuple[ExplorerEvaluatorAnnotationV1, ...]:
    """Build per-action evaluator annotations bound to public action nodes."""

    bindings = {item.action_event_id: item for item in evaluator.bindings}
    truths = {item.action_event_id: item for item in evaluator.authority_truth}
    cases = {item.action_event_id: item for item in evaluator.cases}
    expected_ids = set(action_nodes)
    if (
        set(bindings) != expected_ids
        or set(truths) != expected_ids
        or set(cases) != expected_ids
    ):
        raise ValueError(
            f"{subject} evaluator action inventory differs from the projection"
        )

    annotations: list[ExplorerEvaluatorAnnotationV1] = []
    for action_event_id in sorted(expected_ids):
        target_id = action_nodes[action_event_id]
        binding = bindings[action_event_id]
        truth = truths[action_event_id]
        case = cases[action_event_id]
        action_failures = (
            ", ".join(item.value for item in truth.failure_reasons_at_action) or "none"
        )
        audit_failures = (
            ", ".join(item.value for item in truth.failure_reasons_at_audit) or "none"
        )
        annotations.extend(
            (
                ExplorerEvaluatorAnnotationV1(
                    id=framed_identifier("annotation", action_event_id, "authority"),
                    source_action_event_id=action_event_id,
                    target_id=target_id,
                    kind="authority_decision",
                    label="Expected authority decision",
                    value=(
                        f"at action: {truth.decision_at_action.value}; "
                        f"at audit: {truth.decision_at_audit.value}"
                    ),
                    properties=build_properties(
                        ("expected_policy_version", truth.expected_policy_version),
                        ("expected_side_effect", truth.expected_side_effect),
                        (
                            "reconstructable_at_audit",
                            str(truth.reconstructable_at_audit).lower(),
                        ),
                    ),
                ),
                ExplorerEvaluatorAnnotationV1(
                    id=framed_identifier("annotation", action_event_id, "failures"),
                    source_action_event_id=action_event_id,
                    target_id=target_id,
                    kind="failure_reason",
                    label="Expected failure reasons",
                    value=(f"at action: {action_failures}; at audit: {audit_failures}"),
                    properties=build_properties(
                        ("delegation_chain_ids", truth.delegation_chain_ids),
                        ("required_evidence_refs", truth.required_evidence_refs),
                    ),
                ),
                ExplorerEvaluatorAnnotationV1(
                    id=framed_identifier("annotation", action_event_id, "binding"),
                    source_action_event_id=action_event_id,
                    target_id=target_id,
                    kind="canonical_binding",
                    label="Canonical identity binding",
                    value="Evaluator-only identity roles",
                    properties=build_properties(
                        ("originating_principal_id", binding.originating_principal_id),
                        ("logical_agent_id", binding.logical_agent_id),
                        ("runtime_id", binding.runtime_id),
                        ("runtime_principal_id", binding.runtime_principal_id),
                        ("credential_subject_id", binding.credential_subject_id),
                        ("attributed_actor_id", binding.attributed_actor_id),
                        ("accountable_owner_chain", binding.accountable_owner_chain),
                    ),
                ),
                ExplorerEvaluatorAnnotationV1(
                    id=framed_identifier("annotation", action_event_id, "case"),
                    source_action_event_id=action_event_id,
                    target_id=target_id,
                    kind="case_kind",
                    label="Evaluator case",
                    value=case.kind.value,
                ),
            )
        )
    return tuple(annotations)
