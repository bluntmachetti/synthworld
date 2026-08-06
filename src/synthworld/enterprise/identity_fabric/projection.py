"""Cell-preserving projection of native enterprise truth into the #7 smoke pack."""

from __future__ import annotations

from collections import defaultdict
from itertools import pairwise
from typing import TypedDict
from uuid import UUID, uuid5

from synthworld.enterprise.abac.models import AbacRuleTruthV1
from synthworld.enterprise.authorization_common import (
    AuthorizationEvaluationProfileKind,
    MechanismOutcome,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    encode_parts,
    synthetic_digest,
)
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricBenchmarkV1,
    EnterpriseIdentityFabricEvaluatorArtifactsV1,
    EnterpriseIdentityFabricProjectionLimitsV1,
    EnterpriseIdentityFabricPublicInputV1,
    EnterpriseIdentityFabricTruthV1,
    IdentityFabricAccessQueryV1,
    IdentityFabricAccessTruthV1,
    IdentityFabricAccountQueryV1,
    IdentityFabricAccountTruthV1,
    IdentityFabricAccumulationQueryV1,
    IdentityFabricAccumulationTruthV1,
    IdentityFabricCaseLabelV1,
    IdentityFabricCheckpointEvaluatorArtifactV1,
    IdentityFabricCheckpointPublicInputV1,
    IdentityFabricCheckpointReferenceV1,
    IdentityFabricCheckpointTruthV1,
    IdentityFabricInvariantPublicInputV1,
    IdentityFabricMembershipQueryV1,
    IdentityFabricMembershipTruthV1,
    IdentityFabricRoleQueryV1,
    IdentityFabricRoleTruthV1,
)
from synthworld.enterprise.models import (
    AdministrativeState,
    EnterpriseCanonicalBindingTruthV1,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    BindingStatus,
    DerivationMechanism,
    LifecycleStatus,
)
from synthworld.enterprise.rbac.models import (
    AuthorizedRolePathTruthV1,
    DirectoryAccountObservationV1,
    RoleAssignmentSourceKind,
)
from synthworld.enterprise.rebac.models import RebacRuleTruthV1

IDENTITY_FABRIC_QUERY_NAMESPACE_V1 = UUID("96ce26a1-24a1-5be5-bc05-f2524696de39")


class _CheckpointQueries(TypedDict):
    membership: tuple[IdentityFabricMembershipQueryV1, ...]
    roles: tuple[IdentityFabricRoleQueryV1, ...]
    accounts: tuple[IdentityFabricAccountQueryV1, ...]
    access: tuple[IdentityFabricAccessQueryV1, ...]


def project_enterprise_identity_fabric_public(
    *,
    invariant: IdentityFabricInvariantPublicInputV1,
    checkpoints: tuple[IdentityFabricCheckpointPublicInputV1, ...],
    limits: EnterpriseIdentityFabricProjectionLimitsV1 | None = None,
) -> EnterpriseIdentityFabricPublicInputV1:
    """Create only public query inventory and digest-bound product inputs."""

    selected_limits = limits or EnterpriseIdentityFabricProjectionLimitsV1()
    universe_digest, corpus_digest = _validate_public_inputs(invariant, checkpoints)
    _preflight(invariant, checkpoints, selected_limits)
    checkpoint_refs = tuple(
        IdentityFabricCheckpointReferenceV1(
            checkpoint_id=item.checkpoint_id,
            sequence=item.sequence,
            checkpoint_input_digest=synthetic_digest(canonical_json_bytes(item)),
        )
        for item in checkpoints
    )
    subjects = tuple(item.subject_id for item in invariant.universe.access_subjects)
    groups = tuple(item.group_id for item in invariant.universe.groups)
    roles = tuple(item.role_id for item in invariant.universe.roles)
    accounts = tuple(item.account_id for item in invariant.universe.accounts)
    cells = tuple(item.cell_id for item in invariant.corpus.evaluation_cells)
    ticks = tuple(sorted({item.tick for item in invariant.corpus.evaluation_cells}))
    namespace_parts = (universe_digest.value, corpus_digest.value)
    membership = tuple(
        IdentityFabricMembershipQueryV1(
            query_id=_query_id(
                *namespace_parts, "membership", checkpoint.checkpoint_id, subject, group
            ),
            checkpoint_id=checkpoint.checkpoint_id,
            subject_id=subject,
            group_id=group,
        )
        for checkpoint in checkpoints
        for subject in subjects
        for group in groups
    )
    role_queries = tuple(
        IdentityFabricRoleQueryV1(
            query_id=_query_id(
                *namespace_parts, "role", checkpoint.checkpoint_id, subject, role
            ),
            checkpoint_id=checkpoint.checkpoint_id,
            subject_id=subject,
            role_id=role,
        )
        for checkpoint in checkpoints
        for subject in subjects
        for role in roles
    )
    account_queries = tuple(
        IdentityFabricAccountQueryV1(
            query_id=_query_id(
                *namespace_parts,
                "account",
                checkpoint.checkpoint_id,
                account,
                str(tick),
            ),
            checkpoint_id=checkpoint.checkpoint_id,
            account_id=account,
            tick=tick,
        )
        for checkpoint in checkpoints
        for account in accounts
        for tick in ticks
    )
    access_queries = tuple(
        IdentityFabricAccessQueryV1(
            query_id=_query_id(
                *namespace_parts, "access", checkpoint.checkpoint_id, cell
            ),
            checkpoint_id=checkpoint.checkpoint_id,
            cell_id=cell,
        )
        for checkpoint in checkpoints
        for cell in cells
    )
    accumulation = tuple(
        IdentityFabricAccumulationQueryV1(
            query_id=_query_id(
                *namespace_parts,
                "accumulation",
                subject,
                left.checkpoint_id,
                right.checkpoint_id,
            ),
            subject_id=subject,
            from_checkpoint_id=left.checkpoint_id,
            to_checkpoint_id=right.checkpoint_id,
        )
        for left, right in pairwise(checkpoints)
        for subject in subjects
    )
    benchmark = EnterpriseIdentityFabricBenchmarkV1(
        identity_access_universe_digest=universe_digest,
        evaluation_corpus_digest=corpus_digest,
        invariant_input_digest=synthetic_digest(canonical_json_bytes(invariant)),
        checkpoints=checkpoint_refs,
        membership_queries=membership,
        role_queries=role_queries,
        account_queries=account_queries,
        access_queries=access_queries,
        accumulation_queries=accumulation,
    )
    return EnterpriseIdentityFabricPublicInputV1(
        invariant=invariant,
        checkpoints=checkpoints,
        benchmark=benchmark,
    )


