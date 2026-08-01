"""Staged ambiguity receipts with physically and temporally separate truths."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from synthworld.ambiguity import (
    AMBIGUITY_SCHEMA_VERSION,
    PairPrediction,
    PublicAmbiguityTask,
)
from synthworld.ambiguity_metrics import (
    AMBIGUITY_DISPOSITION_SCORING_VERSION,
    AmbiguityDispositionMetrics,
    evaluate_ambiguity_dispositions,
)
from synthworld.ambiguity_partition import (
    AMBIGUITY_MEMBERSHIP_SCORING_VERSION,
    AmbiguityMembershipMetrics,
    derive_ambiguity_pair_predictions,
    evaluate_ambiguity_memberships,
    validate_ambiguity_partition,
)
from synthworld.ambiguity_serialization import (
    DispositionTruth,
    MembershipTruth,
    load_golden_ambiguity_disposition_truth,
    load_golden_ambiguity_membership_truth,
    load_golden_ambiguity_public_task,
)
from synthworld.assurance import reference_product
from synthworld.assurance.models import (
    EXECUTION_RECEIPT_SCHEMA_VERSION,
    RUN_RECEIPT_SCHEMA_VERSION,
    AdapterProvenance,
    ArtifactPhase,
    ArtifactSerialization,
    ConfigurationEntry,
    EvaluationStatus,
    EvidenceClaim,
    ExecutionReceipt,
    ExecutionStatus,
    RepositoryProvenance,
    RunReceiptManifest,
    SeedPopulation,
    SystemUnderTestProvenance,
    VersionBinding,
)
from synthworld.assurance.receipt import (
    EXECUTION_PATH,
    PRODUCT_INPUT_PATH,
    PRODUCT_OUTPUT_PATH,
    SOURCE_PUBLIC_PATH,
    ArtifactSpec,
    ProductRunner,
    PublicAdapter,
    ReceiptIntegrityError,
    canonical_json_bytes,
    capture_repository_provenance,
    describe_artifact,
    digest_file,
    run_product_stage,
    validate_manifest,
    write_canonical_model,
    write_manifest_last,
)
from synthworld.evaluation import EntityResolutionPrediction
from synthworld.models import SyntheticModel

AMBIGUITY_PAIR_SUBMISSION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"

SUBMISSION_CLUSTERS_PATH = "submission-clusters.json"
SUBMISSION_PAIRS_PATH = "submission-pairs.json"
MEMBERSHIP_TRUTH_PATH = "truth/memberships.json"
DISPOSITION_TRUTH_PATH = "truth/dispositions.json"
MEMBERSHIP_EVALUATION_PATH = "evaluation/membership.json"
DISPOSITION_EVALUATION_PATH = "evaluation/dispositions.json"

_ROLE_PATHS = {
    "source_public": SOURCE_PUBLIC_PATH,
    "product_input": PRODUCT_INPUT_PATH,
    "product_output": PRODUCT_OUTPUT_PATH,
    "execution": EXECUTION_PATH,
    "cluster_submission": SUBMISSION_CLUSTERS_PATH,
    "pair_submission": SUBMISSION_PAIRS_PATH,
    "membership_truth": MEMBERSHIP_TRUTH_PATH,
    "disposition_truth": DISPOSITION_TRUTH_PATH,
    "membership_evaluation": MEMBERSHIP_EVALUATION_PATH,
    "disposition_evaluation": DISPOSITION_EVALUATION_PATH,
}

MembershipTruthLoader = Callable[[], MembershipTruth]
DispositionTruthLoader = Callable[[], DispositionTruth]
OutputNormalizer = Callable[[bytes, PublicAmbiguityTask], EntityResolutionPrediction]


class AmbiguityPairSubmission(SyntheticModel):
    schema_version: Literal["1.0.0"] = AMBIGUITY_PAIR_SUBMISSION_SCHEMA_VERSION
    predictions: tuple[PairPrediction, ...] = Field(min_length=1)


class AmbiguityRunMetadata(SyntheticModel):
    """Consumer-neutral metadata supplied by a concrete product overlay."""

    benchmark_family: str = "synthworld.ambiguity"
    benchmark_version: str = AMBIGUITY_SCHEMA_VERSION
    product_input_schema_version: str = Field(min_length=1)
    product_output_schema_version: str = Field(min_length=1)
    callable_identifier: str = Field(min_length=1)
    generator_configuration: tuple[ConfigurationEntry, ...]
    event_schedule: tuple[ConfigurationEntry, ...] = ()
    synthworld: RepositoryProvenance
    adapter: AdapterProvenance
    system_under_test: SystemUnderTestProvenance
    seed_population: SeedPopulation
    evidence_claim: EvidenceClaim


def canonicalize_partition(
    prediction: EntityResolutionPrediction,
) -> EntityResolutionPrediction:
    clusters = tuple(
        sorted(
            (
                tuple(sorted(cluster, key=lambda record_id: record_id.int))
                for cluster in prediction.clusters
            ),
            key=lambda cluster: tuple(record_id.int for record_id in cluster),
        )
    )
    return EntityResolutionPrediction(clusters=clusters)


def _artifact_specs(metadata: AmbiguityRunMetadata) -> tuple[ArtifactSpec, ...]:
    canonical = ArtifactSerialization.CANONICAL_JSON_V1
    return (
        ArtifactSpec(
            path=SOURCE_PUBLIC_PATH,
            role="source_public",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=AMBIGUITY_SCHEMA_VERSION,
        ),
        ArtifactSpec(
            path=PRODUCT_INPUT_PATH,
            role="product_input",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=metadata.product_input_schema_version,
        ),
        ArtifactSpec(
            path=PRODUCT_OUTPUT_PATH,
            role="product_output",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=ArtifactSerialization.RAW_BYTES,
            schema_version=metadata.product_output_schema_version,
        ),
        ArtifactSpec(
            path=EXECUTION_PATH,
            role="execution",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=canonical,
            schema_version=EXECUTION_RECEIPT_SCHEMA_VERSION,
        ),
        ArtifactSpec(
            path=SUBMISSION_CLUSTERS_PATH,
            role="cluster_submission",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version="0.1.0",
        ),
        ArtifactSpec(
            path=SUBMISSION_PAIRS_PATH,
            role="pair_submission",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version=AMBIGUITY_PAIR_SUBMISSION_SCHEMA_VERSION,
        ),
        ArtifactSpec(
            path=MEMBERSHIP_TRUTH_PATH,
            role="membership_truth",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version=AMBIGUITY_SCHEMA_VERSION,
        ),
        ArtifactSpec(
            path=DISPOSITION_TRUTH_PATH,
            role="disposition_truth",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version=AMBIGUITY_SCHEMA_VERSION,
        ),
        ArtifactSpec(
            path=MEMBERSHIP_EVALUATION_PATH,
            role="membership_evaluation",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version="1.0.0",
        ),
        ArtifactSpec(
            path=DISPOSITION_EVALUATION_PATH,
            role="disposition_evaluation",
            phase=ArtifactPhase.EVALUATION,
            media_type="application/json",
            serialization=canonical,
            schema_version="1.0.0",
        ),
    )


def _schema_versions(specs: tuple[ArtifactSpec, ...]) -> tuple[VersionBinding, ...]:
    artifact_versions = tuple(
        VersionBinding(role=spec.role, version=spec.schema_version)
        for spec in specs
        if spec.schema_version is not None
    )
    return (
        VersionBinding(role="run_receipt", version=RUN_RECEIPT_SCHEMA_VERSION),
        *artifact_versions,
    )


def build_ambiguity_run_receipt(
    root: Path,
    *,
    source_public: bytes,
    membership_truth_loader: MembershipTruthLoader,
    disposition_truth_loader: DispositionTruthLoader,
    adapter: PublicAdapter,
    runner: ProductRunner,
    normalizer: OutputNormalizer,
    metadata: AmbiguityRunMetadata,
) -> RunReceiptManifest:
    """Execute product first, normalize completely, then load each truth separately."""

    public = PublicAmbiguityTask.model_validate_json(source_public)
    if source_public != canonical_json_bytes(public):
        raise ReceiptIntegrityError("source public input must use canonical JSON")

    execution = run_product_stage(
        root,
        source_public=source_public,
        adapter=adapter,
        runner=runner,
        adapter_provenance=metadata.adapter,
        callable_identifier=metadata.callable_identifier,
    )
    if execution.status is not ExecutionStatus.SUCCEEDED:
        raise ReceiptIntegrityError("a failed product execution cannot be evaluated")

    raw_output = (root / PRODUCT_OUTPUT_PATH).read_bytes()
    partition = canonicalize_partition(normalizer(raw_output, public))
    validate_ambiguity_partition(partition, public=public)
    pairs = AmbiguityPairSubmission(
        predictions=derive_ambiguity_pair_predictions(partition, public=public)
    )
    write_canonical_model(root / SUBMISSION_CLUSTERS_PATH, partition)
    write_canonical_model(root / SUBMISSION_PAIRS_PATH, pairs)

    # These calls deliberately occur only after both normalized submissions exist.
    memberships = membership_truth_loader()
    dispositions = disposition_truth_loader()
    write_canonical_model(root / MEMBERSHIP_TRUTH_PATH, memberships)
    write_canonical_model(root / DISPOSITION_TRUTH_PATH, dispositions)

    membership_report = evaluate_ambiguity_memberships(
        partition,
        public=public,
        truth=memberships,
    )
    disposition_report = evaluate_ambiguity_dispositions(
        pairs.predictions,
        public=public,
        truth=dispositions,
    )
    write_canonical_model(root / MEMBERSHIP_EVALUATION_PATH, membership_report)
    write_canonical_model(root / DISPOSITION_EVALUATION_PATH, disposition_report)

    specs = _artifact_specs(metadata)
    manifest = RunReceiptManifest(
        benchmark_family=metadata.benchmark_family,
        benchmark_version=metadata.benchmark_version,
        schema_versions=_schema_versions(specs),
        scoring_formula_versions=(
            VersionBinding(
                role="ambiguity_membership",
                version=AMBIGUITY_MEMBERSHIP_SCORING_VERSION,
            ),
            VersionBinding(
                role="ambiguity_evidence_disposition",
                version=AMBIGUITY_DISPOSITION_SCORING_VERSION,
            ),
        ),
        seed=public.corpus.seed,
        generator_configuration=metadata.generator_configuration,
        event_schedule=metadata.event_schedule,
        synthworld=metadata.synthworld,
        adapter=metadata.adapter,
        system_under_test=metadata.system_under_test,
        artifacts=tuple(describe_artifact(root, spec) for spec in specs),
        execution_status=execution.status,
        evaluation_status=EvaluationStatus.EVALUATED,
        seed_population=metadata.seed_population,
        evidence_claim=metadata.evidence_claim,
    )
    write_manifest_last(root, manifest)
    return validate_ambiguity_run_receipt(
        root,
        adapter=adapter,
        normalizer=normalizer,
    )


def _read_model[ModelT: BaseModel](
    root: Path, path: str, model: type[ModelT]
) -> ModelT:
    payload = (root / path).read_bytes()
    try:
        parsed = model.model_validate_json(payload)
    except ValueError as error:
        raise ReceiptIntegrityError(
            f"{path} does not match its declared schema"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise ReceiptIntegrityError(f"{path} is not canonical for its declared schema")
    return parsed


def validate_ambiguity_run_receipt(
    root: Path,
    *,
    adapter: PublicAdapter,
    normalizer: OutputNormalizer,
) -> RunReceiptManifest:
    """Replay all public transforms and both independent evaluations."""

    manifest = validate_manifest(root)
    role_paths = {item.role: item.path for item in manifest.artifacts}
    if role_paths != _ROLE_PATHS:
        raise ReceiptIntegrityError("ambiguity receipt roles or paths are incomplete")

    descriptors = {item.role: item for item in manifest.artifacts}
    declared_schemas = {item.role: item.version for item in manifest.schema_versions}
    expected_schemas = {"run_receipt": manifest.schema_version} | {
        item.role: item.schema_version
        for item in manifest.artifacts
        if item.schema_version is not None
    }
    if declared_schemas != expected_schemas:
        raise ReceiptIntegrityError("manifest schema bindings differ from artifacts")
    if {item.role: item.version for item in manifest.scoring_formula_versions} != {
        "ambiguity_membership": AMBIGUITY_MEMBERSHIP_SCORING_VERSION,
        "ambiguity_evidence_disposition": AMBIGUITY_DISPOSITION_SCORING_VERSION,
    }:
        raise ReceiptIntegrityError("manifest scoring formula bindings are incorrect")

    public = _read_model(root, SOURCE_PUBLIC_PATH, PublicAmbiguityTask)
    execution = _read_model(root, EXECUTION_PATH, ExecutionReceipt)
    partition = _read_model(root, SUBMISSION_CLUSTERS_PATH, EntityResolutionPrediction)
    pairs = _read_model(root, SUBMISSION_PAIRS_PATH, AmbiguityPairSubmission)
    memberships = _read_model(root, MEMBERSHIP_TRUTH_PATH, MembershipTruth)
    dispositions = _read_model(root, DISPOSITION_TRUTH_PATH, DispositionTruth)
    membership_report = _read_model(
        root, MEMBERSHIP_EVALUATION_PATH, AmbiguityMembershipMetrics
    )
    disposition_report = _read_model(
        root, DISPOSITION_EVALUATION_PATH, AmbiguityDispositionMetrics
    )

    if (
        execution.boundary != manifest.adapter.boundary
        or execution.callable_identifier == ""
        or execution.adapter_name != manifest.adapter.name
        or execution.adapter_version != manifest.adapter.version
        or execution.adapter_source_digest != manifest.adapter.source_digest
        or execution.status is not manifest.execution_status
    ):
        raise ReceiptIntegrityError("execution provenance differs from manifest")
    if (
        execution.source_public_digest != descriptors["source_public"].digest
        or execution.product_input_digest != descriptors["product_input"].digest
        or execution.product_output_digest != descriptors["product_output"].digest
    ):
        raise ReceiptIntegrityError("execution artifact digests differ from manifest")
    if manifest.evaluation_status is not EvaluationStatus.EVALUATED:
        raise ReceiptIntegrityError("a complete ambiguity receipt must be evaluated")
    if manifest.seed != public.corpus.seed:
        raise ReceiptIntegrityError("manifest seed differs from public input")
    if manifest.benchmark_version != public.schema_version:
        raise ReceiptIntegrityError("benchmark version differs from public input")

    source = (root / SOURCE_PUBLIC_PATH).read_bytes()
    expected_input = adapter(source)
    if expected_input != (root / PRODUCT_INPUT_PATH).read_bytes():
        raise ReceiptIntegrityError("product input is not the declared adapter output")
    raw_output = (root / PRODUCT_OUTPUT_PATH).read_bytes()
    try:
        expected_partition = canonicalize_partition(normalizer(raw_output, public))
        validate_ambiguity_partition(expected_partition, public=public)
    except ValueError as error:
        raise ReceiptIntegrityError(
            "raw product output cannot form a valid partition"
        ) from error
    if partition != expected_partition:
        raise ReceiptIntegrityError("cluster submission differs from normalized output")
    expected_pairs = AmbiguityPairSubmission(
        predictions=derive_ambiguity_pair_predictions(partition, public=public)
    )
    if pairs != expected_pairs:
        raise ReceiptIntegrityError(
            "pair submission differs from public-only projection"
        )

    try:
        expected_membership_report = evaluate_ambiguity_memberships(
            partition,
            public=public,
            truth=memberships,
        )
        expected_disposition_report = evaluate_ambiguity_dispositions(
            pairs.predictions,
            public=public,
            truth=dispositions,
        )
    except ValueError as error:
        raise ReceiptIntegrityError(
            "public input, submission, and truth artifacts do not belong together"
        ) from error
    if membership_report != expected_membership_report:
        raise ReceiptIntegrityError("membership evaluation does not replay exactly")
    if disposition_report != expected_disposition_report:
        raise ReceiptIntegrityError("disposition evaluation does not replay exactly")
    return manifest


def build_reference_ambiguity_run_receipt(
    root: Path,
    *,
    repository_root: Path,
) -> RunReceiptManifest:
    """Build the canonical reference-product receipt used by public CI."""

    public = load_golden_ambiguity_public_task()
    source_public = canonical_json_bytes(public)
    repository = capture_repository_provenance(repository_root, name="SynthWorld")
    reference_source = Path(reference_product.__file__)
    source_digest = digest_file(reference_source)
    adapter = AdapterProvenance(
        name="synthworld-reference-ambiguity-adaptation",
        version="1.0.0",
        source_digest=source_digest,
        boundary=reference_product.REFERENCE_BOUNDARY,
    )
    system = SystemUnderTestProvenance(
        name="SynthWorld exact-strong-identifier reference resolver",
        revision=repository.revision,
        package_or_executable_digest=source_digest,
        dependency_lock_digest=digest_file(repository_root / "uv.lock"),
        tree_state=repository.tree_state,
        tree_digest=repository.tree_digest,
        replayability="public implementation included in the SynthWorld source tree",
    )
    metadata = AmbiguityRunMetadata(
        product_input_schema_version=reference_product.REFERENCE_PRODUCT_SCHEMA_VERSION,
        product_output_schema_version=reference_product.REFERENCE_PRODUCT_SCHEMA_VERSION,
        callable_identifier=reference_product.REFERENCE_CALLABLE,
        generator_configuration=(
            ConfigurationEntry(
                name="generator",
                value="synthworld.ambiguity_generator.generate_ambiguity_benchmark",
            ),
            ConfigurationEntry(name="configuration", value="canonical defaults"),
        ),
        synthworld=repository,
        adapter=adapter,
        system_under_test=system,
        seed_population=SeedPopulation(
            seeds=(public.corpus.seed,),
            description="the single hand-reviewed canonical ambiguity fixture",
        ),
        evidence_claim=EvidenceClaim.CANONICAL_CONFORMANCE,
    )
    return build_ambiguity_run_receipt(
        root,
        source_public=source_public,
        membership_truth_loader=load_golden_ambiguity_membership_truth,
        disposition_truth_loader=load_golden_ambiguity_disposition_truth,
        adapter=reference_product.adapt_public_ambiguity,
        runner=reference_product.run_reference_product,
        normalizer=reference_product.normalize_reference_output,
        metadata=metadata,
    )


__all__ = [
    "AMBIGUITY_PAIR_SUBMISSION_SCHEMA_VERSION",
    "DISPOSITION_EVALUATION_PATH",
    "DISPOSITION_TRUTH_PATH",
    "MEMBERSHIP_EVALUATION_PATH",
    "MEMBERSHIP_TRUTH_PATH",
    "SUBMISSION_CLUSTERS_PATH",
    "SUBMISSION_PAIRS_PATH",
    "AmbiguityPairSubmission",
    "AmbiguityRunMetadata",
    "DispositionTruthLoader",
    "MembershipTruthLoader",
    "OutputNormalizer",
    "build_ambiguity_run_receipt",
    "build_reference_ambiguity_run_receipt",
    "canonicalize_partition",
    "validate_ambiguity_run_receipt",
]
