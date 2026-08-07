"""Offline tests for the Claude adapter example.

These tests exercise the adapter's pure logic — the public manifest
boundary, cache fingerprinting and invalidation, envelope validation,
offline replay, run-manifest evidence binding, extraction offset
conversion, output serialization, and both completer request paths — with
fakes and temporary files. Live network calls remain manual and are not
exercised here.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest

from synthworld.agentic import export_agentic_benchmark, load_golden_agentic_benchmark


def _load_adapter() -> ModuleType:
    path = Path(__file__).parent.parent / "examples" / "claude_adapter.py"
    spec = importlib.util.spec_from_file_location("claude_adapter", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before executing so pydantic can resolve the module's
    # postponed annotations when building its model classes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load_adapter()


class FakeCompleter:
    """Deterministic completer keyed by unit ID, with call accounting."""

    def __init__(self, outputs: dict[str, dict[str, object]]) -> None:
        self._outputs = outputs
        self.calls: list[str] = []

    def complete(
        self,
        unit_id: str,
        instructions: str,
        context: str | None,
        user_text: str,
        schema: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(unit_id)
        return {
            "output": self._outputs[unit_id],
            "meta": {
                "requested_model": "fake-model",
                "served_model": "fake-model-served",
                "stop_reason": "end_turn",
                "fallbacks_enabled": False,
                "fallback_ran": False,
                "sdk_version": "0.0.0-test",
            },
        }


class RefusingCompleter:
    """Fails the test if any unit reaches the model."""

    def complete(
        self,
        unit_id: str,
        instructions: str,
        context: str | None,
        user_text: str,
        schema: dict[str, object],
    ) -> dict[str, object]:
        raise AssertionError(f"unexpected model call for unit {unit_id}")


@pytest.fixture(scope="module")
def benchmark_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("asteria")
    export_agentic_benchmark(root, load_golden_agentic_benchmark())
    return root


@pytest.fixture(scope="module")
def public_dir(benchmark_root: Path) -> Path:
    return benchmark_root / "public"


def _agentic_args(
    tmp_path: Path,
    public_dir: Path,
    model: str,
    *,
    fallbacks: bool = False,
) -> argparse.Namespace:
    argv = [
        "agentic",
        "--public-dir",
        str(public_dir),
        "--output",
        str(tmp_path / "agentic.jsonl"),
        "--model",
        model,
    ]
    if fallbacks:
        argv.append("--fallbacks")
    return cast(argparse.Namespace, adapter._parse_args(argv))


def _null_row(event_id: str) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(adapter.AGENTIC_TRACE_FIELDS)
    row["event_id"] = event_id
    return row


def _scenario_ids(public_dir: Path) -> list[str]:
    scenario = json.loads(
        (public_dir / "scenarios" / "procurement-delegation.json").read_text(
            encoding="utf-8"
        )
    )
    return cast(list[str], scenario["action_event_ids"])


def _agentic_outputs(public_dir: Path) -> dict[str, dict[str, object]]:
    return {event_id: _null_row(event_id) for event_id in _scenario_ids(public_dir)}


def _copied_public_dir(tmp_path: Path, public_dir: Path) -> Path:
    copy = tmp_path / "public"
    shutil.copytree(public_dir, copy)
    return copy


def test_agentic_offline_run_writes_rows_envelopes_and_manifest(
    tmp_path: Path, public_dir: Path
) -> None:
    args = _agentic_args(tmp_path, public_dir, "fake-model")
    completer = FakeCompleter(_agentic_outputs(public_dir))
    adapter.run_agentic(args, completer)

    rows = [
        json.loads(line)
        for line in args.output.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 11
    assert len(completer.calls) == 11

    envelope = json.loads(
        (args.responses_dir / adapter._cache_file_name(rows[0]["event_id"])).read_text(
            encoding="utf-8"
        )
    )
    assert set(envelope) == {"unit_id", "fingerprint", "meta", "output"}
    assert envelope["meta"]["served_model"] == "fake-model-served"

    manifest = json.loads(
        (args.responses_dir / "run-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["task"] == "agentic"
    assert manifest["requested_model"] == "fake-model"
    assert manifest["adapter_version"] == adapter.ADAPTER_VERSION
    assert manifest["served_models"] == ["fake-model-served"]
    assert manifest["fallbacks_enabled"] is False
    assert manifest["fallback_ran"] is False
    assert manifest["stop_reasons"] == {"end_turn": 11}
    assert manifest["units"] == 11
    assert manifest["benchmark_artifact_set_digest"] is not None


def test_agentic_cached_run_replays_without_model_calls(
    tmp_path: Path, public_dir: Path
) -> None:
    args = _agentic_args(tmp_path, public_dir, "fake-model")
    adapter.run_agentic(args, FakeCompleter(_agentic_outputs(public_dir)))
    first = args.output.read_text(encoding="utf-8")
    args.output.unlink()

    adapter.run_agentic(args, RefusingCompleter())
    assert args.output.read_text(encoding="utf-8") == first


def test_agentic_cache_rejects_changed_model(tmp_path: Path, public_dir: Path) -> None:
    adapter.run_agentic(
        _agentic_args(tmp_path, public_dir, "fake-model"),
        FakeCompleter(_agentic_outputs(public_dir)),
    )
    with pytest.raises(SystemExit, match="different adapter inputs"):
        adapter.run_agentic(
            _agentic_args(tmp_path, public_dir, "other-model"),
            RefusingCompleter(),
        )


def test_agentic_cache_rejects_changed_fallback_mode(
    tmp_path: Path, public_dir: Path
) -> None:
    adapter.run_agentic(
        _agentic_args(tmp_path, public_dir, "fake-model"),
        FakeCompleter(_agentic_outputs(public_dir)),
    )
    with pytest.raises(SystemExit, match="different adapter inputs"):
        adapter.run_agentic(
            _agentic_args(tmp_path, public_dir, "fake-model", fallbacks=True),
            RefusingCompleter(),
        )


def test_agentic_rejects_benchmark_root(tmp_path: Path, benchmark_root: Path) -> None:
    args = _agentic_args(tmp_path, benchmark_root, "fake-model")
    with pytest.raises(SystemExit, match=r"no manifest\.json"):
        adapter.run_agentic(args, RefusingCompleter())


def test_agentic_rejects_non_oracle_free_package(
    tmp_path: Path, public_dir: Path
) -> None:
    copy = _copied_public_dir(tmp_path, public_dir)
    manifest_path = copy / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["oracle_free"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    args = _agentic_args(tmp_path, copy, "fake-model")
    with pytest.raises(SystemExit, match="oracle_free"):
        adapter.run_agentic(args, RefusingCompleter())


def test_agentic_rejects_modified_listed_artifact(
    tmp_path: Path, public_dir: Path
) -> None:
    copy = _copied_public_dir(tmp_path, public_dir)
    target = copy / "agents.jsonl"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    args = _agentic_args(tmp_path, copy, "fake-model")
    with pytest.raises(SystemExit, match="SHA-256"):
        adapter.run_agentic(args, RefusingCompleter())


def test_agentic_rejects_unlisted_file(tmp_path: Path, public_dir: Path) -> None:
    copy = _copied_public_dir(tmp_path, public_dir)
    (copy / "authority_truth.jsonl").write_text("{}\n", encoding="utf-8")
    args = _agentic_args(tmp_path, copy, "fake-model")
    with pytest.raises(SystemExit, match="not listed in the public manifest"):
        adapter.run_agentic(args, RefusingCompleter())


def test_cache_rejects_tampered_envelope_provenance(
    tmp_path: Path, public_dir: Path
) -> None:
    args = _agentic_args(tmp_path, public_dir, "fake-model")
    adapter.run_agentic(args, FakeCompleter(_agentic_outputs(public_dir)))
    target = args.responses_dir / adapter._cache_file_name(
        "evt-010-authorised-comparison"
    )
    envelope = json.loads(target.read_text(encoding="utf-8"))
    envelope["meta"]["requested_model"] = "someone-else"
    target.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(SystemExit, match="provenance metadata"):
        adapter.run_agentic(args, RefusingCompleter())


def test_cache_rejects_structurally_invalid_envelope(
    tmp_path: Path, public_dir: Path
) -> None:
    args = _agentic_args(tmp_path, public_dir, "fake-model")
    adapter.run_agentic(args, FakeCompleter(_agentic_outputs(public_dir)))
    target = args.responses_dir / adapter._cache_file_name(
        "evt-010-authorised-comparison"
    )
    envelope = json.loads(target.read_text(encoding="utf-8"))
    del envelope["meta"]
    target.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(SystemExit, match="invalid response envelope"):
        adapter.run_agentic(args, RefusingCompleter())


def test_run_manifest_binds_output_and_envelopes(
    tmp_path: Path, public_dir: Path
) -> None:
    args = _agentic_args(tmp_path, public_dir, "fake-model")
    adapter.run_agentic(args, FakeCompleter(_agentic_outputs(public_dir)))
    manifest = json.loads(
        (args.responses_dir / "run-manifest.json").read_text(encoding="utf-8")
    )

    assert (
        manifest["output_sha256"]
        == hashlib.sha256(args.output.read_bytes()).hexdigest()
    )
    unit_ids = _scenario_ids(public_dir)
    assert sorted(manifest["unit_fingerprints"]) == sorted(unit_ids)
    envelope_bytes = {
        adapter._cache_file_name(unit_id): (
            args.responses_dir / adapter._cache_file_name(unit_id)
        ).read_bytes()
        for unit_id in unit_ids
    }
    assert manifest["response_artifact_set_digest"] == adapter._artifact_set_digest(
        envelope_bytes
    )

    # Editing the output after the run is detectable against the manifest.
    args.output.write_text("tampered\n", encoding="utf-8")
    assert (
        hashlib.sha256(args.output.read_bytes()).hexdigest()
        != manifest["output_sha256"]
    )


def _stub_response(
    *,
    stop_reason: str = "end_turn",
    model: str = "served-model",
    iterations: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        model=model,
        id="msg_stub_001",
        usage=SimpleNamespace(iterations=iterations),
        content=[SimpleNamespace(type="text", text='{"findings": []}')],
    )


class _StubMessages:
    def __init__(self, response: SimpleNamespace) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self.response


def test_completer_normal_request_path() -> None:
    completer = adapter.ClaudeJsonCompleter("requested-model")
    messages = _StubMessages(_stub_response())
    completer._client = SimpleNamespace(messages=messages)
    completion = completer.complete(
        "unit-1", "instructions", None, "user text", {"type": "object"}
    )

    assert len(messages.calls) == 1
    request = messages.calls[0]
    assert request["model"] == "requested-model"
    assert "betas" not in request
    assert "fallbacks" not in request
    meta = cast(dict[str, object], completion["meta"])
    assert meta["served_model"] == "served-model"
    assert meta["fallbacks_enabled"] is False
    assert meta["fallback_ran"] is False
    assert meta["response_id"] == "msg_stub_001"


def test_completer_fallback_request_path() -> None:
    completer = adapter.ClaudeJsonCompleter("requested-model", use_fallbacks=True)
    beta_messages = _StubMessages(
        _stub_response(
            model="fallback-served-model",
            iterations=[SimpleNamespace(type="fallback_message")],
        )
    )
    completer._client = SimpleNamespace(beta=SimpleNamespace(messages=beta_messages))
    completion = completer.complete(
        "unit-1", "instructions", "context", "user text", {"type": "object"}
    )

    assert len(beta_messages.calls) == 1
    request = beta_messages.calls[0]
    assert request["betas"] == list(adapter.FALLBACK_BETAS)
    assert request["fallbacks"] == "default"
    meta = cast(dict[str, object], completion["meta"])
    assert meta["served_model"] == "fallback-served-model"
    assert meta["fallbacks_enabled"] is True
    assert meta["fallback_ran"] is True


def test_completer_raises_on_refusal() -> None:
    completer = adapter.ClaudeJsonCompleter("requested-model")
    completer._client = SimpleNamespace(
        messages=_StubMessages(_stub_response(stop_reason="refusal"))
    )
    with pytest.raises(RuntimeError, match="declined unit unit-1"):
        completer.complete(
            "unit-1", "instructions", None, "user text", {"type": "object"}
        )


def test_extraction_offsets_dedupe_and_serialization(tmp_path: Path) -> None:
    page_content = "Email: a@example.test\nBackup email: a@example.test\n"
    corpus = {
        "synthetic": True,
        "schema_version": "1.0.0",
        "seed": 1,
        "pages": [
            {
                "source_type": "search",
                "source_record_id": "search-0001-01",
                "content": page_content,
            },
            {
                "source_type": "search",
                "source_record_id": "negative-control-0001",
                "content": "No personal values are published.\n",
            },
        ],
    }
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
    args = cast(
        argparse.Namespace,
        adapter._parse_args(
            [
                "extraction",
                "--corpus",
                str(corpus_path),
                "--output",
                str(tmp_path / "extraction.json"),
                "--model",
                "fake-model",
            ]
        ),
    )
    outputs: dict[str, dict[str, object]] = {
        "search--search-0001-01": {
            "findings": [
                {"data_class": "email", "text": "a@example.test"},
                {"data_class": "email", "text": "a@example.test"},
                {"data_class": "phone", "text": "not-in-the-page"},
                {"data_class": "username", "text": ""},
            ]
        },
        "search--negative-control-0001": {"findings": []},
    }
    adapter.run_extraction(args, FakeCompleter(outputs))

    prediction_set = json.loads(args.output.read_text(encoding="utf-8"))
    assert prediction_set["schema_version"] == "0.1.0"
    spans = prediction_set["predictions"][0]["spans"]
    # Duplicate findings dedupe to one span per occurrence; unlocatable and
    # empty findings produce no spans.
    assert [page_content[span["start"] : span["end"]] for span in spans] == [
        "a@example.test",
        "a@example.test",
    ]
    assert prediction_set["predictions"][1]["spans"] == []

    manifest = json.loads(
        (args.responses_dir / "run-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["task"] == "extraction"
    assert manifest["benchmark_artifact_set_digest"] is None
    assert manifest["units"] == 2


def test_extraction_cache_rejects_changed_corpus(tmp_path: Path) -> None:
    def corpus_with(content: str) -> Path:
        corpus_path = tmp_path / "corpus.json"
        corpus_path.write_text(
            json.dumps(
                {
                    "synthetic": True,
                    "schema_version": "1.0.0",
                    "seed": 1,
                    "pages": [
                        {
                            "source_type": "search",
                            "source_record_id": "search-0001-01",
                            "content": content,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return corpus_path

    outputs: dict[str, dict[str, object]] = {"search--search-0001-01": {"findings": []}}

    def args_for(corpus_path: Path) -> argparse.Namespace:
        return cast(
            argparse.Namespace,
            adapter._parse_args(
                [
                    "extraction",
                    "--corpus",
                    str(corpus_path),
                    "--output",
                    str(tmp_path / "extraction.json"),
                ]
            ),
        )

    adapter.run_extraction(args_for(corpus_with("One body.\n")), FakeCompleter(outputs))
    with pytest.raises(SystemExit, match="different adapter inputs"):
        adapter.run_extraction(
            args_for(corpus_with("A different body.\n")), RefusingCompleter()
        )


def _rewrite_manifest(public_copy: Path) -> None:
    """Recompute per-file hashes and the artifact-set digest after edits."""

    manifest_path = public_copy / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_bytes = {
        name: (public_copy / name).read_bytes() for name in manifest["artifacts"]
    }
    manifest["artifacts"] = {
        name: adapter._sha256_bytes(data) for name, data in artifact_bytes.items()
    }
    manifest["artifact_set_digest"] = adapter._artifact_set_digest(artifact_bytes)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_agentic_rejects_absolute_manifest_path(
    tmp_path: Path, public_dir: Path
) -> None:
    copy = _copied_public_dir(tmp_path, public_dir)
    manifest_path = copy / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["/etc/hostname"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    args = _agentic_args(tmp_path, copy, "fake-model")
    with pytest.raises(SystemExit, match="unsafe artifact name"):
        adapter.run_agentic(args, RefusingCompleter())


def test_agentic_rejects_traversal_manifest_path(
    tmp_path: Path, public_dir: Path
) -> None:
    copy = _copied_public_dir(tmp_path, public_dir)
    manifest_path = copy / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["../evaluator/cases.jsonl"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    args = _agentic_args(tmp_path, copy, "fake-model")
    with pytest.raises(SystemExit, match="unsafe artifact name"):
        adapter.run_agentic(args, RefusingCompleter())


@pytest.mark.parametrize(
    "drive_name",
    ["C:/outside/evaluator.json", "C:relative-drive-path.json"],
)
def test_agentic_rejects_windows_drive_manifest_path(
    tmp_path: Path, public_dir: Path, drive_name: str
) -> None:
    copy = _copied_public_dir(tmp_path, public_dir)
    manifest_path = copy / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][drive_name] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    args = _agentic_args(tmp_path, copy, "fake-model")
    with pytest.raises(SystemExit, match="unsafe artifact name"):
        adapter.run_agentic(args, RefusingCompleter())


def test_agentic_rejects_symlinked_artifact(
    tmp_path: Path, benchmark_root: Path, public_dir: Path
) -> None:
    copy = _copied_public_dir(tmp_path, public_dir)
    target = copy / "agents.jsonl"
    target.unlink()
    target.symlink_to(benchmark_root / "evaluator" / "cases.jsonl")
    _rewrite_manifest(copy)
    args = _agentic_args(tmp_path, copy, "fake-model")
    with pytest.raises(SystemExit, match="symlink"):
        adapter.run_agentic(args, RefusingCompleter())


def test_agentic_rejects_symlinked_parent_directory(
    tmp_path: Path, public_dir: Path
) -> None:
    copy = _copied_public_dir(tmp_path, public_dir)
    outside = tmp_path / "outside-scenarios"
    shutil.move(str(copy / "scenarios"), str(outside))
    (copy / "scenarios").symlink_to(outside, target_is_directory=True)
    args = _agentic_args(tmp_path, copy, "fake-model")
    with pytest.raises(SystemExit, match="escapes the public directory"):
        adapter.run_agentic(args, RefusingCompleter())


def test_agentic_traversal_event_id_stays_inside_cache_dir(
    tmp_path: Path, public_dir: Path
) -> None:
    copy = _copied_public_dir(tmp_path, public_dir)
    scenario_path = copy / "scenarios" / "procurement-delegation.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    evil_id = "../../evil-escape"
    scenario["action_event_ids"] = [*scenario["action_event_ids"], evil_id]
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    _rewrite_manifest(copy)

    args = _agentic_args(tmp_path, copy, "fake-model")
    outputs = _agentic_outputs(public_dir)
    outputs[evil_id] = _null_row(evil_id)
    adapter.run_agentic(args, FakeCompleter(outputs))

    cache_file = args.responses_dir / adapter._cache_file_name(evil_id)
    assert cache_file.is_file()
    assert not (tmp_path / "evil-escape.json").exists()
    assert not (tmp_path.parent / "evil-escape.json").exists()
    written = {path.name for path in args.responses_dir.iterdir()}
    assert written == {
        "run-manifest.json",
        *(adapter._cache_file_name(unit_id) for unit_id in outputs),
    }


def test_extraction_traversal_record_id_stays_inside_cache_dir(
    tmp_path: Path,
) -> None:
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps(
            {
                "synthetic": True,
                "schema_version": "1.0.0",
                "seed": 1,
                "pages": [
                    {
                        "source_type": "search",
                        "source_record_id": "../../escape",
                        "content": "No values.\n",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = cast(
        argparse.Namespace,
        adapter._parse_args(
            [
                "extraction",
                "--corpus",
                str(corpus_path),
                "--output",
                str(tmp_path / "out" / "extraction.json"),
            ]
        ),
    )
    outputs: dict[str, dict[str, object]] = {"search--../../escape": {"findings": []}}
    adapter.run_extraction(args, FakeCompleter(outputs))

    unit_id = "search--../../escape"
    assert (args.responses_dir / adapter._cache_file_name(unit_id)).is_file()
    assert not (tmp_path / "escape.json").exists()
    written = {path.name for path in args.responses_dir.iterdir()}
    assert written == {"run-manifest.json", adapter._cache_file_name(unit_id)}


def _tamper_cached_output(args: argparse.Namespace, output: object) -> None:
    target = args.responses_dir / adapter._cache_file_name(
        "evt-010-authorised-comparison"
    )
    envelope = json.loads(target.read_text(encoding="utf-8"))
    envelope["output"] = output
    target.write_text(json.dumps(envelope), encoding="utf-8")


def test_cache_rejects_empty_agentic_output(tmp_path: Path, public_dir: Path) -> None:
    args = _agentic_args(tmp_path, public_dir, "fake-model")
    adapter.run_agentic(args, FakeCompleter(_agentic_outputs(public_dir)))
    _tamper_cached_output(args, {})
    with pytest.raises(SystemExit, match="does not conform to the task schema"):
        adapter.run_agentic(args, RefusingCompleter())


def test_cache_rejects_extra_field_in_agentic_output(
    tmp_path: Path, public_dir: Path
) -> None:
    args = _agentic_args(tmp_path, public_dir, "fake-model")
    adapter.run_agentic(args, FakeCompleter(_agentic_outputs(public_dir)))
    row = _null_row("evt-010-authorised-comparison")
    row["bogus"] = 1
    _tamper_cached_output(args, row)
    with pytest.raises(SystemExit, match="does not conform to the task schema"):
        adapter.run_agentic(args, RefusingCompleter())


def test_fresh_invalid_agentic_output_is_rejected_and_not_cached(
    tmp_path: Path, public_dir: Path
) -> None:
    args = _agentic_args(tmp_path, public_dir, "fake-model")
    outputs = _agentic_outputs(public_dir)
    outputs["evt-010-authorised-comparison"] = {}
    with pytest.raises(SystemExit, match="invalid response for"):
        adapter.run_agentic(args, FakeCompleter(outputs))
    assert not (
        args.responses_dir / adapter._cache_file_name("evt-010-authorised-comparison")
    ).exists()


def _run_single_page_extraction(
    tmp_path: Path, findings: list[dict[str, object]]
) -> argparse.Namespace:
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps(
            {
                "synthetic": True,
                "schema_version": "1.0.0",
                "seed": 1,
                "pages": [
                    {
                        "source_type": "search",
                        "source_record_id": "search-0001-01",
                        "content": "Email: a@example.test\n",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = cast(
        argparse.Namespace,
        adapter._parse_args(
            [
                "extraction",
                "--corpus",
                str(corpus_path),
                "--output",
                str(tmp_path / "extraction.json"),
                "--model",
                "fake-model",
            ]
        ),
    )
    adapter.run_extraction(
        args, FakeCompleter({"search--search-0001-01": {"findings": findings}})
    )
    return args


def test_cache_rejects_extraction_output_missing_findings(tmp_path: Path) -> None:
    args = _run_single_page_extraction(tmp_path, [])
    target = args.responses_dir / adapter._cache_file_name("search--search-0001-01")
    envelope = json.loads(target.read_text(encoding="utf-8"))
    envelope["output"] = {}
    target.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(SystemExit, match="does not conform to the task schema"):
        adapter.run_extraction(args, RefusingCompleter())


def test_cache_rejects_extraction_output_with_invalid_data_class(
    tmp_path: Path,
) -> None:
    args = _run_single_page_extraction(tmp_path, [])
    target = args.responses_dir / adapter._cache_file_name("search--search-0001-01")
    envelope = json.loads(target.read_text(encoding="utf-8"))
    envelope["output"] = {"findings": [{"data_class": "password", "text": "x"}]}
    target.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(SystemExit, match="does not conform to the task schema"):
        adapter.run_extraction(args, RefusingCompleter())