def compile_enterprise_identity_fabric_truth(
    *,
    public: EnterpriseIdentityFabricPublicInputV1,
    canonical_binding_truth: EnterpriseCanonicalBindingTruthV1,
    checkpoints: tuple[IdentityFabricCheckpointEvaluatorArtifactV1, ...],
) -> EnterpriseIdentityFabricEvaluatorArtifactsV1:
    """Derive evaluator-only findings without adding an identity or access cell."""

    _validate_public_query_inventory(public)
    public_digest = synthetic_digest(canonical_json_bytes(public))
    benchmark_digest = synthetic_digest(canonical_json_bytes(public.benchmark))
    binding_digest = synthetic_digest(canonical_json_bytes(canonical_binding_truth))
    if (
        canonical_binding_truth.identity_access_universe_digest
        != public.benchmark.identity_access_universe_digest
    ):
        raise EnterpriseCompileError(
            "identity_fabric_binding_universe_digest_mismatch",
            "canonical account bindings do not bind the public universe",
        )
    expected = tuple(
        (item.checkpoint_id, item.sequence) for item in public.benchmark.checkpoints
    )
    actual = tuple((item.checkpoint_id, item.sequence) for item in checkpoints)
    if actual != expected:
        raise EnterpriseCompileError(
            "identity_fabric_evaluator_checkpoint_inventory_mismatch",
            "evaluator checkpoints do not exactly match the public inventory",
        )
    public_by_id = {item.checkpoint_id: item for item in public.checkpoints}
    query_sets = _queries_by_checkpoint(public.benchmark)
    checkpoint_truth: list[IdentityFabricCheckpointTruthV1] = []
    labels: list[IdentityFabricCaseLabelV1] = []
    for evaluator in checkpoints:
        public_checkpoint = public_by_id[evaluator.checkpoint_id]
        _validate_evaluator_checkpoint(
            public=public,
            public_checkpoint=public_checkpoint,
            evaluator=evaluator,
            binding_digest=binding_digest,
        )
        checkpoint_row, checkpoint_labels = _compile_checkpoint_truth(
            public=public,
            public_checkpoint=public_checkpoint,
            evaluator=evaluator,
            queries=query_sets[evaluator.checkpoint_id],
            canonical_binding_truth=canonical_binding_truth,
        )
        checkpoint_truth.append(checkpoint_row)
        labels.extend(checkpoint_labels)
    access_by_checkpoint = {
        item.checkpoint_id: {row.query_id: row for row in item.access}
        for item in checkpoint_truth
    }
    access_query_by_id = {
        item.query_id: item for item in public.benchmark.access_queries
    }
    atom_by_cell = _atom_subject_by_cell(public.invariant)
    accumulation: list[IdentityFabricAccumulationTruthV1] = []
    for query in public.benchmark.accumulation_queries:
        before = {
            access_query_by_id[row.query_id].cell_id
            for row in access_by_checkpoint[query.from_checkpoint_id].values()
            if atom_by_cell[access_query_by_id[row.query_id].cell_id]
            == query.subject_id
            and row.outside_intent
        }
        after = {
            access_query_by_id[row.query_id].cell_id
            for row in access_by_checkpoint[query.to_checkpoint_id].values()
            if atom_by_cell[access_query_by_id[row.query_id].cell_id]
            == query.subject_id
            and row.outside_intent
        }
        accumulated = tuple(sorted(after - before))
        accumulation.append(
            IdentityFabricAccumulationTruthV1(
                query_id=query.query_id, accumulated_cell_ids=accumulated
            )
        )
        labels.append(
            IdentityFabricCaseLabelV1(
                query_id=query.query_id,
                labels=(
                    "privilege-accumulation-positive"
                    if accumulated
                    else "privilege-accumulation-negative",
                ),
            )
        )
    enterprise_truth = EnterpriseIdentityFabricTruthV1(
        public_input_digest=public_digest,
        benchmark_digest=benchmark_digest,
        canonical_binding_truth_digest=binding_digest,
        checkpoints=tuple(checkpoint_truth),
        accumulation=tuple(accumulation),
        case_labels=tuple(labels),
    )
    return EnterpriseIdentityFabricEvaluatorArtifactsV1(
        public_input_digest=public_digest,
        canonical_binding_truth=canonical_binding_truth,
        checkpoints=checkpoints,
        truth=enterprise_truth,
    )


