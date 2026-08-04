"""Canonical bytes, private digests, and stable enterprise identifiers."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from uuid import UUID, uuid5

from pydantic import BaseModel

from synthworld.enterprise.models import (
    ENTERPRISE_BLUEPRINT_SCHEMA_VERSION,
    ENTERPRISE_COMPILER_VERSION,
    EnterpriseIdentityAccessBlueprintV1,
    EnterprisePrivateCompilationReceiptV1,
    SyntheticDigestV1,
)

ENTERPRISE_BLUEPRINT_NAMESPACE_V1 = UUID("b90f6f38-9346-5d77-a05c-f6a5463f5b6e")
ENTERPRISE_TENANT_NAMESPACE_V1 = UUID("1c7e4678-4d5b-5ecf-a811-f1f40f109bda")
ENTERPRISE_ORGANISATION_NAMESPACE_V1 = UUID("57eb1b7f-18b5-505b-bc67-b3760eb84d73")
ENTERPRISE_UNIT_NAMESPACE_V1 = UUID("ca096205-d237-51fe-bbd2-790435cd0cd1")
ENTERPRISE_PRINCIPAL_NAMESPACE_V1 = UUID("50fe6e3c-f4cc-5001-b9d6-eeb9aa265a2a")
ENTERPRISE_ACCOUNT_NAMESPACE_V1 = UUID("595caa50-f1b8-5b82-af6f-f588ab50a65b")
ENTERPRISE_GROUP_NAMESPACE_V1 = UUID("40561413-dd6f-592b-b9c6-7d4660c23a98")
ENTERPRISE_ROLE_NAMESPACE_V1 = UUID("b5777045-d82c-5b37-89a3-4cf5420287f3")
ENTERPRISE_TARGET_NAMESPACE_V1 = UUID("5ba286e5-a133-5a31-b082-b41c7f31e910")
ENTERPRISE_PERMISSION_NAMESPACE_V1 = UUID("f5ffb93a-332d-5474-80a3-c7ee32af86b7")
ENTERPRISE_ACCESS_ATOM_NAMESPACE_V1 = UUID("6650da98-7fb1-5236-bb2a-26e1ad5de0f2")
ENTERPRISE_RELATIONSHIP_ANCHOR_NAMESPACE_V1 = UUID(
    "a4741778-b97e-5484-a706-21755fa88b63"
)


def encode_parts(parts: Sequence[str]) -> str:
    """Encode NFC strings injectively using UTF-8 byte lengths."""

    encoded: list[str] = []
    for part in parts:
        normalised = unicodedata.normalize("NFC", part)
        if not normalised:
            raise ValueError("identifier components must be nonempty")
        encoded.append(f"{len(normalised.encode('utf-8'))}:{normalised}")
    return "".join(encoded)


def blueprint_namespace_uuid(id_namespace_salt: str) -> UUID:
    return uuid5(
        ENTERPRISE_BLUEPRINT_NAMESPACE_V1,
        encode_parts((ENTERPRISE_BLUEPRINT_SCHEMA_VERSION, id_namespace_salt)),
    )


def stable_enterprise_id(
    namespace: UUID,
    blueprint_namespace: UUID,
    *logical_key_components: str,
) -> str:
    return str(
        uuid5(
            namespace,
            encode_parts((str(blueprint_namespace), *logical_key_components)),
        )
    )


def canonical_json_bytes(model: BaseModel) -> bytes:
    return canonical_json_value_bytes(model.model_dump(mode="json"))


def canonical_json_value_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def synthetic_digest(payload: bytes) -> SyntheticDigestV1:
    return SyntheticDigestV1(value=hashlib.sha256(payload).hexdigest())


def blueprint_semantic_digest(
    blueprint: EnterpriseIdentityAccessBlueprintV1,
) -> str:
    payload = canonical_json_bytes(blueprint)
    prefix = encode_parts(
        (ENTERPRISE_BLUEPRINT_SCHEMA_VERSION, ENTERPRISE_COMPILER_VERSION)
    ).encode("utf-8")
    return hashlib.sha256(prefix + payload).hexdigest()


def source_artifact_set_digest(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(files):
        normalised_name = unicodedata.normalize("NFC", name)
        payload = files[name]
        digest.update(encode_parts((normalised_name, str(len(payload)))).encode())
        digest.update(payload)
    return digest.hexdigest()


def build_private_compilation_receipt(
    *,
    blueprint: EnterpriseIdentityAccessBlueprintV1,
    source_files: Mapping[str, bytes],
    publication_consent: bool,
) -> EnterprisePrivateCompilationReceiptV1:
    if not publication_consent:
        raise ValueError("private digests require explicit publication consent")
    return EnterprisePrivateCompilationReceiptV1(
        publication_consent=True,
        blueprint_semantic_digest=blueprint_semantic_digest(blueprint),
        source_artifact_set_digest=source_artifact_set_digest(source_files),
    )


__all__ = [
    "ENTERPRISE_ACCESS_ATOM_NAMESPACE_V1",
    "ENTERPRISE_ACCOUNT_NAMESPACE_V1",
    "ENTERPRISE_BLUEPRINT_NAMESPACE_V1",
    "ENTERPRISE_GROUP_NAMESPACE_V1",
    "ENTERPRISE_ORGANISATION_NAMESPACE_V1",
    "ENTERPRISE_PERMISSION_NAMESPACE_V1",
    "ENTERPRISE_PRINCIPAL_NAMESPACE_V1",
    "ENTERPRISE_RELATIONSHIP_ANCHOR_NAMESPACE_V1",
    "ENTERPRISE_ROLE_NAMESPACE_V1",
    "ENTERPRISE_TARGET_NAMESPACE_V1",
    "ENTERPRISE_TENANT_NAMESPACE_V1",
    "ENTERPRISE_UNIT_NAMESPACE_V1",
    "blueprint_namespace_uuid",
    "blueprint_semantic_digest",
    "build_private_compilation_receipt",
    "canonical_json_bytes",
    "canonical_json_value_bytes",
    "encode_parts",
    "source_artifact_set_digest",
    "stable_enterprise_id",
    "synthetic_digest",
]
