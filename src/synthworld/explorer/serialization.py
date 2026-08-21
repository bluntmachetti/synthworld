from __future__ import annotations

import hashlib
import json

from synthworld.explorer.models import (
    ExplorerEnterpriseGeneratedLayoutV1,
    ExplorerEnterpriseGeneratedProjectionV1,
    ExplorerEvaluatorOverlayV1,
    ExplorerLayoutManifestV1,
    ExplorerLayoutManifestV2,
    ExplorerPublicProjectionV1,
)

type ExplorerArtifact = (
    ExplorerPublicProjectionV1
    | ExplorerEnterpriseGeneratedProjectionV1
    | ExplorerEvaluatorOverlayV1
    | ExplorerLayoutManifestV1
    | ExplorerLayoutManifestV2
    | ExplorerEnterpriseGeneratedLayoutV1
)


def canonical_json_bytes(artifact: ExplorerArtifact) -> bytes:
    """Serialize one Explorer artifact as canonical UTF-8 JSON plus one LF."""

    text = json.dumps(
        artifact.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{text}\n".encode()


def explorer_digest(artifact: ExplorerArtifact) -> str:
    """Return the SHA-256 digest of the canonical serialized artifact."""

    return hashlib.sha256(canonical_json_bytes(artifact)).hexdigest()