def _validate_public_query_inventory(
    public: EnterpriseIdentityFabricPublicInputV1,
) -> None:
    benchmark = public.benchmark
    checkpoint_ids = tuple(item.checkpoint_id for item in benchmark.checkpoints)
    subject_ids = {
        item.subject_id for item in public.invariant.universe.access_subjects
    }
    group_ids = {item.group_id for item in public.invariant.universe.groups}
    role_ids = {item.role_id for item in public.invariant.universe.roles}
    account_ids = {item.account_id for item in public.invariant.universe.accounts}
    cell_ids = {item.cell_id for item in public.invariant.corpus.evaluation_cells}
    ticks = {item.tick for item in public.invariant.corpus.evaluation_cells}
    namespace_parts = (
        benchmark.identity_access_universe_digest.value,
        benchmark.evaluation_corpus_digest.value,
    )
    membership_valid = len(benchmark.membership_queries) == (
        len(checkpoint_ids) * len(subject_ids) * len(group_ids)
    ) and all(
        item.checkpoint_id in checkpoint_ids
        and item.subject_id in subject_ids
        and item.group_id in group_ids
        and item.query_id
        == _query_id(
            *namespace_parts,
            "membership",
            item.checkpoint_id,
            item.subject_id,
            item.group_id,
        )
        for item in benchmark.membership_queries
    )
    role_valid = len(benchmark.role_queries) == (
        len(checkpoint_ids) * len(subject_ids) * len(role_ids)
    ) and all(
        item.checkpoint_id in checkpoint_ids
        and item.subject_id in subject_ids
        and item.role_id in role_ids
        and item.query_id
        == _query_id(
            *namespace_parts,
            "role",
            item.checkpoint_id,
            item.subject_id,
            item.role_id,
        )
        for item in benchmark.role_queries
    )
    account_valid = len(benchmark.account_queries) == (
        len(checkpoint_ids) * len(account_ids) * len(ticks)
    ) and all(
        item.checkpoint_id in checkpoint_ids
        and item.account_id in account_ids
        and item.tick in ticks
        and item.query_id
        == _query_id(
            *namespace_parts,
            "account",
            item.checkpoint_id,
            item.account_id,
            str(item.tick),
        )
        for item in benchmark.account_queries
    )
    access_valid = len(benchmark.access_queries) == (
        len(checkpoint_ids) * len(cell_ids)
    ) and all(
        item.checkpoint_id in checkpoint_ids
        and item.cell_id in cell_ids
        and item.query_id
        == _query_id(
            *namespace_parts,
            "access",
            item.checkpoint_id,
            item.cell_id,
        )
        for item in benchmark.access_queries
    )
    adjacent_pairs = set(pairwise(checkpoint_ids))
    accumulation_valid = len(benchmark.accumulation_queries) == (
        len(adjacent_pairs) * len(subject_ids)
    ) and all(
        (item.from_checkpoint_id, item.to_checkpoint_id) in adjacent_pairs
        and item.subject_id in subject_ids
        and item.query_id
        == _query_id(
            *namespace_parts,
            "accumulation",
            item.subject_id,
            item.from_checkpoint_id,
            item.to_checkpoint_id,
        )
        for item in benchmark.accumulation_queries
    )
    if not all(
        (
            membership_valid,
            role_valid,
            account_valid,
            access_valid,
            accumulation_valid,
        )
    ):
        raise EnterpriseCompileError(
            "identity_fabric_public_query_inventory_mismatch",
            "public query coordinates must equal the deterministic "
            "fixed-world inventory",
        )


