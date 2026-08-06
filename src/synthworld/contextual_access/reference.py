"""Deterministic contextual-access smoke pack over the fixed enterprise universe."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from synthworld.contextual_access.common import (
    contextual_profile_namespace,
    stable_contextual_fact_key,
    stable_contextual_id,
)
from synthworld.contextual_access.models import (
    BusinessJustificationContextV1,
    BusinessJustificationKind,
    CaseAssignmentContextV1,
    CaseAssignmentState,
    ContextDeliveryAttemptV1,
    ContextualAccessConfigV1,
    ContextualAccessEvaluatorV1,
    ContextualAccessEventV1,
    ContextualAccessPublicV1,
    ContextualAccessRequestV1,
    ContextualCaseKind,
    ContextualCaseLabelV1,
    ContextualFactKind,
    ContextualFactMappingProfileV1,
    ContextualFactMappingV1,
    ContextualFactRemovedV1,
    ContextualFactUpsertedV1,
    ContextualMappingKind,
    ContextualObjectKind,
    ContextualObjectRegistryV1,
    ContextualObjectV1,
    ContextualPolicyV1,
    ContextualRuleComposition,
    ContextualRuleEffect,
    ContextualRuleV1,
    DevicePosture,
    DevicePostureContextV1,
    DevicePostureIsV1,
    HasActiveCaseAssignmentV1,
    HasValidBusinessJustificationV1,
    IsOnCallV1,
    OnCallContextV1,
    OnCallState,
    RiskAtMostV1,
    RiskLevel,
    RiskSignalContextV1,
)
from synthworld.contextual_access.projection import (
    compile_contextual_access_truth,
    project_contextual_access_public,
)
from synthworld.enterprise.authorization.reference import (
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    AccessAtomV1,
    EnterpriseIdentityAccessUniverseV1,
)

REFERENCE_CONTEXTUAL_ACCESS_SEED = 20_260_804
REFERENCE_CONTEXTUAL_UNIVERSE_SHA256 = (
    "b4eae423689ede98d98858cae004f98d07fa5b0ac4774858500a4ba257946f4a"
)


@dataclass(frozen=True, slots=True)
class ReferenceContextualAccessV1:
    config: ContextualAccessConfigV1
    public: ContextualAccessPublicV1
    evaluator: ContextualAccessEvaluatorV1


@dataclass(frozen=True, slots=True)
class _CaseDraft:
    kind: ContextualCaseKind
    atom: AccessAtomV1
    request_tick: int
    device_id: str
    transition_event_ids: tuple[str, ...]


def reference_contextual_access(
    *, seed: int = REFERENCE_CONTEXTUAL_ACCESS_SEED
) -> ReferenceContextualAccessV1:
    """Generate the contextual smoke pack over the pinned enterprise reference."""

    config = ContextualAccessConfigV1(seed=seed)
    authorization = reference_enterprise_authorization_inputs()
    universe = authorization.rbac.universe_result.public_universe
    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    if universe_digest.value != REFERENCE_CONTEXTUAL_UNIVERSE_SHA256:
        raise RuntimeError("contextual reference enterprise universe changed")
    return generate_contextual_access_smoke(universe=universe, config=config)


def generate_contextual_access_smoke(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    config: ContextualAccessConfigV1,
) -> ReferenceContextualAccessV1:
    """Generate one case per closed smoke kind without adding an access atom."""

    _require_reference_config(config)
    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    namespace = contextual_profile_namespace(
        universe_sha256=universe_digest.value,
        seed=config.seed,
    )
    registry = _registry(config, universe, namespace)
    mapping_profile = _mapping_profile(namespace)
    policies = _policies(registry, universe, namespace)
    atoms = _principal_atoms(universe)
    if len(atoms) < len(ContextualCaseKind):
        raise RuntimeError("contextual reference has too few principal access atoms")
    selected = atoms[: len(ContextualCaseKind)]
    objects = _objects_by_kind(registry)
    devices_by_subject: dict[str, int] = defaultdict(int)

    def device_for(atom: AccessAtomV1) -> str:
        offset = devices_by_subject[atom.subject_id]
        devices_by_subject[atom.subject_id] += 1
        return objects[ContextualObjectKind.DEVICE][offset].id

    initial: list[
        CaseAssignmentContextV1
        | OnCallContextV1
        | DevicePostureContextV1
        | RiskSignalContextV1
        | BusinessJustificationContextV1
    ] = []
    events: list[ContextualAccessEventV1] = []
    drafts: list[_CaseDraft] = []

    def add_draft(
        kind: ContextualCaseKind,
        atom: AccessAtomV1,
        *,
        request_tick: int,
        transition_events: tuple[ContextualAccessEventV1, ...] = (),
    ) -> str:
        device_id = device_for(atom)
        events.extend(transition_events)
        drafts.append(
            _CaseDraft(
                kind=kind,
                atom=atom,
                request_tick=request_tick,
                device_id=device_id,
                transition_event_ids=tuple(item.id for item in transition_events),
            )
        )
        return device_id

    # Static allow: one active closed-world relationship.
    static_allow = _assignment(
        namespace,
        selected[0],
        objects[ContextualObjectKind.WORK_ITEM][0].id,
    )
    initial.append(static_allow)
    add_draft(ContextualCaseKind.STATIC_ALLOW, selected[0], request_tick=1)

    # Static deny: an allow and a deny rule both match; deny-overrides is observable.
    static_deny_assignment = _assignment(
        namespace,
        selected[1],
        objects[ContextualObjectKind.WORK_ITEM][1].id,
    )
    static_deny_scope = _on_call(
        namespace,
        selected[1],
        objects[ContextualObjectKind.DUTY_SCOPE][1].id,
    )
    initial.extend((static_deny_assignment, static_deny_scope))
    add_draft(ContextualCaseKind.STATIC_DENY, selected[1], request_tick=1)

    assignment = _assignment(
        namespace,
        selected[2],
        objects[ContextualObjectKind.WORK_ITEM][2].id,
    )
    initial.append(assignment)
    assignment_removed = _event(
        namespace,
        _assignment(
            namespace,
            selected[2],
            objects[ContextualObjectKind.WORK_ITEM][2].id,
            revision=1,
            tick=5,
            state=CaseAssignmentState.UNASSIGNED,
            tombstone=True,
        ),
        removed=True,
    )
    add_draft(
        ContextualCaseKind.ASSIGNMENT_REMOVED,
        selected[2],
        request_tick=6,
        transition_events=(assignment_removed,),
    )

    on_call = _on_call(
        namespace,
        selected[3],
        objects[ContextualObjectKind.DUTY_SCOPE][0].id,
        valid_until_tick=5,
    )
    initial.append(on_call)
    add_draft(ContextualCaseKind.ON_CALL_EXPIRED, selected[3], request_tick=5)

    degraded_device_id = device_for(selected[4])
    devices_by_subject[selected[4].subject_id] -= 1
    device = _device(
        namespace,
        selected[4],
        degraded_device_id,
        posture=DevicePosture.TRUSTED,
    )
    initial.append(device)
    degraded = _event(
        namespace,
        _device(
            namespace,
            selected[4],
            degraded_device_id,
            posture=DevicePosture.NONCOMPLIANT,
            revision=1,
            tick=5,
        ),
    )
    add_draft(
        ContextualCaseKind.DEVICE_DEGRADED,
        selected[4],
        request_tick=6,
        transition_events=(degraded,),
    )

    risk = _risk(
        namespace,
        selected[5],
        objects[ContextualObjectKind.SIGNAL_SOURCE][0].id,
        level=RiskLevel.LOW,
    )
    initial.append(risk)
    elevated = _event(
        namespace,
        _risk(
            namespace,
            selected[5],
            objects[ContextualObjectKind.SIGNAL_SOURCE][0].id,
            level=RiskLevel.HIGH,
            revision=1,
            tick=5,
        ),
    )
    add_draft(
        ContextualCaseKind.RISK_ELEVATED,
        selected[5],
        request_tick=6,
        transition_events=(elevated,),
    )

    justification = _justification(
        namespace,
        selected[6],
        objects[ContextualObjectKind.APPROVAL_EVIDENCE][0].id,
        valid_until_tick=5,
    )
    initial.append(justification)
    add_draft(
        ContextualCaseKind.JUSTIFICATION_EXPIRED,
        selected[6],
        request_tick=5,
    )

    delayed_assignment = _assignment(
        namespace,
        selected[7],
        objects[ContextualObjectKind.WORK_ITEM][0].id,
    )
    initial.append(delayed_assignment)
    delayed = _event(
        namespace,
        _assignment(
            namespace,
            selected[7],
            objects[ContextualObjectKind.WORK_ITEM][0].id,
            revision=1,
            tick=5,
            state=CaseAssignmentState.UNASSIGNED,
            tombstone=True,
        ),
        removed=True,
    )
    add_draft(
        ContextualCaseKind.DELAYED_DELIVERY,
        selected[7],
        request_tick=6,
        transition_events=(delayed,),
    )

    duplicate_device_id = device_for(selected[8])
    devices_by_subject[selected[8].subject_id] -= 1
    duplicate_device = _device(
        namespace,
        selected[8],
        duplicate_device_id,
        posture=DevicePosture.TRUSTED,
    )
    initial.append(duplicate_device)
    duplicate_event = _event(
        namespace,
        _device(
            namespace,
            selected[8],
            duplicate_device_id,
            posture=DevicePosture.NONCOMPLIANT,
            revision=1,
            tick=5,
        ),
    )
    add_draft(
        ContextualCaseKind.DUPLICATE_DELIVERY,
        selected[8],
        request_tick=7,
        transition_events=(duplicate_event,),
    )

    out_of_order_risk = _risk(
        namespace,
        selected[9],
        objects[ContextualObjectKind.SIGNAL_SOURCE][1].id,
        level=RiskLevel.LOW,
    )
    initial.append(out_of_order_risk)
    out_high = _event(
        namespace,
        _risk(
            namespace,
            selected[9],
            objects[ContextualObjectKind.SIGNAL_SOURCE][1].id,
            level=RiskLevel.HIGH,
            revision=1,
            tick=5,
        ),
    )
    out_low = _event(
        namespace,
        _risk(
            namespace,
            selected[9],
            objects[ContextualObjectKind.SIGNAL_SOURCE][1].id,
            level=RiskLevel.LOW,
            revision=2,
            tick=6,
        ),
    )
    add_draft(
        ContextualCaseKind.OUT_OF_ORDER_DELIVERY,
        selected[9],
        request_tick=8,
        transition_events=(out_high, out_low),
    )

    canonical_events = tuple(
        sorted(events, key=lambda item: (item.effective_tick, item.id))
    )
    attempts = _delivery_attempts(
        namespace,
        canonical_events,
        delayed_event_id=delayed.id,
        duplicate_event_id=duplicate_event.id,
        out_of_order_event_ids=(out_high.id, out_low.id),
    )
    requests, labels = _requests_and_labels(namespace, drafts)
    public = project_contextual_access_public(
        config=config,
        universe=universe,
        registry=registry,
        mapping_profile=mapping_profile,
        policies=policies,
        initial_facts=tuple(initial),
        events=canonical_events,
        delivery_attempts=attempts,
        requests=requests,
    )
    evaluator = compile_contextual_access_truth(public=public, case_labels=labels)
    _require_case_inventory(evaluator)
    return ReferenceContextualAccessV1(
        config=config,
        public=public,
        evaluator=evaluator,
    )


def _registry(
    config: ContextualAccessConfigV1,
    universe: EnterpriseIdentityAccessUniverseV1,
    namespace: UUID,
) -> ContextualObjectRegistryV1:
    organisation = universe.organisations[0]
    counts = {
        ContextualObjectKind.WORK_ITEM: config.object_counts.work_items,
        ContextualObjectKind.DUTY_SCOPE: config.object_counts.duty_scopes,
        ContextualObjectKind.DEVICE: config.object_counts.devices,
        ContextualObjectKind.SIGNAL_SOURCE: config.object_counts.signal_sources,
        ContextualObjectKind.APPROVAL_EVIDENCE: (
            config.object_counts.approval_evidence
        ),
    }
    objects = tuple(
        ContextualObjectV1(
            id=stable_contextual_id(namespace, f"registry-{kind.value}", str(slot)),
            kind=kind,
            tenant_id=organisation.tenant_id,
            organisation_id=organisation.organisation_id,
            display_label=(
                f"Example {kind.value.replace('_', ' ').title()} {slot + 1:03d}"
            ),
        )
        for kind in ContextualObjectKind
        for slot in range(counts[kind])
    )
    return ContextualObjectRegistryV1(objects=objects)


def _mapping_profile(namespace: UUID) -> ContextualFactMappingProfileV1:
    return ContextualFactMappingProfileV1(
        profile_id=stable_contextual_id(namespace, "fact-mapping", "native-v1"),
        mappings=(
            ContextualFactMappingV1(
                fact_type=ContextualFactKind.CASE_ASSIGNMENT,
                mapping_kind=ContextualMappingKind.RELATIONSHIP_PREDICATE,
                nist_category=None,
                relationship_predicate="subject_assigned_to_asset_work_item",
            ),
            ContextualFactMappingV1(
                fact_type=ContextualFactKind.ON_CALL,
                mapping_kind=ContextualMappingKind.SUBJECT_ATTRIBUTE,
                nist_category="subject",
                relationship_predicate=None,
            ),
            ContextualFactMappingV1(
                fact_type=ContextualFactKind.DEVICE_POSTURE,
                mapping_kind=ContextualMappingKind.ENVIRONMENT_ATTRIBUTE,
                nist_category="environment",
                relationship_predicate=None,
            ),
            ContextualFactMappingV1(
                fact_type=ContextualFactKind.RISK_SIGNAL,
                mapping_kind=ContextualMappingKind.ENVIRONMENT_ATTRIBUTE,
                nist_category="environment",
                relationship_predicate=None,
            ),
            ContextualFactMappingV1(
                fact_type=ContextualFactKind.BUSINESS_JUSTIFICATION,
                mapping_kind=ContextualMappingKind.RELATIONSHIP_PREDICATE,
                nist_category=None,
                relationship_predicate="subject_has_justification_for_action",
            ),
        ),
    )


def _policies(
    registry: ContextualObjectRegistryV1,
    universe: EnterpriseIdentityAccessUniverseV1,
    namespace: UUID,
) -> tuple[ContextualPolicyV1, ...]:
    objects = _objects_by_kind(registry)
    duty_allow = objects[ContextualObjectKind.DUTY_SCOPE][0].id
    duty_deny = objects[ContextualObjectKind.DUTY_SCOPE][1].id
    risk_source = objects[ContextualObjectKind.SIGNAL_SOURCE][0].id
    reordered_risk_source = objects[ContextualObjectKind.SIGNAL_SOURCE][1].id

    def predicate_id(template: str) -> str:
        return stable_contextual_id(namespace, "predicate", template)

    def rule(
        template: str,
        effect: ContextualRuleEffect,
        composition: ContextualRuleComposition,
        predicates: tuple[
            HasActiveCaseAssignmentV1
            | HasValidBusinessJustificationV1
            | IsOnCallV1
            | DevicePostureIsV1
            | RiskAtMostV1,
            ...,
        ],
    ) -> ContextualRuleV1:
        return ContextualRuleV1(
            rule_id=stable_contextual_id(namespace, "rule", template),
            effect=effect,
            composition=composition,
            predicates=predicates,
        )

    allow_rules = (
        rule(
            "assignment-or-justification",
            ContextualRuleEffect.ALLOW,
            ContextualRuleComposition.ANY,
            (
                HasActiveCaseAssignmentV1(predicate_id=predicate_id("has-assignment")),
                HasValidBusinessJustificationV1(
                    predicate_id=predicate_id("has-emergency-justification"),
                    justification_kind=BusinessJustificationKind.EMERGENCY_ACCESS,
                ),
            ),
        ),
        rule(
            "on-call",
            ContextualRuleEffect.ALLOW,
            ContextualRuleComposition.ALL,
            (
                IsOnCallV1(
                    predicate_id=predicate_id("is-on-call"),
                    duty_scope_id=duty_allow,
                ),
            ),
        ),
        rule(
            "trusted-device",
            ContextualRuleEffect.ALLOW,
            ContextualRuleComposition.ALL,
            (
                DevicePostureIsV1(
                    predicate_id=predicate_id("trusted-device"),
                    required_posture=DevicePosture.TRUSTED,
                ),
            ),
        ),
        rule(
            "risk-at-most-medium",
            ContextualRuleEffect.ALLOW,
            ContextualRuleComposition.ALL,
            (
                RiskAtMostV1(
                    predicate_id=predicate_id("risk-at-most-medium"),
                    signal_source_id=risk_source,
                    maximum_level=RiskLevel.MEDIUM,
                ),
            ),
        ),
        rule(
            "reordered-risk-at-most-medium",
            ContextualRuleEffect.ALLOW,
            ContextualRuleComposition.ALL,
            (
                RiskAtMostV1(
                    predicate_id=predicate_id("reordered-risk-at-most-medium"),
                    signal_source_id=reordered_risk_source,
                    maximum_level=RiskLevel.MEDIUM,
                ),
            ),
        ),
    )
    targets = tuple(
        item.authorization_target_id for item in universe.authorization_targets
    )
    allow_policy = ContextualPolicyV1(
        policy_id=stable_contextual_id(namespace, "policy", "allow-context"),
        policy_version_id=stable_contextual_id(
            namespace, "policy-version", "allow-context-v1"
        ),
        target_handles=targets,
        actions=("read",),
        rules=allow_rules,
    )
    deny_policy = ContextualPolicyV1(
        policy_id=stable_contextual_id(namespace, "policy", "deny-on-duty"),
        policy_version_id=stable_contextual_id(
            namespace, "policy-version", "deny-on-duty-v1"
        ),
        target_handles=targets,
        actions=("read",),
        rules=(
            rule(
                "deny-special-duty",
                ContextualRuleEffect.DENY,
                ContextualRuleComposition.ALL,
                (
                    IsOnCallV1(
                        predicate_id=predicate_id("is-special-duty"),
                        duty_scope_id=duty_deny,
                    ),
                ),
            ),
        ),
    )
    return allow_policy, deny_policy


def _principal_atoms(
    universe: EnterpriseIdentityAccessUniverseV1,
) -> tuple[AccessAtomV1, ...]:
    principal_ids = {item.principal_id for item in universe.principals}
    by_subject: dict[str, list[AccessAtomV1]] = defaultdict(list)
    for item in universe.access_atoms:
        if item.subject_id in principal_ids and item.action == "read":
            by_subject[item.subject_id].append(item)
    groups = tuple(
        tuple(sorted(items, key=lambda item: item.access_atom_id))
        for _, items in sorted(by_subject.items())
    )
    if len(groups) < 6 or any(len(group) < 2 for group in groups[:5]):
        raise RuntimeError("contextual reference atom pairing changed")
    # Pair only cases whose active facts cannot contaminate one another. On-call and
    # risk predicates are subject-scoped, while assignments and justifications also
    # bind the requested asset and device posture binds the explicit request device.
    return (
        groups[0][0],  # static allow
        groups[1][0],  # static deny (paired atom intentionally unused)
        groups[2][0],  # assignment removed
        groups[3][0],  # on-call expired
        groups[3][1],  # device degraded after the paired on-call expires
        groups[4][0],  # risk elevated
        groups[5][0],  # justification expired (paired atom intentionally unused)
        groups[2][1],  # delayed assignment removal
        groups[4][1],  # duplicate device delivery after risk elevation
        groups[0][1],  # out-of-order risk; paired static case is also an allow
    )


def _objects_by_kind(
    registry: ContextualObjectRegistryV1,
) -> dict[ContextualObjectKind, tuple[ContextualObjectV1, ...]]:
    return {
        kind: tuple(item for item in registry.objects if item.kind is kind)
        for kind in ContextualObjectKind
    }


def _assignment(
    namespace: UUID,
    atom: AccessAtomV1,
    work_item_id: str,
    *,
    revision: int = 0,
    tick: int = 0,
    state: CaseAssignmentState = CaseAssignmentState.ASSIGNED,
    tombstone: bool = False,
) -> CaseAssignmentContextV1:
    key = stable_contextual_fact_key(
        ContextualFactKind.CASE_ASSIGNMENT.value,
        atom.subject_id,
        work_item_id,
        atom.authorization_target_id,
    )
    return CaseAssignmentContextV1(
        fact_id=_fact_id(namespace, key, revision),
        fact_key=key,
        revision=revision,
        tombstone=tombstone,
        subject_id=atom.subject_id,
        work_item_id=work_item_id,
        asset_id=atom.authorization_target_id,
        assignment_state=state,
        valid_from_tick=tick,
    )


def _on_call(
    namespace: UUID,
    atom: AccessAtomV1,
    duty_scope_id: str,
    *,
    revision: int = 0,
    tick: int = 0,
    state: OnCallState = OnCallState.ON_CALL,
    valid_until_tick: int | None = None,
    tombstone: bool = False,
) -> OnCallContextV1:
    key = stable_contextual_fact_key(
        ContextualFactKind.ON_CALL.value,
        atom.subject_id,
        duty_scope_id,
    )
    return OnCallContextV1(
        fact_id=_fact_id(namespace, key, revision),
        fact_key=key,
        revision=revision,
        tombstone=tombstone,
        subject_id=atom.subject_id,
        duty_scope_id=duty_scope_id,
        duty_state=state,
        valid_from_tick=tick,
        valid_until_tick=valid_until_tick,
    )


def _device(
    namespace: UUID,
    atom: AccessAtomV1,
    device_id: str,
    *,
    posture: DevicePosture,
    revision: int = 0,
    tick: int = 0,
    expires_at_tick: int | None = None,
    tombstone: bool = False,
) -> DevicePostureContextV1:
    key = stable_contextual_fact_key(
        ContextualFactKind.DEVICE_POSTURE.value,
        atom.subject_id,
        device_id,
    )
    return DevicePostureContextV1(
        fact_id=_fact_id(namespace, key, revision),
        fact_key=key,
        revision=revision,
        tombstone=tombstone,
        subject_id=atom.subject_id,
        device_id=device_id,
        posture=posture,
        observed_at_tick=tick,
        expires_at_tick=expires_at_tick,
    )


def _risk(
    namespace: UUID,
    atom: AccessAtomV1,
    signal_source_id: str,
    *,
    level: RiskLevel,
    revision: int = 0,
    tick: int = 0,
    expires_at_tick: int | None = None,
    tombstone: bool = False,
) -> RiskSignalContextV1:
    key = stable_contextual_fact_key(
        ContextualFactKind.RISK_SIGNAL.value,
        atom.subject_id,
        signal_source_id,
    )
    return RiskSignalContextV1(
        fact_id=_fact_id(namespace, key, revision),
        fact_key=key,
        revision=revision,
        tombstone=tombstone,
        subject_id=atom.subject_id,
        signal_source_id=signal_source_id,
        risk_level=level,
        effective_from_tick=tick,
        expires_at_tick=expires_at_tick,
    )


def _justification(
    namespace: UUID,
    atom: AccessAtomV1,
    approval_evidence_id: str,
    *,
    revision: int = 0,
    tick: int = 0,
    valid_until_tick: int | None = None,
    tombstone: bool = False,
) -> BusinessJustificationContextV1:
    kind = BusinessJustificationKind.EMERGENCY_ACCESS
    key = stable_contextual_fact_key(
        ContextualFactKind.BUSINESS_JUSTIFICATION.value,
        atom.subject_id,
        atom.authorization_target_id,
        atom.action,
        kind.value,
        approval_evidence_id,
    )
    return BusinessJustificationContextV1(
        fact_id=_fact_id(namespace, key, revision),
        fact_key=key,
        revision=revision,
        tombstone=tombstone,
        subject_id=atom.subject_id,
        asset_id=atom.authorization_target_id,
        action=atom.action,
        justification_kind=kind,
        approval_evidence_id=approval_evidence_id,
        valid_from_tick=tick,
        valid_until_tick=valid_until_tick,
    )


def _fact_id(namespace: UUID, fact_key: str, revision: int) -> str:
    return stable_contextual_id(namespace, "fact", fact_key, str(revision))


def _event(
    namespace: UUID,
    fact: CaseAssignmentContextV1
    | OnCallContextV1
    | DevicePostureContextV1
    | RiskSignalContextV1
    | BusinessJustificationContextV1,
    *,
    removed: bool = False,
) -> ContextualAccessEventV1:
    tick = (
        fact.observed_at_tick
        if isinstance(fact, DevicePostureContextV1)
        else fact.effective_from_tick
        if isinstance(fact, RiskSignalContextV1)
        else fact.valid_from_tick
    )
    payload = (
        ContextualFactRemovedV1(fact=fact)
        if removed
        else ContextualFactUpsertedV1(fact=fact)
    )
    return ContextualAccessEventV1(
        id=stable_contextual_id(
            namespace,
            "event",
            fact.fact_id,
            payload.event_type,
            str(tick),
        ),
        effective_tick=tick,
        payload=payload,
    )


def _delivery_attempts(
    namespace: UUID,
    events: tuple[ContextualAccessEventV1, ...],
    *,
    delayed_event_id: str,
    duplicate_event_id: str,
    out_of_order_event_ids: tuple[str, str],
) -> tuple[ContextDeliveryAttemptV1, ...]:
    high_id, low_id = out_of_order_event_ids
    planned: list[tuple[str, int, int, int]] = []
    for event in events:
        if event.id == delayed_event_id:
            planned.append((event.id, 0, 10, 0))
        elif event.id == duplicate_event_id:
            planned.extend(
                (
                    (event.id, 0, event.effective_tick, 0),
                    (event.id, 1, event.effective_tick + 1, 0),
                )
            )
        elif event.id == high_id:
            planned.append((event.id, 0, 7, 1))
        elif event.id == low_id:
            planned.append((event.id, 0, 7, 0))
        else:
            planned.append((event.id, 0, event.effective_tick, 0))
    by_tick: dict[int, list[tuple[str, int, int, int]]] = defaultdict(list)
    for item in planned:
        by_tick[item[2]].append(item)
    attempts: list[ContextDeliveryAttemptV1] = []
    for delivery_tick in sorted(by_tick):
        ordered = sorted(
            by_tick[delivery_tick],
            key=lambda item: (item[3], item[0], item[1]),
        )
        for delivery_order, (event_id, attempt_index, _, _) in enumerate(ordered):
            attempts.append(
                ContextDeliveryAttemptV1(
                    attempt_id=stable_contextual_id(
                        namespace,
                        "delivery-attempt",
                        event_id,
                        str(attempt_index),
                        str(delivery_tick),
                    ),
                    event_id=event_id,
                    attempt_index=attempt_index,
                    delivery_tick=delivery_tick,
                    delivery_order=delivery_order,
                )
            )
    return tuple(attempts)


def _requests_and_labels(
    namespace: UUID,
    drafts: list[_CaseDraft],
) -> tuple[
    tuple[ContextualAccessRequestV1, ...],
    tuple[ContextualCaseLabelV1, ...],
]:
    requests: list[ContextualAccessRequestV1] = []
    labels: list[ContextualCaseLabelV1] = []
    for index, draft in enumerate(drafts):
        request_id = stable_contextual_id(
            namespace,
            "request",
            draft.kind.value,
            draft.atom.access_atom_id,
            str(draft.request_tick),
        )
        requests.append(
            ContextualAccessRequestV1(
                request_id=request_id,
                request_index=index,
                request_tick=draft.request_tick,
                subject_id=draft.atom.subject_id,
                asset_id=draft.atom.authorization_target_id,
                action=draft.atom.action,
                access_atom_id=draft.atom.access_atom_id,
                device_id=draft.device_id,
            )
        )
        labels.append(
            ContextualCaseLabelV1(
                case_id=stable_contextual_id(
                    namespace,
                    "case",
                    draft.kind.value,
                    request_id,
                ),
                request_id=request_id,
                kind=draft.kind,
                transition_event_ids=draft.transition_event_ids,
            )
        )
    return tuple(requests), tuple(labels)


def _require_reference_config(config: ContextualAccessConfigV1) -> None:
    minima = (
        config.object_counts.work_items >= 3,
        config.object_counts.duty_scopes >= 2,
        config.object_counts.devices >= 2,
        config.object_counts.signal_sources >= 2,
        config.object_counts.approval_evidence >= 1,
    )
    if (
        set(config.enabled_fact_kinds) != set(ContextualFactKind)
        or set(config.enabled_case_kinds) != set(ContextualCaseKind)
        or config.cases_per_kind != 1
        or not all(minima)
    ):
        raise ValueError(
            "reference contextual smoke requires every kind once and minimum objects"
        )


def _require_case_inventory(evaluator: ContextualAccessEvaluatorV1) -> None:
    actual = {item.kind for item in evaluator.truth.case_labels}
    expected = set(ContextualCaseKind)
    if actual != expected or len(evaluator.truth.case_labels) != len(expected):
        raise RuntimeError("contextual smoke case inventory is incomplete")
    stale = {item.request_id for item in evaluator.truth.cases if item.stale_context}
    delayed = {
        item.request_id
        for item in evaluator.truth.case_labels
        if item.kind is ContextualCaseKind.DELAYED_DELIVERY
    }
    if stale != delayed:
        raise RuntimeError("contextual stale-context inventory is not discriminating")


__all__ = [
    "REFERENCE_CONTEXTUAL_ACCESS_SEED",
    "REFERENCE_CONTEXTUAL_UNIVERSE_SHA256",
    "ReferenceContextualAccessV1",
    "generate_contextual_access_smoke",
    "reference_contextual_access",
]
