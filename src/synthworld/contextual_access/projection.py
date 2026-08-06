"""Public projection and evaluator compilation for contextual-access v1."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from synthworld.contextual_access.models import (
    BusinessJustificationContextV1,
    CaseAssignmentContextV1,
    ContextDeliveryAttemptV1,
    ContextualAccessBenchmarkV1,
    ContextualAccessCaseTruthV1,
    ContextualAccessConfigV1,
    ContextualAccessEvaluatorV1,
    ContextualAccessEventV1,
    ContextualAccessPublicV1,
    ContextualAccessRequestV1,
    ContextualAccessTruthV1,
    ContextualCaseLabelV1,
    ContextualFactMappingProfileV1,
    ContextualFactV1,
    ContextualObjectKind,
    ContextualObjectRegistryV1,
    ContextualObjectV1,
    ContextualPolicyV1,
    ContextualRuleV1,
    DevicePostureContextV1,
    DevicePostureIsV1,
    IsOnCallV1,
    OnCallContextV1,
    RiskAtMostV1,
    RiskSignalContextV1,
    canonical_model_tuple_bytes,
)
from synthworld.contextual_access.policy import evaluate_contextual_request
from synthworld.contextual_access.replay import (
    ContextualReplayError,
    active_contextual_facts,
    contextual_checkpoints,
    materialize_contextual_state,
    presented_contextual_state,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseIdentityAccessUniverseV1
from synthworld.temporal_schedule import (
    compile_contextual_temporal_schedule,
    validate_contextual_temporal_schedule,
)


class ContextualAccessIntegrityError(ValueError):
    """Raised when contextual public or evaluator bindings are inconsistent."""


def project_contextual_access_public(
    *,
    config: ContextualAccessConfigV1,
    universe: EnterpriseIdentityAccessUniverseV1,
    registry: ContextualObjectRegistryV1,
    mapping_profile: ContextualFactMappingProfileV1,
    policies: tuple[ContextualPolicyV1, ...],
    initial_facts: tuple[ContextualFactV1, ...],
    events: tuple[ContextualAccessEventV1, ...],
    delivery_attempts: tuple[ContextDeliveryAttemptV1, ...],
    requests: tuple[ContextualAccessRequestV1, ...],
) -> ContextualAccessPublicV1:
    """Build public input field by field without evaluator outcomes or labels."""

    policies = tuple(sorted(policies, key=lambda item: item.policy_id))
    initial_facts = tuple(sorted(initial_facts, key=lambda item: item.fact_key))
    events = tuple(sorted(events, key=lambda item: (item.effective_tick, item.id)))
    delivery_attempts = tuple(
        sorted(
            delivery_attempts,
            key=lambda item: (
                item.delivery_tick,
                item.delivery_order,
                item.event_id,
                item.attempt_index,
            ),
        )
    )
    requests = tuple(
        sorted(requests, key=lambda item: (item.request_index, item.request_id))
    )
    _enforce_limits(
        config=config,
        registry=registry,
        policies=policies,
        initial_facts=initial_facts,
        events=events,
        delivery_attempts=delivery_attempts,
        requests=requests,
    )
    configured_facts = set(config.enabled_fact_kinds)
    actual_facts = {
        fact.fact_type
        for fact in (
            *initial_facts,
            *(event.payload.fact for event in events),
        )
    }
    if not actual_facts <= configured_facts:
        raise ContextualAccessIntegrityError(
            "contextual facts include a kind disabled by configuration"
        )
    schedule = compile_contextual_temporal_schedule(
        events=events,
        event_schedule_version=config.event_schedule_version,
    )
    atom_bytes = canonical_model_tuple_bytes(universe.access_atoms)
    benchmark = ContextualAccessBenchmarkV1(
        seed=config.seed,
        tier=config.tier,
        event_schedule_version=config.event_schedule_version,
        config_digest=synthetic_digest(canonical_json_bytes(config)),
        identity_access_universe_digest=synthetic_digest(
            canonical_json_bytes(universe)
        ),
        access_atom_digest=synthetic_digest(atom_bytes),
        registry_digest=synthetic_digest(canonical_json_bytes(registry)),
        mapping_profile_digest=synthetic_digest(canonical_json_bytes(mapping_profile)),
        policy_digest=synthetic_digest(canonical_model_tuple_bytes(policies)),
        initial_fact_digest=synthetic_digest(
            canonical_model_tuple_bytes(initial_facts)
        ),
        event_digest=synthetic_digest(canonical_model_tuple_bytes(events)),
        schedule_digest=synthetic_digest(canonical_model_tuple_bytes(schedule)),
        delivery_attempt_digest=synthetic_digest(
            canonical_model_tuple_bytes(delivery_attempts)
        ),
        request_digest=synthetic_digest(canonical_model_tuple_bytes(requests)),
    )
    public = ContextualAccessPublicV1(
        universe=universe,
        registry=registry,
        mapping_profile=mapping_profile,
        policies=policies,
        initial_facts=initial_facts,
        events=events,
        schedule=schedule,
        delivery_attempts=delivery_attempts,
        requests=requests,
        benchmark=benchmark,
    )
    validate_contextual_access_public(public)
    return public


def compile_contextual_access_truth(
    *,
    public: ContextualAccessPublicV1,
    case_labels: tuple[ContextualCaseLabelV1, ...],
) -> ContextualAccessEvaluatorV1:
    """Compile canonical and presented-feed decisions from exact public inputs."""

    validate_contextual_access_public(public)
    labels = {item.request_id: item for item in case_labels}
    request_ids = {item.request_id for item in public.requests}
    if set(labels) != request_ids:
        raise ContextualAccessIntegrityError(
            "contextual case labels must cover every public request exactly once"
        )
    event_ids = {item.id for item in public.events}
    if any(not set(item.transition_event_ids) <= event_ids for item in case_labels):
        raise ContextualAccessIntegrityError(
            "contextual case label references an unknown transition event"
        )
    cases: list[ContextualAccessCaseTruthV1] = []
    for request in public.requests:
        canonical_state = materialize_contextual_state(
            public.initial_facts,
            public.events,
            as_of_tick=request.request_tick,
        )
        canonical = evaluate_contextual_request(
            active_facts=active_contextual_facts(
                canonical_state,
                at_tick=request.request_tick,
            ),
            policies=public.policies,
            request=request,
        )
        presented_state = presented_contextual_state(
            public.initial_facts,
            public.events,
            public.delivery_attempts,
            as_of_tick=request.request_tick,
        )
        presented = evaluate_contextual_request(
            active_facts=active_contextual_facts(
                presented_state,
                at_tick=request.request_tick,
            ),
            policies=public.policies,
            request=request,
        )
        label = labels[request.request_id]
        cases.append(
            ContextualAccessCaseTruthV1(
                case_id=label.case_id,
                request_id=request.request_id,
                canonical=canonical,
                presented_feed=presented,
                stale_context=canonical.decision is not presented.decision,
                required_evidence_refs=(f"contextual-evidence:{request.request_id}",),
            )
        )
    public_digest = synthetic_digest(canonical_json_bytes(public))
    truth = ContextualAccessTruthV1(
        public_digest=public_digest,
        benchmark_digest=synthetic_digest(canonical_json_bytes(public.benchmark)),
        checkpoints=contextual_checkpoints(public.initial_facts, public.events),
        cases=tuple(cases),
        case_labels=case_labels,
    )
    return ContextualAccessEvaluatorV1(
        public_digest=public_digest,
        truth=truth,
    )


def validate_contextual_access_public(public: ContextualAccessPublicV1) -> None:
    """Validate references and replay without reading evaluator artifacts."""

    try:
        validate_contextual_temporal_schedule(
            events=public.events,
            envelopes=public.schedule,
            event_schedule_version=public.benchmark.event_schedule_version,
        )
        materialize_contextual_state(public.initial_facts, public.events)
    except (ValueError, ContextualReplayError) as error:
        raise ContextualAccessIntegrityError(
            "contextual schedule or fact history is invalid"
        ) from error
    _validate_delivery_attempts(public)
    _validate_registry(public)
    _validate_facts(public)
    _validate_policies(public)
    _validate_requests(public)


def _validate_registry(public: ContextualAccessPublicV1) -> None:
    tenants = {item.tenant_id for item in public.universe.tenants}
    organisations = {
        item.organisation_id: item.tenant_id for item in public.universe.organisations
    }
    for item in public.registry.objects:
        if item.tenant_id not in tenants:
            raise ContextualAccessIntegrityError(
                "contextual registry object references an unknown tenant"
            )
        if organisations.get(item.organisation_id) != item.tenant_id:
            raise ContextualAccessIntegrityError(
                "contextual registry organization does not belong to its tenant"
            )


def _validate_facts(public: ContextualAccessPublicV1) -> None:
    principals = {item.principal_id: item for item in public.universe.principals}
    targets = {
        item.authorization_target_id: item
        for item in public.universe.authorization_targets
    }
    registry = {item.id: item for item in public.registry.objects}
    facts = (
        *public.initial_facts,
        *(event.payload.fact for event in public.events),
    )
    for fact in facts:
        subject = principals.get(fact.subject_id)
        if subject is None:
            raise ContextualAccessIntegrityError(
                "contextual fact references an unknown principal subject"
            )
        object_ids: tuple[tuple[str, ContextualObjectKind], ...]
        asset_id: str | None = None
        if isinstance(fact, CaseAssignmentContextV1):
            object_ids = ((fact.work_item_id, ContextualObjectKind.WORK_ITEM),)
            asset_id = fact.asset_id
        elif isinstance(fact, OnCallContextV1):
            object_ids = ((fact.duty_scope_id, ContextualObjectKind.DUTY_SCOPE),)
        elif isinstance(fact, DevicePostureContextV1):
            object_ids = ((fact.device_id, ContextualObjectKind.DEVICE),)
        elif isinstance(fact, RiskSignalContextV1):
            object_ids = ((fact.signal_source_id, ContextualObjectKind.SIGNAL_SOURCE),)
        else:
            object_ids = (
                (
                    fact.approval_evidence_id,
                    ContextualObjectKind.APPROVAL_EVIDENCE,
                ),
            )
            asset_id = fact.asset_id
        for object_id, expected_kind in object_ids:
            item = registry.get(object_id)
            if item is None:
                raise ContextualAccessIntegrityError(
                    "contextual fact references an unknown registry object"
                )
            if item.kind is not expected_kind:
                raise ContextualAccessIntegrityError(
                    "contextual fact references the wrong registry object kind"
                )
            if (
                item.tenant_id != subject.tenant_id
                or item.organisation_id != subject.organisation_id
            ):
                raise ContextualAccessIntegrityError(
                    "contextual fact crosses tenant or organization scope"
                )
        if asset_id is not None:
            target = targets.get(asset_id)
            if target is None:
                raise ContextualAccessIntegrityError(
                    "contextual fact references an unknown authorization target"
                )
            if (
                target.tenant_id != subject.tenant_id
                or target.organisation_id != subject.organisation_id
            ):
                raise ContextualAccessIntegrityError(
                    "contextual fact asset crosses tenant or organization scope"
                )
        if isinstance(fact, BusinessJustificationContextV1) and (
            fact.action not in targets[fact.asset_id].actions
        ):
            raise ContextualAccessIntegrityError(
                "contextual justification action is undeclared by its target"
            )


def _validate_policies(public: ContextualAccessPublicV1) -> None:
    targets = {
        item.authorization_target_id: item
        for item in public.universe.authorization_targets
    }
    registry = {item.id: item for item in public.registry.objects}
    for policy in public.policies:
        for target_id in policy.target_handles:
            target = targets.get(target_id)
            if target is None:
                raise ContextualAccessIntegrityError(
                    "contextual policy references an unknown target"
                )
            if not set(policy.actions) <= set(target.actions):
                raise ContextualAccessIntegrityError(
                    "contextual policy action is undeclared by a target"
                )
        for rule in policy.rules:
            _validate_predicate_references(rule, registry)


def _validate_predicate_references(
    rule: ContextualRuleV1,
    registry: Mapping[str, ContextualObjectV1],
) -> None:
    for predicate in rule.predicates:
        reference: tuple[str, ContextualObjectKind] | None = None
        if isinstance(predicate, IsOnCallV1):
            reference = (predicate.duty_scope_id, ContextualObjectKind.DUTY_SCOPE)
        elif isinstance(predicate, RiskAtMostV1):
            reference = (
                predicate.signal_source_id,
                ContextualObjectKind.SIGNAL_SOURCE,
            )
        if reference is None:
            continue
        item = registry.get(reference[0])
        if item is None or item.kind is not reference[1]:
            raise ContextualAccessIntegrityError(
                "contextual predicate references an unknown or wrong-kind object"
            )


def _validate_requests(public: ContextualAccessPublicV1) -> None:
    principals = {item.principal_id: item for item in public.universe.principals}
    targets = {
        item.authorization_target_id: item
        for item in public.universe.authorization_targets
    }
    atoms = {item.access_atom_id: item for item in public.universe.access_atoms}
    registry = {item.id: item for item in public.registry.objects}
    for request in public.requests:
        subject = principals.get(request.subject_id)
        target = targets.get(request.asset_id)
        atom = atoms.get(request.access_atom_id)
        if subject is None or target is None or atom is None:
            raise ContextualAccessIntegrityError(
                "contextual request references an unknown universe object"
            )
        if (
            atom.subject_id != request.subject_id
            or atom.authorization_target_id != request.asset_id
            or atom.action != request.action
        ):
            raise ContextualAccessIntegrityError(
                "contextual request does not bind one existing access atom"
            )
        if (
            subject.tenant_id != target.tenant_id
            or subject.organisation_id != target.organisation_id
        ):
            raise ContextualAccessIntegrityError(
                "contextual request crosses tenant or organization scope"
            )
        applicable = _applicable_policies(public.policies, request)
        needs_device = any(
            isinstance(predicate, DevicePostureIsV1)
            for policy in applicable
            for rule in policy.rules
            for predicate in rule.predicates
        )
        if needs_device and request.device_id is None:
            raise ContextualAccessIntegrityError(
                "contextual request requires a device for applicable policy"
            )
        if request.device_id is not None:
            device = registry.get(request.device_id)
            if device is None or device.kind is not ContextualObjectKind.DEVICE:
                raise ContextualAccessIntegrityError(
                    "contextual request device is unknown or wrong kind"
                )
            if (
                device.tenant_id != subject.tenant_id
                or device.organisation_id != subject.organisation_id
            ):
                raise ContextualAccessIntegrityError(
                    "contextual request device crosses scope"
                )


def _validate_delivery_attempts(public: ContextualAccessPublicV1) -> None:
    event_ids = {item.id for item in public.events}
    attempt_events = {item.event_id for item in public.delivery_attempts}
    if attempt_events != event_ids:
        raise ContextualAccessIntegrityError(
            "contextual delivery attempts must cover every event"
        )


def _enforce_limits(
    *,
    config: ContextualAccessConfigV1,
    registry: ContextualObjectRegistryV1,
    policies: tuple[ContextualPolicyV1, ...],
    initial_facts: tuple[ContextualFactV1, ...],
    events: tuple[ContextualAccessEventV1, ...],
    delivery_attempts: tuple[ContextDeliveryAttemptV1, ...],
    requests: tuple[ContextualAccessRequestV1, ...],
) -> None:
    measured = (
        ("registry objects", len(registry.objects), config.limits.max_registry_objects),
        ("initial facts", len(initial_facts), config.limits.max_initial_facts),
        ("events", len(events), config.limits.max_events),
        (
            "delivery attempts",
            len(delivery_attempts),
            config.limits.max_delivery_attempts,
        ),
        ("requests", len(requests), config.limits.max_requests),
        ("policies", len(policies), config.limits.max_policies),
    )
    for description, count, limit in measured:
        if count > limit:
            raise ContextualAccessIntegrityError(
                f"contextual {description} count exceeds its configured limit"
            )
    for policy in policies:
        if len(policy.rules) > config.limits.max_rules_per_policy:
            raise ContextualAccessIntegrityError(
                "contextual policy rule count exceeds its configured limit"
            )
        if any(
            len(rule.predicates) > config.limits.max_predicates_per_rule
            for rule in policy.rules
        ):
            raise ContextualAccessIntegrityError(
                "contextual rule predicate count exceeds its configured limit"
            )


def _applicable_policies(
    policies: Collection[ContextualPolicyV1],
    request: ContextualAccessRequestV1,
) -> tuple[ContextualPolicyV1, ...]:
    return tuple(
        item
        for item in policies
        if request.asset_id in item.target_handles and request.action in item.actions
    )


__all__ = [
    "ContextualAccessIntegrityError",
    "compile_contextual_access_truth",
    "project_contextual_access_public",
    "validate_contextual_access_public",
]