def _validate_public_inputs(
    invariant: IdentityFabricInvariantPublicInputV1,
    checkpoints: tuple[IdentityFabricCheckpointPublicInputV1, ...],
) -> tuple[SyntheticDigestV1, SyntheticDigestV1]:
    if len(checkpoints) < 2:
        raise EnterpriseCompileError(
            "identity_fabric_checkpoint_minimum_not_met",
            "the smoke profile requires at least two ordered checkpoints",
        )
    sequences = tuple(item.sequence for item in checkpoints)
    if sequences != tuple(range(len(checkpoints))):
        raise EnterpriseCompileError(
            "identity_fabric_checkpoint_sequence_not_contiguous",
            "checkpoint sequence must be ordered and contiguous from zero",
        )
    if len({item.checkpoint_id for item in checkpoints}) != len(checkpoints):
        raise EnterpriseCompileError(
            "duplicate_identity_fabric_checkpoint_id",
            "checkpoint IDs must be unique",
        )
    universe_digest = synthetic_digest(canonical_json_bytes(invariant.universe))
    corpus_digest = synthetic_digest(canonical_json_bytes(invariant.corpus))
    if invariant.corpus.identity_access_universe_digest != universe_digest:
        raise EnterpriseCompileError(
            "identity_fabric_corpus_universe_digest_mismatch",
            "the evaluation corpus does not bind the fixed universe",
        )
    for label, digest in (
        (
            "directory_intent_universe",
            invariant.directory_rbac_intent.identity_access_universe_digest,
        ),
        ("abac_intent_universe", invariant.abac_intent.identity_access_universe_digest),
        (
            "rebac_intent_universe",
            invariant.rebac_intent.identity_access_universe_digest,
        ),
    ):
        _require_digest(label, digest, universe_digest)
    for label, digest in (
        (
            "directory_intent_corpus",
            invariant.directory_rbac_intent.evaluation_corpus_digest,
        ),
        ("session_state_corpus", invariant.rbac_session_state.evaluation_corpus_digest),
        ("abac_intent_corpus", invariant.abac_intent.evaluation_corpus_digest),
        ("rebac_intent_corpus", invariant.rebac_intent.evaluation_corpus_digest),
        (
            "evaluation_profile_corpus",
            invariant.evaluation_profile.evaluation_corpus_digest,
        ),
    ):
        _require_digest(label, digest, corpus_digest)
    profile_cells = {item.cell_id for item in invariant.evaluation_profile.cells}
    corpus_cells = {item.cell_id for item in invariant.corpus.evaluation_cells}
    if profile_cells != corpus_cells:
        raise EnterpriseCompileError(
            "identity_fabric_profile_cell_inventory_mismatch",
            "the evaluation profile must cover the frozen corpus exactly",
        )
    for checkpoint in checkpoints:
        _require_digest(
            "checkpoint_kernel_universe",
            checkpoint.directory_rbac_kernel.identity_access_universe_digest,
            universe_digest,
        )
        _require_digest(
            "checkpoint_abac_state_universe",
            checkpoint.abac_state.identity_access_universe_digest,
            universe_digest,
        )
        _require_digest(
            "checkpoint_rebac_state_universe",
            checkpoint.rebac_state.identity_access_universe_digest,
            universe_digest,
        )
        _require_digest(
            "checkpoint_composition_universe",
            checkpoint.composition.identity_access_universe_digest,
            universe_digest,
        )
        _require_digest(
            "checkpoint_authorization_kernel_universe",
            checkpoint.authorization_kernel.identity_access_universe_digest,
            universe_digest,
        )
        for label, digest in (
            ("abac_state_corpus", checkpoint.abac_state.evaluation_corpus_digest),
            ("rebac_state_corpus", checkpoint.rebac_state.evaluation_corpus_digest),
            ("composition_corpus", checkpoint.composition.evaluation_corpus_digest),
            (
                "authorization_kernel_corpus",
                checkpoint.authorization_kernel.evaluation_corpus_digest,
            ),
        ):
            _require_digest(f"checkpoint_{label}", digest, corpus_digest)
        _require_digest(
            "checkpoint_authorization_kernel_composition",
            checkpoint.authorization_kernel.composition_digest,
            synthetic_digest(canonical_json_bytes(checkpoint.composition)),
        )
        _require_digest(
            "checkpoint_authorization_kernel_profile",
            checkpoint.authorization_kernel.evaluation_profile_digest,
            synthetic_digest(canonical_json_bytes(invariant.evaluation_profile)),
        )
    return universe_digest, corpus_digest


