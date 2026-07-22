"""Run public-only baseline adapters for all four SynthWorld evaluation tasks.

This example creates predictions from only the data a real system is allowed to
see, then lets each evaluator load its separate truth. It demonstrates:
- Exact-span PII extraction (using naive regex rules over public pages);
- Entity resolution (using exact shared email or username values);
- Relationship inference (requiring reciprocal public associations);
- Risk calibration (using breach severity only).

Run with:

    uv run python examples/evaluate_all.py

Add ``--predictions-dir predictions`` to write four JSON files that can be
passed directly to ``synthworld evaluate``.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from synthworld.connection import (
    PublicAssociationKind,
    PublicConnectionCorpus,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    PublicTruthRelationshipKind,
)
from synthworld.connection_generator import (
    generate_adversarial_connection_benchmark,
    generate_relationship_connection_benchmark,
)
from synthworld.evaluation import (
    EntityResolutionPrediction,
    ExtractionPagePrediction,
    ExtractionPredictionSet,
    PredictedRelationship,
    PredictedSpan,
    RelationshipPrediction,
    RiskCasePrediction,
    RiskPrediction,
    evaluate_entity_resolution,
    evaluate_extraction,
    evaluate_relationship_inference,
    evaluate_risk_calibration,
)
from synthworld.exposures import DataClass
from synthworld.extraction_generator import generate_extraction_benchmark
from synthworld.models import SyntheticModel
from synthworld.risk import band_for_score, severity_points
from synthworld.risk_generator import generate_risk_benchmark

_EMAIL = re.compile(r"[a-z0-9][a-z0-9._%+-]*@example\.test")
_PHONE = re.compile(r"\+1-[0-9]{3}-555-01[0-9]{2}")
_NATIONAL_ID = re.compile(r"SYN-[0-9]+")
_STRONG_IDENTIFIERS = {
    PublicIdentityAttributeKind.EMAIL,
    PublicIdentityAttributeKind.USERNAME,
}


def run_extraction_eval(seed: int, persona_count: int) -> ExtractionPredictionSet:
    print("\n=== Evaluating Extraction ===")
    benchmark = generate_extraction_benchmark(seed=seed, persona_count=persona_count)

    pages: list[ExtractionPagePrediction] = []
    for page in benchmark.public.pages:
        spans: list[PredictedSpan] = []
        for pattern, data_class in (
            (_EMAIL, DataClass.EMAIL),
            (_PHONE, DataClass.PHONE),
            (_NATIONAL_ID, DataClass.NATIONAL_ID),
        ):
            for match in pattern.finditer(page.content):
                spans.append(
                    PredictedSpan(
                        data_class=data_class,
                        start=match.start(),
                        end=match.end(),
                    )
                )
        pages.append(
            ExtractionPagePrediction(
                source_type=page.source_type,
                source_record_id=page.source_record_id,
                spans=tuple(spans),
            )
        )

    preds = ExtractionPredictionSet(predictions=tuple(pages))
    report = evaluate_extraction(preds, seed=seed, persona_count=persona_count)
    print(report.model_dump_json(indent=2))
    return preds


def run_entity_resolution_eval(seed: int) -> EntityResolutionPrediction:
    print("\n=== Evaluating Entity Resolution ===")
    benchmark = generate_adversarial_connection_benchmark(seed=seed)

    preds = EntityResolutionPrediction(
        clusters=_exact_identifier_clusters(benchmark.public.identity_records)
    )
    report = evaluate_entity_resolution(preds, seed=seed)
    print(report.model_dump_json(indent=2))
    return preds


def run_relationship_eval(seed: int, persona_count: int) -> RelationshipPrediction:
    print("\n=== Evaluating Relationship Inference ===")
    benchmark = generate_relationship_connection_benchmark(
        seed=seed, persona_count=persona_count
    )

    preds = RelationshipPrediction(edges=_reciprocal_relationships(benchmark.public))
    report = evaluate_relationship_inference(
        preds, seed=seed, persona_count=persona_count
    )
    print(report.model_dump_json(indent=2))
    return preds


def run_risk_eval(seed: int, persona_count: int) -> RiskPrediction:
    print("\n=== Evaluating Risk Calibration ===")
    benchmark = generate_risk_benchmark(seed=seed, persona_count=persona_count)

    preds = RiskPrediction(
        cases=tuple(
            RiskCasePrediction(
                case_id=case.id,
                band=band_for_score(score),
                score=score,
            )
            for case in benchmark.public.cases
            for score in (
                min(
                    100,
                    sum(severity_points(item.severity) for item in case.breaches),
                ),
            )
        )
    )
    report = evaluate_risk_calibration(preds, seed=seed, persona_count=persona_count)
    print(report.model_dump_json(indent=2))
    return preds


def _exact_identifier_clusters(
    records: tuple[PublicIdentityRecord, ...],
) -> tuple[tuple[UUID, ...], ...]:
    """Partition records by exact shared email or username, retaining singletons."""

    parent = {record.id: record.id for record in records}

    def find(record_id: UUID) -> UUID:
        root = record_id
        while parent[root] != root:
            root = parent[root]
        while parent[record_id] != root:
            parent[record_id], record_id = root, parent[record_id]
        return root

    def join(left: UUID, right: UUID) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    first_record_by_value: dict[tuple[str, str], UUID] = {}
    for record in records:
        for attribute in record.attributes:
            if attribute.kind not in _STRONG_IDENTIFIERS:
                continue
            key = (attribute.kind.value, attribute.value)
            first = first_record_by_value.setdefault(key, record.id)
            join(first, record.id)

    by_root: dict[UUID, list[UUID]] = {}
    for record in records:
        by_root.setdefault(find(record.id), []).append(record.id)
    clusters = (
        tuple(sorted(items, key=lambda item: item.int)) for items in by_root.values()
    )
    return tuple(sorted(clusters, key=lambda items: items[0].int))


def _reciprocal_relationships(
    corpus: PublicConnectionCorpus,
) -> tuple[PredictedRelationship, ...]:
    """Infer an edge only from a reciprocal pair of public associations."""

    reference_to_record: dict[str, UUID] = {}
    for record in corpus.identity_records:
        for attribute in record.attributes:
            if attribute.kind in {
                PublicIdentityAttributeKind.FULL_ADDRESS,
                PublicIdentityAttributeKind.SOCIAL_PROFILE,
            }:
                reference_to_record[attribute.value] = record.id

    association_by_direction = {
        (item.kind, item.source_reference, item.target_reference): item
        for item in corpus.association_records
    }
    edges: dict[
        tuple[UUID, UUID, PublicTruthRelationshipKind], PredictedRelationship
    ] = {}
    for association in corpus.association_records:
        reverse = association_by_direction.get(
            (
                association.kind,
                association.target_reference,
                association.source_reference,
            )
        )
        source = reference_to_record.get(association.source_reference)
        target = reference_to_record.get(association.target_reference)
        if reverse is None or source is None or target is None:
            continue
        source, target = (
            (source, target) if source.int <= target.int else (target, source)
        )
        kind = (
            PublicTruthRelationshipKind.NEIGHBOR
            if association.kind is PublicAssociationKind.PROPERTY_ADJACENCY
            else PublicTruthRelationshipKind.SOCIAL
        )
        key = (source, target, kind)
        edges[key] = PredictedRelationship(
            source_record_id=source,
            target_record_id=target,
            kind=kind,
            evidence_association_ids=tuple(
                sorted((association.id, reverse.id), key=lambda item: item.int)
            ),
        )
    return tuple(
        edges[key]
        for key in sorted(
            edges, key=lambda item: (item[0].int, item[1].int, item[2].value)
        )
    )


def _write_predictions(
    directory: Path,
    predictions: tuple[tuple[str, SyntheticModel], ...],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, prediction in predictions:
        path = directory / f"{name}.json"
        path.write_text(prediction.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluate_all")
    parser.add_argument("--seed", type=int, default=20_260_719)
    parser.add_argument("--persona-count", type=int, default=10)
    parser.add_argument(
        "--predictions-dir",
        type=Path,
        help="optionally write one CLI-ready prediction JSON file per task",
    )
    args = parser.parse_args(argv)

    predictions: tuple[tuple[str, SyntheticModel], ...] = (
        ("extraction", run_extraction_eval(args.seed, args.persona_count)),
        ("entity-resolution", run_entity_resolution_eval(args.seed)),
        ("relationship", run_relationship_eval(args.seed, args.persona_count)),
        ("risk", run_risk_eval(args.seed, args.persona_count)),
    )
    if args.predictions_dir is not None:
        _write_predictions(args.predictions_dir, predictions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
