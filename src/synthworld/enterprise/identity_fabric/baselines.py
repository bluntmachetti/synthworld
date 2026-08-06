"""Deliberately weak public-only baselines for the #7 smoke benchmark."""

from __future__ import annotations

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricPredictionV1,
    EnterpriseIdentityFabricPublicInputV1,
    IdentityFabricAccessPredictionV1,
    IdentityFabricAccessQueryV1,
    IdentityFabricAccountPredictionV1,
    IdentityFabricAccountQueryV1,
    IdentityFabricCheckpointPredictionV1,
    IdentityFabricMembershipPredictionV1,
    IdentityFabricMembershipQueryV1,
    IdentityFabricRolePredictionV1,
    IdentityFabricRoleQueryV1,
)
from synthworld.enterprise.models import AdministrativeState, SyntheticDigestV1
from synthworld.enterprise.rbac.common import BindingStatus, LifecycleStatus
from synthworld.enterprise.rbac.models import DirectoryAccountObservationV1


def direct_only_membership_baseline(
    public: EnterpriseIdentityFabricPublicInputV1,
) -> EnterpriseIdentityFabricPredictionV1:
    """Treat only recorded subject-to-group edges as effective membership."""

    checkpoints = {item.checkpoint_id: item for item in public.checkpoints}
    queries = _membership_queries(public)
    return EnterpriseIdentityFabricPredictionV1(
        benchmark_digest=_benchmark_digest(public),
        checkpoints=tuple(
            IdentityFabricCheckpointPredictionV1(
                checkpoint_id=checkpoint_id,
                membership=tuple(
                    IdentityFabricMembershipPredictionV1(
                        query_id=query.query_id,
                        direct_member=(query.subject_id, query.group_id) in direct,
                        effective_member=(query.subject_id, query.group_id) in direct,
                    )
                    for query in queries[checkpoint_id]
                ),
            )
            for checkpoint_id, checkpoint in checkpoints.items()
            for direct in (
                {
                    (item.subject_id, item.group_id)
                    for item in checkpoint.directory_rbac_kernel.memberships
                },
            )
        ),
    )


def no_hierarchy_or_nesting_role_baseline(
    public: EnterpriseIdentityFabricPublicInputV1,
) -> EnterpriseIdentityFabricPredictionV1:
    """Resolve direct roles and one-hop roles from direct memberships only."""

    queries = _role_queries(public)
    rows: list[IdentityFabricCheckpointPredictionV1] = []
    for checkpoint in public.checkpoints:
        kernel = checkpoint.directory_rbac_kernel
        direct_roles = {
            (item.subject_id, item.role_id) for item in kernel.subject_role_assignments
        }
        direct_memberships = {
            (item.subject_id, item.group_id) for item in kernel.memberships
        }
        group_roles = {
            (item.group_id, item.role_id) for item in kernel.group_role_assignments
        }
        role_predictions: list[IdentityFabricRolePredictionV1] = []
        for query in queries[checkpoint.checkpoint_id]:
            direct = (query.subject_id, query.role_id) in direct_roles
            group = any(
                subject_id == query.subject_id
                and (group_id, query.role_id) in group_roles
                for subject_id, group_id in direct_memberships
            )
            role_predictions.append(
                IdentityFabricRolePredictionV1(
                    query_id=query.query_id,
                    direct_role_assignment=direct,
                    group_derived_role=group,
                    hierarchy_inherited_role=False,
                    effective_role=direct or group,
                )
            )
        rows.append(
            IdentityFabricCheckpointPredictionV1(
                checkpoint_id=checkpoint.checkpoint_id,
                roles=tuple(role_predictions),
            )
        )
    return EnterpriseIdentityFabricPredictionV1(
        benchmark_digest=_benchmark_digest(public), checkpoints=tuple(rows)
    )


def trust_recorded_state_baseline(
    public: EnterpriseIdentityFabricPublicInputV1,
) -> EnterpriseIdentityFabricPredictionV1:
    """Assume every recorded owner is canonical and report no hidden mismatch."""

    queries = _account_queries(public)
    rows: list[IdentityFabricCheckpointPredictionV1] = []
    for checkpoint in public.checkpoints:
        observations = {
            item.account_id: item
            for item in checkpoint.directory_rbac_kernel.account_observations
        }
        predictions: list[IdentityFabricAccountPredictionV1] = []
        for query in queries[checkpoint.checkpoint_id]:
            observation = observations.get(query.account_id)
            if observation is None:
                binding = BindingStatus.MISSING
                lifecycle = LifecycleStatus.INACTIVE
                observed_principal_id = None
            elif observation.observed_principal_id is None:
                binding = BindingStatus.MISSING
                lifecycle = _recorded_lifecycle(observation, query.tick)
                observed_principal_id = None
            else:
                binding = BindingStatus.MATCHES_CANONICAL
                lifecycle = _recorded_lifecycle(observation, query.tick)
                observed_principal_id = observation.observed_principal_id
            predictions.append(
                IdentityFabricAccountPredictionV1(
                    query_id=query.query_id,
                    canonical_principal_id=observed_principal_id,
                    binding_status=binding,
                    lifecycle_status=lifecycle,
                    orphaned=binding is BindingStatus.MISSING,
                    inactive=lifecycle is not LifecycleStatus.ACTIVE,
                )
            )
        rows.append(
            IdentityFabricCheckpointPredictionV1(
                checkpoint_id=checkpoint.checkpoint_id,
                accounts=tuple(predictions),
            )
        )
    return EnterpriseIdentityFabricPredictionV1(
        benchmark_digest=_benchmark_digest(public), checkpoints=tuple(rows)
    )