def _preflight(
    invariant: IdentityFabricInvariantPublicInputV1,
    checkpoints: tuple[IdentityFabricCheckpointPublicInputV1, ...],
    limits: EnterpriseIdentityFabricProjectionLimitsV1,
) -> None:
    checkpoint_count = len(checkpoints)
    subject_count = len(invariant.universe.access_subjects)
    membership = checkpoint_count * subject_count * len(invariant.universe.groups)
    roles = checkpoint_count * subject_count * len(invariant.universe.roles)
    ticks = len({item.tick for item in invariant.corpus.evaluation_cells})
    accounts = checkpoint_count * len(invariant.universe.accounts) * ticks
    access = checkpoint_count * len(invariant.corpus.evaluation_cells)
    accumulation = max(0, checkpoint_count - 1) * subject_count
    for code, measured, allowed in (
        ("checkpoint_budget_exceeded", checkpoint_count, limits.max_checkpoints),
        ("membership_query_budget_exceeded", membership, limits.max_membership_queries),
        ("role_query_budget_exceeded", roles, limits.max_role_queries),
        ("account_query_budget_exceeded", accounts, limits.max_account_queries),
        ("access_query_budget_exceeded", access, limits.max_access_queries),
        (
            "accumulation_query_budget_exceeded",
            accumulation,
            limits.max_accumulation_queries,
        ),
        (
            "total_query_budget_exceeded",
            membership + roles + accounts + access + accumulation,
            limits.max_total_queries,
        ),
    ):
        if measured > allowed:
            raise EnterpriseCompileError(
                f"identity_fabric_{code}",
                "identity-fabric projection exceeds an independent query budget",
                measured=measured,
                allowed=allowed,
            )


def _validate_evaluator_checkpoint(
    *,
    public: EnterpriseIdentityFabricPublicInputV1,
    public_checkpoint: IdentityFabricCheckpointPublicInputV1,
    evaluator: IdentityFabricCheckpointEvaluatorArtifactV1,
    binding_digest: SyntheticDigestV1,
) -> None:
    universe_digest = public.benchmark.identity_access_universe_digest
    corpus_digest = public.benchmark.evaluation_corpus_digest
    directory_digest = synthetic_digest(
        canonical_json_bytes(evaluator.directory_rbac_truth)
    )
    abac_digest = synthetic_digest(canonical_json_bytes(evaluator.abac_truth))
    rebac_digest = synthetic_digest(canonical_json_bytes(evaluator.rebac_truth))
    for label, observed, expected in (
        (
            "directory_universe",
            evaluator.directory_rbac_truth.identity_access_universe_digest,
            universe_digest,
        ),
        (
            "directory_corpus",
            evaluator.directory_rbac_truth.evaluation_corpus_digest,
            corpus_digest,
        ),
        (
            "directory_binding",
            evaluator.directory_rbac_truth.canonical_binding_truth_digest,
            binding_digest,
        ),
        (
            "directory_kernel",
            evaluator.directory_rbac_truth.directory_rbac_kernel_digest,
            synthetic_digest(
                canonical_json_bytes(public_checkpoint.directory_rbac_kernel)
            ),
        ),
        (
            "abac_universe",
            evaluator.abac_truth.identity_access_universe_digest,
            universe_digest,
        ),
        ("abac_corpus", evaluator.abac_truth.evaluation_corpus_digest, corpus_digest),
        (
            "abac_state",
            evaluator.abac_truth.abac_state_digest,
            synthetic_digest(canonical_json_bytes(public_checkpoint.abac_state)),
        ),
        (
            "abac_intent",
            evaluator.abac_truth.abac_intent_digest,
            synthetic_digest(canonical_json_bytes(public.invariant.abac_intent)),
        ),
        (
            "rebac_universe",
            evaluator.rebac_truth.identity_access_universe_digest,
            universe_digest,
        ),
        ("rebac_corpus", evaluator.rebac_truth.evaluation_corpus_digest, corpus_digest),
        (
            "rebac_state",
            evaluator.rebac_truth.rebac_state_digest,
            synthetic_digest(canonical_json_bytes(public_checkpoint.rebac_state)),
        ),
        (
            "rebac_intent",
            evaluator.rebac_truth.rebac_intent_digest,
            synthetic_digest(canonical_json_bytes(public.invariant.rebac_intent)),
        ),
        (
            "aggregate_universe",
            evaluator.access_state.identity_access_universe_digest,
            universe_digest,
        ),
        (
            "aggregate_corpus",
            evaluator.access_state.evaluation_corpus_digest,
            corpus_digest,
        ),
        (
            "aggregate_binding",
            evaluator.access_state.canonical_binding_truth_digest,
            binding_digest,
        ),
        (
            "aggregate_composition",
            evaluator.access_state.composition_digest,
            synthetic_digest(canonical_json_bytes(public_checkpoint.composition)),
        ),
        (
            "aggregate_kernel",
            evaluator.access_state.authorization_kernel_digest,
            synthetic_digest(
                canonical_json_bytes(public_checkpoint.authorization_kernel)
            ),
        ),
        (
            "aggregate_directory",
            evaluator.access_state.directory_rbac_truth_digest,
            directory_digest,
        ),
        ("aggregate_abac", evaluator.access_state.abac_truth_digest, abac_digest),
        ("aggregate_rebac", evaluator.access_state.rebac_truth_digest, rebac_digest),
    ):
        _require_digest(f"evaluator_{label}", observed, expected)
    composition = public_checkpoint.composition
    if composition.abac is None or composition.rebac is None:
        raise EnterpriseCompileError(
            "identity_fabric_composition_component_missing",
            "the smoke profile requires all three native component families",
        )
    _require_digest(
        "evaluator_composition_directory",
        composition.directory_rbac.component_digest,
        directory_digest,
    )
    _require_digest(
        "evaluator_composition_abac", composition.abac.component_digest, abac_digest
    )
    _require_digest(
        "evaluator_composition_rebac", composition.rebac.component_digest, rebac_digest
    )


