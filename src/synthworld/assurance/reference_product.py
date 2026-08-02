"""A deterministic public-only product used to prove the receipt protocol."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field

from synthworld.ambiguity import PublicAmbiguityTask
from synthworld.assurance.receipt import canonical_json_bytes
from synthworld.connection import PublicIdentityAttributeKind, PublicIdentityRecord
from synthworld.evaluation import EntityResolutionPrediction
from synthworld.models import SyntheticModel

REFERENCE_PRODUCT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
REFERENCE_BOUNDARY = "synthworld.reference.exact-strong-identifier.resolve/v1"
REFERENCE_CALLABLE = "synthworld.assurance.reference_product.run_reference_product"

_STRONG_KINDS = frozenset(
    {
        PublicIdentityAttributeKind.EMAIL,
        PublicIdentityAttributeKind.PHONE,
        PublicIdentityAttributeKind.USERNAME,
    }
)


class ReferenceResolverInput(SyntheticModel):
    """The records exposed to the reference resolver, with no task or truth labels."""

    schema_version: Literal["1.0.0"] = REFERENCE_PRODUCT_SCHEMA_VERSION
    records: tuple[PublicIdentityRecord, ...] = Field(min_length=1)


class ReferenceResolverOutput(SyntheticModel):
    """Raw reference-product clusters before consumer-neutral normalization."""

    schema_version: Literal["1.0.0"] = REFERENCE_PRODUCT_SCHEMA_VERSION
    clusters: tuple[tuple[UUID, ...], ...]


def adapt_public_ambiguity(source_public: bytes) -> bytes:
    """Map the public task to the reference resolver's exact input contract."""

    public = PublicAmbiguityTask.model_validate_json(source_public)
    product_input = ReferenceResolverInput(records=public.corpus.identity_records)
    return canonical_json_bytes(product_input)


def _strong_values(record: PublicIdentityRecord) -> frozenset[tuple[str, str]]:
    return frozenset(
        (attribute.kind.value, attribute.value)
        for attribute in record.attributes
        if attribute.kind in _STRONG_KINDS
    )


def resolve_reference(input_data: ReferenceResolverInput) -> ReferenceResolverOutput:
    """Cluster transitively on exact shared email, phone, or username values."""

    records = tuple(sorted(input_data.records, key=lambda item: item.id.int))
    parent = {record.id: record.id for record in records}

    def find(record_id: UUID) -> UUID:
        while parent[record_id] != record_id:
            parent[record_id] = parent[parent[record_id]]
            record_id = parent[record_id]
        return record_id

    values = {record.id: _strong_values(record) for record in records}
    for left, right in combinations(records, 2):
        if values[left.id] & values[right.id]:
            left_root, right_root = find(left.id), find(right.id)
            if left_root != right_root:
                first, second = sorted(
                    (left_root, right_root), key=lambda item: item.int
                )
                parent[second] = first

    grouped: dict[UUID, list[UUID]] = {}
    for record in records:
        grouped.setdefault(find(record.id), []).append(record.id)
    clusters = tuple(
        tuple(sorted(members, key=lambda item: item.int))
        for _root, members in sorted(grouped.items(), key=lambda item: item[0].int)
    )
    return ReferenceResolverOutput(clusters=clusters)


def run_reference_product(input_path: Path, output_path: Path) -> int:
    """Read only the supplied input path and write only the supplied output path."""

    input_data = ReferenceResolverInput.model_validate_json(input_path.read_bytes())
    output = resolve_reference(input_data)
    output_path.write_bytes(canonical_json_bytes(output))
    return 0


def normalize_reference_output(
    raw_output: bytes,
    _public: PublicAmbiguityTask,
) -> EntityResolutionPrediction:
    """Normalize raw clusters without consulting either evaluator truth."""

    output = ReferenceResolverOutput.model_validate_json(raw_output)
    return EntityResolutionPrediction(clusters=output.clusters)


__all__ = [
    "REFERENCE_BOUNDARY",
    "REFERENCE_CALLABLE",
    "REFERENCE_PRODUCT_SCHEMA_VERSION",
    "ReferenceResolverInput",
    "ReferenceResolverOutput",
    "adapt_public_ambiguity",
    "normalize_reference_output",
    "resolve_reference",
    "run_reference_product",
]