def latest_state_only_baseline(
    *,
    public: EnterpriseIdentityFabricPublicInputV1,
    source: EnterpriseIdentityFabricPredictionV1,
) -> EnterpriseIdentityFabricPredictionV1:
    """Apply the latest checkpoint prediction to every historical checkpoint."""

    benchmark_digest = _benchmark_digest(public)
    if source.benchmark_digest != benchmark_digest:
        raise ValueError("latest_state_baseline_benchmark_digest_mismatch")
    latest = max(public.checkpoints, key=lambda item: item.sequence)
    source_by_checkpoint = {item.checkpoint_id: item for item in source.checkpoints}
    latest_prediction = source_by_checkpoint.get(latest.checkpoint_id)
    if latest_prediction is None:
        raise ValueError("latest_state_baseline_latest_checkpoint_missing")
    membership_source = _membership_source(
        public,
        latest.checkpoint_id,
        latest_prediction.membership,
    )
    role_source = _role_source(public, latest.checkpoint_id, latest_prediction.roles)
    account_source = _account_source(
        public, latest.checkpoint_id, latest_prediction.accounts
    )
    access_source = _access_source(
        public, latest.checkpoint_id, latest_prediction.access
    )
    rows: list[IdentityFabricCheckpointPredictionV1] = []
    for checkpoint in public.checkpoints:
        rows.append(
            IdentityFabricCheckpointPredictionV1(
                checkpoint_id=checkpoint.checkpoint_id,
                directory_rbac=latest_prediction.directory_rbac,
                abac=latest_prediction.abac,
                rebac=latest_prediction.rebac,
                membership=tuple(
                    item.model_copy(update={"query_id": query.query_id})
                    for query in _membership_queries(public)[checkpoint.checkpoint_id]
                    for item in (membership_source[(query.subject_id, query.group_id)],)
                ),
                roles=tuple(
                    item.model_copy(update={"query_id": query.query_id})
                    for query in _role_queries(public)[checkpoint.checkpoint_id]
                    for item in (role_source[(query.subject_id, query.role_id)],)
                ),
                accounts=tuple(
                    item.model_copy(update={"query_id": query.query_id})
                    for query in _account_queries(public)[checkpoint.checkpoint_id]
                    for item in (account_source[(query.account_id, query.tick)],)
                ),
                access=tuple(
                    item.model_copy(update={"query_id": query.query_id})
                    for query in _access_queries(public)[checkpoint.checkpoint_id]
                    for item in (access_source[(query.cell_id,)],)
                ),
            )
        )
    return EnterpriseIdentityFabricPredictionV1(
        benchmark_digest=benchmark_digest,
        checkpoints=tuple(rows),
        accumulation=(),
    )


def all_non_birthright_is_sprawl_baseline(
    source: EnterpriseIdentityFabricPredictionV1,
) -> EnterpriseIdentityFabricPredictionV1:
    """Conflate access outside birthright with access outside intended policy."""

    return source.model_copy(
        update={
            "checkpoints": tuple(
                checkpoint.model_copy(
                    update={
                        "access": tuple(
                            item.model_copy(
                                update={"outside_intent": item.outside_birthright}
                            )
                            for item in checkpoint.access
                        )
                    }
                )
                for checkpoint in source.checkpoints
            )
        }
    )


def _recorded_lifecycle(
    observation: DirectoryAccountObservationV1, tick: int
) -> LifecycleStatus:
    valid_from_tick = observation.valid_from_tick
    valid_until_tick = observation.valid_until_tick
    if tick < valid_from_tick:
        return LifecycleStatus.NOT_YET_VALID
    if valid_until_tick is not None and tick >= valid_until_tick:
        return LifecycleStatus.EXPIRED
    if observation.administrative_state is not AdministrativeState.ACTIVE:
        return LifecycleStatus.INACTIVE
    return LifecycleStatus.ACTIVE