def _compile_checkpoint_truth(
    *,
    public: EnterpriseIdentityFabricPublicInputV1,
    public_checkpoint: IdentityFabricCheckpointPublicInputV1,
    evaluator: IdentityFabricCheckpointEvaluatorArtifactV1,
    queries: _CheckpointQueries,
    canonical_binding_truth: EnterpriseCanonicalBindingTruthV1,
) -> tuple[IdentityFabricCheckpointTruthV1, tuple[IdentityFabricCaseLabelV1, ...]]:
    directory = evaluator.directory_rbac_truth
    membership_paths: dict[tuple[str, str], list[str]] = defaultdict(list)
    for membership_path in directory.membership_paths:
        membership_paths[(membership_path.subject_id, membership_path.group_id)].append(
            membership_path.path_id
        )
    direct_memberships = {
        (item.subject_id, item.group_id)
        for item in public_checkpoint.directory_rbac_kernel.memberships
    }
    role_paths: dict[tuple[str, str], list[AuthorizedRolePathTruthV1]] = defaultdict(
        list
    )
    for role_path in directory.authorized_role_paths:
        role_paths[(role_path.subject_id, role_path.role_id)].append(role_path)
    direct_roles = {
        (item.subject_id, item.role_id)
        for item in public_checkpoint.directory_rbac_kernel.subject_role_assignments
    }
    canonical_by_account = {
        item.account_id: item.principal_id for item in canonical_binding_truth.bindings
    }
    observations = {
        item.account_id: item
        for item in public_checkpoint.directory_rbac_kernel.account_observations
    }
    directory_cells = {item.cell_id: item for item in directory.cells}
    directory_paths = {item.path_id: item for item in directory.access_derivation_paths}
    abac_cells = {item.cell_id: item for item in evaluator.abac_truth.cells}
    abac_rules = {item.truth_id: item for item in evaluator.abac_truth.rule_truth}
    rebac_cells = {item.cell_id: item for item in evaluator.rebac_truth.cells}
    rebac_rules = {item.truth_id: item for item in evaluator.rebac_truth.rule_truth}
    aggregate_cells = {item.cell_id: item for item in evaluator.access_state.cells}
    conflicts = {
        item.conflict_id: item for item in evaluator.access_state.policy_conflicts
    }
    membership_truth: list[IdentityFabricMembershipTruthV1] = []
    role_truth: list[IdentityFabricRoleTruthV1] = []
    account_truth: list[IdentityFabricAccountTruthV1] = []
    access_truth: list[IdentityFabricAccessTruthV1] = []
    labels: list[IdentityFabricCaseLabelV1] = []
    for membership_query in queries["membership"]:
        path_ids = tuple(
            sorted(
                membership_paths[
                    (membership_query.subject_id, membership_query.group_id)
                ]
            )
        )
        direct = (
            membership_query.subject_id,
            membership_query.group_id,
        ) in direct_memberships
        effective = bool(path_ids)
        membership_truth.append(
            IdentityFabricMembershipTruthV1(
                query_id=membership_query.query_id,
                direct_member=direct,
                effective_member=effective,
                membership_path_ids=path_ids,
            )
        )
        labels.append(
            IdentityFabricCaseLabelV1(
                query_id=membership_query.query_id,
                labels=(
                    "direct-membership"
                    if direct
                    else "nested-membership-only"
                    if effective
                    else "membership-negative",
                ),
            )
        )
    for role_query in queries["roles"]:
        authorized_paths = role_paths[(role_query.subject_id, role_query.role_id)]
        direct = (role_query.subject_id, role_query.role_id) in direct_roles
        group_derived = any(
            item.assignment_source_kind is RoleAssignmentSourceKind.GROUP
            for item in authorized_paths
        )
        hierarchy = any(len(item.role_path) > 1 for item in authorized_paths)
        effective = bool(authorized_paths)
        role_truth.append(
            IdentityFabricRoleTruthV1(
                query_id=role_query.query_id,
                direct_role_assignment=direct,
                group_derived_role=group_derived,
                hierarchy_inherited_role=hierarchy,
                effective_role=effective,
                authorized_role_path_ids=tuple(
                    sorted(item.path_id for item in authorized_paths)
                ),
            )
        )
        role_labels = tuple(
            label
            for flag, label in (
                (direct, "direct-role"),
                (group_derived, "group-derived-role"),
                (hierarchy, "hierarchy-inherited-role"),
                (not effective, "role-negative"),
            )
            if flag
        )
        labels.append(
            IdentityFabricCaseLabelV1(
                query_id=role_query.query_id,
                labels=role_labels or ("effective-role",),
            )
        )
    for account_query in queries["accounts"]:
        canonical = canonical_by_account[account_query.account_id]
        observation = observations.get(account_query.account_id)
        binding, lifecycle = _account_status(
            canonical_principal_id=canonical,
            observation=observation,
            tick=account_query.tick,
        )
        observed = (
            observation.observed_principal_id if observation is not None else None
        )
        orphaned = binding is BindingStatus.MISSING
        inactive = lifecycle is not LifecycleStatus.ACTIVE
        account_truth.append(
            IdentityFabricAccountTruthV1(
                query_id=account_query.query_id,
                canonical_principal_id=canonical,
                observed_principal_id=observed,
                binding_status=binding,
                lifecycle_status=lifecycle,
                orphaned=orphaned,
                inactive=inactive,
            )
        )
        labels.append(
            IdentityFabricCaseLabelV1(
                query_id=account_query.query_id,
                labels=tuple(
                    sorted(
                        {
                            f"binding-{binding.value}",
                            f"lifecycle-{lifecycle.value}",
                        }
                    )
                ),
            )
        )
    for access_query in queries["access"]:
        directory_cell = directory_cells[access_query.cell_id]
        aggregate = aggregate_cells[access_query.cell_id]
        derivation_paths = tuple(
            directory_paths[path_id] for path_id in directory_cell.effective_path_ids
        )
        direct = any(
            item.mechanism is DerivationMechanism.DIRECT_ENTITLEMENT
            for item in derivation_paths
        )
        role = any(
            item.mechanism is DerivationMechanism.ROLE for item in derivation_paths
        )
        derivation_count = _selected_derivation_count(
            aggregate.profile,
            directory_cell.effective_path_ids,
            abac_cells[access_query.cell_id].actual_rule_truth_ids,
            abac_rules,
            rebac_cells[access_query.cell_id].actual_rule_truth_ids,
            rebac_rules,
        )
        birthright = directory_cell.birthright_decision is AuthorizationDecision.ALLOW
        approved_exception = bool(directory_cell.approved_exception_ids)
        outside_birthright = (
            aggregate.effective_decision is AuthorizationDecision.ALLOW
            and not birthright
        )
        outside_intent = (
            aggregate.effective_decision is AuthorizationDecision.ALLOW
            and aggregate.intended_decision is AuthorizationDecision.DENY
        )
        conflict = conflicts[aggregate.policy_conflict_id].actual_conflict
        access_truth.append(
            IdentityFabricAccessTruthV1(
                query_id=access_query.query_id,
                direct_entitlement=direct,
                role_entitlement=role,
                birthright_access=birthright,
                approved_exception=approved_exception,
                intended_decision=aggregate.intended_decision,
                effective_decision=aggregate.effective_decision,
                final_decision=aggregate.final_decision,
                mechanism_outcomes=aggregate.actual_mechanism_outcomes,
                policy_conflict=conflict,
                redundant_derivation=derivation_count > 1,
                outside_birthright=outside_birthright,
                outside_intent=outside_intent,
            )
        )
        access_labels = tuple(
            label
            for flag, label in (
                (direct, "direct-entitlement"),
                (role, "role-entitlement"),
                (birthright, "birthright-access"),
                (approved_exception, "approved-exception"),
                (derivation_count > 1, "redundant-derivation"),
                (outside_birthright, "outside-birthright"),
                (outside_intent, "outside-intent"),
                (conflict, "policy-conflict"),
            )
            if flag
        )
        labels.append(
            IdentityFabricCaseLabelV1(
                query_id=access_query.query_id,
                labels=access_labels or ("access-control",),
            )
        )
    return (
        IdentityFabricCheckpointTruthV1(
            checkpoint_id=evaluator.checkpoint_id,
            sequence=evaluator.sequence,
            membership=tuple(membership_truth),
            roles=tuple(role_truth),
            accounts=tuple(account_truth),
            access=tuple(access_truth),
        ),
        tuple(labels),
    )


