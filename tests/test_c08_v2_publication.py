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
from synthworld.agentic.enterprise.c08_v2 import load_packaged_frozen_benchmark
from synthworld.enterprise.canonical import canonical_json_value_bytes

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
_ASTERIA_V1_PUBLIC_FILES = (
    "organisation.json",
    "principals.jsonl",
    "agents.jsonl",
    "runtimes.jsonl",
    "resources.jsonl",
    "public_credentials.jsonl",
    "public_delegations.jsonl",
    "public_events.jsonl",
    "tool_schemas/procurement-tools.json",
    "scenarios/procurement-delegation.json",
)
_ASTERIA_V1_EVALUATOR_FILES = (
    "canonical_bindings.json",
    "authority_truth.jsonl",
    "cases.jsonl",
    "expected_decisions.jsonl",
    "expected_side_effects.jsonl",
    "expected_provenance.jsonl",
    "evidence_epochs.jsonl",
)
_ASTERIA_V1_PUBLIC_MANIFEST = {
    "artifact_set_digest": _ASTERIA_V1_DIGESTS["public_artifact_set_digest"],
    "artifacts": {
        "agents.jsonl": (
            "3e4884bdcde3ec9e2fbdc958c5fcc587c54e733273afeb4df00e64fac4e20279"
        ),
        "organisation.json": (
            "bc29c6aa8e342e72c76e9ae58ca5e101beeb2e69f7956bf878890f714af29c08"
        ),
        "principals.jsonl": (
            "58163ce487ec8a0e986cac5380706ecac352819a1706d265518fbb515955874c"
        ),
        "public_credentials.jsonl": (
            "59e116652a078eb46b5e3ea1946d3b78a00b3945d2809a4af25c8875a5f42a93"
        ),
        "public_delegations.jsonl": (
            "476df49d66e774c0303370739e9e5bc8011e66985652d14664c581535c743957"
        ),
        "public_events.jsonl": (
            "ab920f3866aaa86deeadbbe4c5882170205c12d8d2c1a0fa638c0415aa0ec6eb"
        ),
        "resources.jsonl": (
            "866a24fdf59e2bbd957717af9c0402a629b341046205d953724a15bddef19266"
        ),
        "runtimes.jsonl": (
            "d1d08d2b060e6b900029bc180a266e41cc3e4da7938fd27fb8c2577f27298704"
        ),
        "scenarios/procurement-delegation.json": (
            "37f09e82146a249cc5a7f02ad3ec5abf95724d2eaf4dbc40da3b969f9ea88ec9"
        ),
        "tool_schemas/procurement-tools.json": (
            "11d22e49cb95b52d294d832d5df145e86c492fd16c3781f21c5e664b4ef6c6c8"
        ),
    },
    "oracle_free": True,
    "schema_version": "1.0.0",
    "seed": 20260719,
    "world_id": "asteria-agentic",
    "world_version": "1.0.0",
}
_ASTERIA_V1_EVALUATOR_CHECKSUMS = {
    "checksum_scheme": "sha256-artifact-set-v1",
    "evaluator_artifact_set_digest": _ASTERIA_V1_DIGESTS[
        "evaluator_artifact_set_digest"
    ],
    "evaluator_artifacts": {
        "authority_truth.jsonl": (
            "093efedf08d1db33e04335bd846a50b58bb8222bb2395dca8358d8e2820536b0"
        ),
        "canonical_bindings.json": (
            "9ed29aa54a1c05d9ae2b62797059a85fb96c6710b762568465f98222fc844cdf"
        ),
        "cases.jsonl": (
            "a44d28143128da2051c665e8ae421e1b2d3af0cb2e364d42af099f0ecc8b35a5"
        ),
        "evidence_epochs.jsonl": (
            "e685ee9b0334eb5c2ae5905e930d6302160e525634eb92f0c4334a8a5c9d15a8"
        ),
        "expected_decisions.jsonl": (
            "49e68d770b3a68666d193d1304d0eaebc67eb689c66ff4697ba59db6be41be49"
        ),
        "expected_provenance.jsonl": (
            "05fedec838d2569ebc4ebbe7d9af8ab5757faf6bcfe1858ecae9d06423553fa1"
        ),
        "expected_side_effects.jsonl": (
            "d5b4aeac96bface4331622c6eba307fad8b2cc5044fcdc2cfef8622c3ff61079"
        ),
    },
    "public_artifact_set_digest": _ASTERIA_V1_DIGESTS["public_artifact_set_digest"],
    "schema_version": "1.0.0",
}
_ASTERIA_V1_FILES = frozenset(
    {f"public/{path}" for path in (*_ASTERIA_V1_PUBLIC_FILES, "manifest.json")}
    | {f"evaluator/{path}" for path in (*_ASTERIA_V1_EVALUATOR_FILES, "checksums.json")}
)
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
    "5fc98eafd7435580ed50581adacd3cbbecae45c02295f3733bdc87da3d59629a"
)
_ENTERPRISE_CHECKSUM_ROOT = (
    "a0b012bda161183ce925ca75b754cd7cbae942bf7fb4787a7b1258293210e123"
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


def _v1_metadata_bytes(document: dict[str, object]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


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
    assert (
        loaded.public_input_digest
        == hashlib.sha256(payloads["public/c08-asteria-public.json"]).hexdigest()
    )


def test_enterprise_package_resources_validate_checksum_root_and_bindings() -> None:
    root = files("synthworld.benchmarks").joinpath("enterprise-agentic-c08-v2")
    payloads = _resource_files(root)
    loaded = load_packaged_frozen_benchmark()

    assert hashlib.sha256(payloads["SHA256SUMS"]).hexdigest() == (
        _ENTERPRISE_CHECKSUM_ROOT
    )
    assert loaded.manifest.public_input_digest == loaded.evaluator.public_input_digest


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
    asteria = benchmarks.joinpath("asteria-agentic-v1")
    tree = _resource_files(asteria)
    assert set(tree) == _ASTERIA_V1_FILES
    public_payloads = {
        path: tree[f"public/{path}"] for path in _ASTERIA_V1_PUBLIC_FILES
    }
    evaluator_payloads = {
        path: tree[f"evaluator/{path}"] for path in _ASTERIA_V1_EVALUATOR_FILES
    }
    assert (
        c08_frozen_artifact_set_digest(public_payloads)
        == (_ASTERIA_V1_DIGESTS["public_artifact_set_digest"])
    )
    assert (
        c08_frozen_artifact_set_digest(evaluator_payloads)
        == (_ASTERIA_V1_DIGESTS["evaluator_artifact_set_digest"])
    )
    assert _ASTERIA_V1_PUBLIC_MANIFEST["artifacts"] == {
        path: hashlib.sha256(payload).hexdigest()
        for path, payload in public_payloads.items()
    }
    assert _ASTERIA_V1_EVALUATOR_CHECKSUMS["evaluator_artifacts"] == {
        path: hashlib.sha256(payload).hexdigest()
        for path, payload in evaluator_payloads.items()
    }
    public_manifest = tree["public/manifest.json"]
    evaluator_checksums = tree["evaluator/checksums.json"]
    assert json.loads(public_manifest) == _ASTERIA_V1_PUBLIC_MANIFEST
    assert json.loads(evaluator_checksums) == _ASTERIA_V1_EVALUATOR_CHECKSUMS
    assert public_manifest == _v1_metadata_bytes(_ASTERIA_V1_PUBLIC_MANIFEST)
    assert evaluator_checksums == _v1_metadata_bytes(_ASTERIA_V1_EVALUATOR_CHECKSUMS)

    examples = Path("enterprise-identity-access-contract/examples")
    for filename, digest in _ENTERPRISE_V1_EXAMPLE_DIGESTS.items():
        assert hashlib.sha256((examples / filename).read_bytes()).hexdigest() == digest