def _membership_source(
    public: EnterpriseIdentityFabricPublicInputV1,
    checkpoint_id: str,
    predictions: tuple[IdentityFabricMembershipPredictionV1, ...],
) -> dict[tuple[str, str], IdentityFabricMembershipPredictionV1]:
    query_by_id = {
        item.query_id: item
        for item in public.benchmark.membership_queries
        if item.checkpoint_id == checkpoint_id
    }
    prediction_by_id = {item.query_id: item for item in predictions}
    if set(prediction_by_id) != set(query_by_id):
        raise ValueError("latest_state_baseline_membership_inventory_mismatch")
    return {
        (query_by_id[query_id].subject_id, query_by_id[query_id].group_id): item
        for query_id, item in prediction_by_id.items()
    }


def _role_source(
    public: EnterpriseIdentityFabricPublicInputV1,
    checkpoint_id: str,
    predictions: tuple[IdentityFabricRolePredictionV1, ...],
) -> dict[tuple[str, str], IdentityFabricRolePredictionV1]:
    query_by_id = {
        item.query_id: item
        for item in public.benchmark.role_queries
        if item.checkpoint_id == checkpoint_id
    }
    prediction_by_id = {item.query_id: item for item in predictions}
    if set(prediction_by_id) != set(query_by_id):
        raise ValueError("latest_state_baseline_role_inventory_mismatch")
    return {
        (query_by_id[query_id].subject_id, query_by_id[query_id].role_id): item
        for query_id, item in prediction_by_id.items()
    }


def _account_source(
    public: EnterpriseIdentityFabricPublicInputV1,
    checkpoint_id: str,
    predictions: tuple[IdentityFabricAccountPredictionV1, ...],
) -> dict[tuple[str, int], IdentityFabricAccountPredictionV1]:
    query_by_id = {
        item.query_id: item
        for item in public.benchmark.account_queries
        if item.checkpoint_id == checkpoint_id
    }
    prediction_by_id = {item.query_id: item for item in predictions}
    if set(prediction_by_id) != set(query_by_id):
        raise ValueError("latest_state_baseline_account_inventory_mismatch")
    return {
        (query_by_id[query_id].account_id, query_by_id[query_id].tick): item
        for query_id, item in prediction_by_id.items()
    }


def _access_source(
    public: EnterpriseIdentityFabricPublicInputV1,
    checkpoint_id: str,
    predictions: tuple[IdentityFabricAccessPredictionV1, ...],
) -> dict[tuple[str], IdentityFabricAccessPredictionV1]:
    query_by_id = {
        item.query_id: item
        for item in public.benchmark.access_queries
        if item.checkpoint_id == checkpoint_id
    }
    prediction_by_id = {item.query_id: item for item in predictions}
    if set(prediction_by_id) != set(query_by_id):
        raise ValueError("latest_state_baseline_access_inventory_mismatch")
    return {
        (query_by_id[query_id].cell_id,): item
        for query_id, item in prediction_by_id.items()
    }


def _membership_queries(
    public: EnterpriseIdentityFabricPublicInputV1,
) -> dict[str, tuple[IdentityFabricMembershipQueryV1, ...]]:
    return {
        checkpoint.checkpoint_id: tuple(
            item
            for item in public.benchmark.membership_queries
            if item.checkpoint_id == checkpoint.checkpoint_id
        )
        for checkpoint in public.checkpoints
    }


def _role_queries(
    public: EnterpriseIdentityFabricPublicInputV1,
) -> dict[str, tuple[IdentityFabricRoleQueryV1, ...]]:
    return {
        checkpoint.checkpoint_id: tuple(
            item
            for item in public.benchmark.role_queries
            if item.checkpoint_id == checkpoint.checkpoint_id
        )
        for checkpoint in public.checkpoints
    }


def _account_queries(
    public: EnterpriseIdentityFabricPublicInputV1,
) -> dict[str, tuple[IdentityFabricAccountQueryV1, ...]]:
    return {
        checkpoint.checkpoint_id: tuple(
            item
            for item in public.benchmark.account_queries
            if item.checkpoint_id == checkpoint.checkpoint_id
        )
        for checkpoint in public.checkpoints
    }


def _access_queries(
    public: EnterpriseIdentityFabricPublicInputV1,
) -> dict[str, tuple[IdentityFabricAccessQueryV1, ...]]:
    return {
        checkpoint.checkpoint_id: tuple(
            item
            for item in public.benchmark.access_queries
            if item.checkpoint_id == checkpoint.checkpoint_id
        )
        for checkpoint in public.checkpoints
    }


def _benchmark_digest(
    public: EnterpriseIdentityFabricPublicInputV1,
) -> SyntheticDigestV1:
    return synthetic_digest(canonical_json_bytes(public.benchmark))


__all__ = [
    "all_non_birthright_is_sprawl_baseline",
    "direct_only_membership_baseline",
    "latest_state_only_baseline",
    "no_hierarchy_or_nesting_role_baseline",
    "trust_recorded_state_baseline",
]