def _selected_derivation_count(
    profile: AuthorizationEvaluationProfileKind,
    directory_path_ids: tuple[str, ...],
    abac_rule_ids: tuple[str, ...],
    abac_rules: dict[str, AbacRuleTruthV1],
    rebac_rule_ids: tuple[str, ...],
    rebac_rules: dict[str, RebacRuleTruthV1],
) -> int:
    if profile in {
        AuthorizationEvaluationProfileKind.RBAC,
        AuthorizationEvaluationProfileKind.RBAC_WITH_ABAC_GUARD,
    }:
        return len(directory_path_ids)
    if profile is AuthorizationEvaluationProfileKind.ABAC:
        return sum(
            abac_rules[item].outcome is MechanismOutcome.ALLOW for item in abac_rule_ids
        )
    return sum(
        len(rebac_rules[item].path_ids)
        for item in rebac_rule_ids
        if rebac_rules[item].outcome is MechanismOutcome.ALLOW
    )


def _account_status(
    *,
    canonical_principal_id: str,
    observation: DirectoryAccountObservationV1 | None,
    tick: int,
) -> tuple[BindingStatus, LifecycleStatus]:
    if observation is None:
        return BindingStatus.MISSING, LifecycleStatus.INACTIVE
    observed_principal_id = observation.observed_principal_id
    if observed_principal_id is None:
        binding = BindingStatus.MISSING
    elif observed_principal_id == canonical_principal_id:
        binding = BindingStatus.MATCHES_CANONICAL
    else:
        binding = BindingStatus.MISMATCH
    if tick < observation.valid_from_tick:
        lifecycle = LifecycleStatus.NOT_YET_VALID
    elif (
        observation.valid_until_tick is not None
        and tick >= observation.valid_until_tick
    ):
        lifecycle = LifecycleStatus.EXPIRED
    elif observation.administrative_state is not AdministrativeState.ACTIVE:
        lifecycle = LifecycleStatus.INACTIVE
    else:
        lifecycle = LifecycleStatus.ACTIVE
    return binding, lifecycle


