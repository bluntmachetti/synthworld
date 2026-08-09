"""Package-resource and publication integrity gates for both C08 v2 lineages."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from synthworld.agentic.c08_v2 import (
    c08_frozen_artifact_set_digest,
    load_c08_v2_frozen_tree,
    load_packaged_c08_v2_benchmark,
)
from synthworld.agentic.enterprise.c08_v2 import (
    C08EvaluatorTruthV2,
    C08FrozenManifestV2,
    C08PublicInputV2,
)
from synthworld.agentic.enterprise.c08_v2.projection import (
    c08_public_input_digest,
    validate_c08_truth_against_public,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
)

_ASTERIA_FILES = frozenset(
    {
        "evaluator/c08-asteria-evaluator.json",
        "evaluator/manifest.json",
        "manifest.json",
        "public/c08-asteria-public.json",
        "public/manifest.json",
    }
)
_ENTERPRISE_FILES = frozenset(
    {
        "SHA256SUMS",
        "evaluator/truth.json",
        "manifest.json",
        "public/public-input.json",
    }
)
_ASTERIA_V1_DIGESTS = {
    "evaluator_artifact_set_digest": (
        "3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f"
    ),
    "public_artifact_set_digest": (
        "9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594"
    ),
}
_ENTERPRISE_V1_EXAMPLE_DIGESTS = {
    "enterprise-agentic-evaluator.json": (
        "9fbf331d8a037e444d3b756007ce1ab2426b3cd39ab46461cb1343bbccbfb723"
    ),
    "enterprise-agentic-metrics.json": (
        "983f5abb9ee17b91dbfec39fd029c8ebce3ed1de738f500a32dc01f4b61864c7"
    ),
    "enterprise-agentic-prediction.json": (
        "c8af6e28c4d7e47f86969cff9a669081414414c498abc9ae1cd46ccb5252a2bd"
    ),
    "enterprise-agentic-public-input.json": (
        "ca581923b57927c9595a6e3f44e783bcdc02bd329f6bd9b79eee11ea034f28a3"
    ),
}
_ASTERIA_ROOT_DIGEST = (
    "a1c72b05a391416ccfacf6eb4bc18ecca342f834b007ee9b1bb0c26a795d21e8"
)
_ENTERPRISE_CHECKSUM_ROOT = (
    "3ad3c6a1dd226d6a62c273a291032b9309bd5fa627540beac8507347fe1e0dcb"
)


def _resource_files(root: Traversable) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}

    def visit(node: Traversable, prefix: str = "") -> None:
        for child in node.iterdir():
            relative = f"{prefix}/{child.name}" if prefix else child.name
            if child.is_dir():
                visit(child, relative)
            else:
                assert child.is_file()
                payloads[relative] = child.read_bytes()

    visit(root)
    return payloads


def _assert_canonical_files(payloads: dict[str, bytes]) -> None:
    for path, payload in payloads.items():
        assert payload.decode("utf-8")
        assert b"\r" not in payload, path
        assert payload.endswith(b"\n"), path
        assert not payload.endswith(b"\n\n"), path
        if path.endswith(".json"):
            assert canonical_json_value_bytes(json.loads(payload)) == payload


def _checksum_rows(payload: bytes) -> dict[str, str]:
    rows = tuple(row.split("  ", 1) for row in payload.decode("ascii").splitlines())
    assert tuple(path for _, path in rows) == tuple(sorted(path for _, path in rows))
    assert len({path for _, path in rows}) == len(rows)
    assert all(len(digest) == 64 for digest, _ in rows)
    return {path: digest for digest, path in rows}


def test_packaged_resource_trees_have_exact_canonical_inventories() -> None:
    benchmarks = files("synthworld.benchmarks")
    asteria = _resource_files(benchmarks.joinpath("asteria-agentic-c08-v2"))
    enterprise = _resource_files(benchmarks.joinpath("enterprise-agentic-c08-v2"))

    assert set(asteria) == _ASTERIA_FILES
    assert set(enterprise) == _ENTERPRISE_FILES
    _assert_canonical_files(asteria)
    _assert_canonical_files(enterprise)


def test_asteria_package_loader_validates_all_digest_roots() -> None:
    root = files("synthworld.benchmarks").joinpath("asteria-agentic-c08-v2")
    payloads = _resource_files(root)
    loaded = load_c08_v2_frozen_tree(root)

    assert loaded == load_packaged_c08_v2_benchmark()
    assert loaded.root_artifact_set_digest == _ASTERIA_ROOT_DIGEST
    assert loaded.root_artifact_set_digest == c08_frozen_artifact_set_digest(
        payloads,
        excluded_paths=("manifest.json",),
    )
    assert loaded.public_input_digest == hashlib.sha256(
        payloads["public/c08-asteria-public.json"]
    ).hexdigest()


def test_enterprise_package_resources_validate_checksum_root_and_bindings() -> None:
    root = files("synthworld.benchmarks").joinpath("enterprise-agentic-c08-v2")
    payloads = _resource_files(root)
    manifest_payload = payloads["manifest.json"]
    public_payload = payloads["public/public-input.json"]
    evaluator_payload = payloads["evaluator/truth.json"]
    manifest = C08FrozenManifestV2.model_validate_json(manifest_payload)
    public = C08PublicInputV2.model_validate_json(public_payload)
    evaluator = C08EvaluatorTruthV2.model_validate_json(evaluator_payload)

    checksums = _checksum_rows(payloads["SHA256SUMS"])
    checksummed_payloads = {
        path: payload for path, payload in payloads.items() if path != "SHA256SUMS"
    }
    assert checksums == {
        path: hashlib.sha256(payload).hexdigest()
        for path, payload in checksummed_payloads.items()
    }
    assert hashlib.sha256(payloads["SHA256SUMS"]).hexdigest() == (
        _ENTERPRISE_CHECKSUM_ROOT
    )
    assert canonical_json_bytes(manifest) == manifest_payload
    assert canonical_json_bytes(public) == public_payload
    assert canonical_json_bytes(evaluator) == evaluator_payload
    assert manifest.public_input_digest == evaluator.public_input_digest
    assert manifest.public_input_digest == c08_public_input_digest(public)
    assert {
        artifact.path: (artifact.byte_size, artifact.sha256)
        for artifact in manifest.public_inventory + manifest.evaluator_inventory
    } == {
        path: (len(payload), hashlib.sha256(payload).hexdigest())
        for path, payload in checksummed_payloads.items()
        if path != "manifest.json"
    }
    validate_c08_truth_against_public(public, evaluator)


def test_public_and_evaluator_package_resources_remain_physically_separate() -> None:
    benchmarks = files("synthworld.benchmarks")
    asteria = _resource_files(benchmarks.joinpath("asteria-agentic-c08-v2"))
    enterprise = _resource_files(benchmarks.joinpath("enterprise-agentic-c08-v2"))

    assert {path for path in asteria if path.startswith("public/")}.isdisjoint(
        path for path in asteria if path.startswith("evaluator/")
    )
    assert {path for path in enterprise if path.startswith("public/")}.isdisjoint(
        path for path in enterprise if path.startswith("evaluator/")
    )
    asteria_public = b"".join(
        payload for path, payload in asteria.items() if path.startswith("public/")
    )
    enterprise_public = b"".join(
        payload for path, payload in enterprise.items() if path.startswith("public/")
    )
    assert b"required_observation_ids" not in asteria_public
    assert b"scenario_kind" not in asteria_public
    assert b"required_evidence_ids" not in enterprise_public
    assert b'"outcome"' not in enterprise_public
    assert not any(
        "submission" in path or "report" in path
        for path in _ASTERIA_FILES | _ENTERPRISE_FILES
    )


def test_v1_artifact_identities_are_preserved() -> None:
    benchmarks = files("synthworld.benchmarks")
    asteria_checksums = json.loads(
        benchmarks.joinpath(
            "asteria-agentic-v1/evaluator/checksums.json"
        ).read_bytes()
    )
    for field, digest in _ASTERIA_V1_DIGESTS.items():
        assert asteria_checksums[field] == digest

    examples = Path("enterprise-identity-access-contract/examples")
    for filename, digest in _ENTERPRISE_V1_EXAMPLE_DIGESTS.items():
        assert hashlib.sha256((examples / filename).read_bytes()).hexdigest() == digest