def _queries_by_checkpoint(
    benchmark: EnterpriseIdentityFabricBenchmarkV1,
) -> dict[str, _CheckpointQueries]:
    result: dict[str, _CheckpointQueries] = {}
    for checkpoint in benchmark.checkpoints:
        checkpoint_id = checkpoint.checkpoint_id
        result[checkpoint_id] = {
            "membership": tuple(
                item
                for item in benchmark.membership_queries
                if item.checkpoint_id == checkpoint_id
            ),
            "roles": tuple(
                item
                for item in benchmark.role_queries
                if item.checkpoint_id == checkpoint_id
            ),
            "accounts": tuple(
                item
                for item in benchmark.account_queries
                if item.checkpoint_id == checkpoint_id
            ),
            "access": tuple(
                item
                for item in benchmark.access_queries
                if item.checkpoint_id == checkpoint_id
            ),
        }
    return result


def _atom_subject_by_cell(
    invariant: IdentityFabricInvariantPublicInputV1,
) -> dict[str, str]:
    atoms = {item.access_atom_id: item for item in invariant.universe.access_atoms}
    return {
        item.cell_id: atoms[item.access_atom_id].subject_id
        for item in invariant.corpus.evaluation_cells
    }


def _require_digest(
    label: str,
    observed: SyntheticDigestV1 | None,
    expected: SyntheticDigestV1,
) -> None:
    if observed != expected:
        raise EnterpriseCompileError(
            f"identity_fabric_{label}_digest_mismatch",
            "identity-fabric input does not bind the supplied immutable artifact",
        )


def _query_id(*parts: str) -> str:
    return str(uuid5(IDENTITY_FABRIC_QUERY_NAMESPACE_V1, encode_parts(parts)))


__all__ = [
    "IDENTITY_FABRIC_QUERY_NAMESPACE_V1",
    "compile_enterprise_identity_fabric_truth",
    "project_enterprise_identity_fabric_public",
]
