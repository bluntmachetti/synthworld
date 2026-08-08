"""Exercise the static-site publication-boundary audit as an external CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from base64 import b64decode
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_AUDIT = _ROOT / "tools" / "audit_publication_boundary.py"
_POLICY = _ROOT / "docs" / "publication-boundary.json"
_ALLOWED_SENSITIVITIES = ("public_input", "public_reference_truth")
_VALID_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source(
    path: str,
    *,
    source_type: str = "project_documentation",
    generator: str | None = None,
    requires_sensitivity: bool = False,
    permitted_sensitivities: list[str] | None = None,
) -> dict[str, object]:
    return {
        "path": path,
        "source_type": source_type,
        "generator": generator,
        "requires_sensitivity": requires_sensitivity,
        "permitted_sensitivities": permitted_sensitivities or [],
    }


def _policy(*, sources: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "sources": sources,
        "allowed_sensitivities": list(_ALLOWED_SENSITIVITIES),
        "forbidden_sensitivities": [
            "private_held_out_truth",
            "operator_private",
            "internal_build_only",
        ],
        "allowed_machine_readable_outputs": ["manifest.json"],
        "forbidden_output_names": [
            ".env",
            "forbidden.txt",
            "llms.txt",
            "llms-full.txt",
        ],
        "forbidden_path_parts": [
            ".local-assurance",
            ".omc",
            "node_modules",
            "private",
        ],
        "forbidden_suffixes": [
            ".7z",
            ".bz2",
            ".csv",
            ".db",
            ".gz",
            ".map",
            ".ndjson",
            ".parquet",
            ".sqlite",
            ".tar",
            ".tgz",
            ".tsv",
            ".xml",
            ".xz",
            ".yaml",
            ".yml",
            ".zip",
        ],
    }


def _provenance(outputs: list[dict[str, object]]) -> dict[str, object]:
    return {"schema_version": "1.0.0", "outputs": outputs}


def _output(
    path: str,
    *sources: str,
    sensitivity: str | None = "public_input",
) -> dict[str, object]:
    return {"path": path, "sources": list(sources), "sensitivity": sensitivity}


def _invoke(
    *,
    policy_path: Path,
    provenance_path: Path,
    dist: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - repository-owned CLI and test-controlled paths
        [
            sys.executable,
            str(_AUDIT),
            "--policy",
            str(policy_path),
            "--provenance",
            str(provenance_path),
            "--dist",
            str(dist),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_audit(
    tmp_path: Path,
    policy: dict[str, object],
    provenance: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    dist = tmp_path / "dist"
    policy_path = tmp_path / "policy.json"
    provenance_path = tmp_path / "provenance.json"
    _write_json(policy_path, policy)
    _write_json(provenance_path, provenance)
    return _invoke(policy_path=policy_path, provenance_path=provenance_path, dist=dist)


def _write_dist(tmp_path: Path, files: dict[str, str | bytes]) -> None:
    dist = tmp_path / "dist"
    for relative_path, content in files.items():
        path = dist / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")


def _baseline_policy() -> dict[str, object]:
    return _policy(
        sources=[
            _source("README.md"),
            _source("docs/guide.md"),
            _source(
                "evaluator/reference.md",
                source_type="evaluator_reference",
                requires_sensitivity=True,
                permitted_sensitivities=["public_reference_truth"],
            ),
            _source("docs/assets/logo.png", source_type="public_asset"),
        ]
    )


def test_real_policy_is_accepted_by_the_real_cli_for_a_minimal_harness(
    tmp_path: Path,
) -> None:
    _write_dist(tmp_path, {"index.html": "<h1>SynthWorld</h1>\n"})
    provenance_path = tmp_path / "provenance.json"
    _write_json(provenance_path, _provenance([_output("index.html", "README.md")]))

    result = _invoke(
        policy_path=_POLICY,
        provenance_path=provenance_path,
        dist=tmp_path / "dist",
    )

    assert result.returncode == 0, result.stderr


def test_visible_html_and_raw_markdown_mirror_pass_when_exactly_provenanced(
    tmp_path: Path,
) -> None:
    _write_dist(
        tmp_path,
        {
            "index.html": "<h1>SynthWorld</h1>\n",
            "guide.md": "# Guide\n",
        },
    )

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance(
            [
                _output("index.html", "README.md"),
                _output("guide.md", "docs/guide.md"),
            ]
        ),
    )

    assert result.returncode == 0, result.stderr


def test_unlisted_hidden_generated_json_fails_even_when_not_navigated(
    tmp_path: Path,
) -> None:
    _write_dist(
        tmp_path,
        {
            "index.html": "<h1>SynthWorld</h1>\n",
            "generated/hidden.json": "{}\n",
        },
    )

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance([_output("index.html", "README.md")]),
    )

    assert result.returncode == 1
    assert "generated/hidden.json: missing provenance entry" in result.stderr


def test_exact_allowlisted_evaluator_source_accepts_only_public_reference_truth(
    tmp_path: Path,
) -> None:
    _write_dist(tmp_path, {"reference.html": "<h1>Reference</h1>\n"})
    provenance = _provenance(
        [
            _output(
                "reference.html",
                "evaluator/reference.md",
                sensitivity="public_reference_truth",
            )
        ]
    )

    result = _run_audit(tmp_path, _baseline_policy(), provenance)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("sensitivity", ["public_input", "private_held_out_truth"])
def test_exact_allowlisted_evaluator_source_rejects_other_sensitivities(
    tmp_path: Path,
    sensitivity: str,
) -> None:
    _write_dist(tmp_path, {"reference.html": "<h1>Reference</h1>\n"})

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance(
            [
                _output(
                    "reference.html",
                    "evaluator/reference.md",
                    sensitivity=sensitivity,
                )
            ]
        ),
    )

    assert result.returncode == 1
    assert "reference.html: sensitivity" in result.stderr


def test_ordinary_prose_and_null_optional_sensitivity_pass(tmp_path: Path) -> None:
    _write_dist(
        tmp_path,
        {
            "index.html": "This discusses an API key, token, and secret as concepts.\n",
        },
    )

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance([_output("index.html", "README.md", sensitivity=None)]),
    )

    assert result.returncode == 0, result.stderr


def test_unapproved_source_fails_even_when_output_looks_safe(tmp_path: Path) -> None:
    _write_dist(tmp_path, {"index.html": "<h1>SynthWorld</h1>\n"})

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance([_output("index.html", "private/draft.md")]),
    )

    assert result.returncode == 1
    assert "index.html: provenance source is not allowlisted" in result.stderr


def test_provenance_entry_for_no_file_is_an_audit_violation(tmp_path: Path) -> None:
    _write_dist(tmp_path, {"index.html": "<h1>SynthWorld</h1>\n"})

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance(
            [
                _output("index.html", "README.md"),
                _output("missing.html", "README.md"),
            ]
        ),
    )

    assert result.returncode == 1
    assert (
        "missing.html: provenance entry does not resolve to a regular file"
        in result.stderr
    )


@pytest.mark.parametrize(
    ("provenance", "expected"),
    [
        (
            _provenance(
                [
                    _output("index.html", "README.md"),
                    _output("index.html", "README.md"),
                ]
            ),
            "provenance outputs must not contain duplicate paths",
        ),
        (
            _provenance([_output("guide//raw.md", "docs/guide.md")]),
            "normalized relative path",
        ),
    ],
)
def test_duplicate_and_unnormalized_provenance_paths_are_schema_errors(
    tmp_path: Path,
    provenance: dict[str, object],
    expected: str,
) -> None:
    _write_dist(
        tmp_path, {"index.html": "<h1>SynthWorld</h1>\n", "guide/raw.md": "# Raw\n"}
    )

    result = _run_audit(tmp_path, _baseline_policy(), provenance)

    assert result.returncode == 2
    assert expected in result.stderr


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    [
        (".env", "setting=ordinary\n", "forbidden output name"),
        ("forbidden.txt", "draft\n", "forbidden output name"),
        ("LLMS.txt", "draft\n", "forbidden output name"),
        ("assets/site.map", "{}\n", "forbidden output suffix"),
        ("exports/raw.csv", "field,value\n", "forbidden output suffix"),
        ("exports/raw.ndjson", "{}\n", "forbidden output suffix"),
        ("exports/raw.yaml", "field: value\n", "forbidden output suffix"),
        ("exports/raw.xml", "<record/>\n", "forbidden output suffix"),
        ("exports/raw.tsv", "field\tvalue\n", "forbidden output suffix"),
        ("exports/raw.parquet", b"PAR1", "forbidden output suffix"),
        ("exports/raw.zip", b"PK\x03\x04", "forbidden output suffix"),
        ("exports/raw.tar", b"archive", "forbidden output suffix"),
        ("exports/raw.sqlite", b"SQLite format 3\x00", "forbidden output suffix"),
        ("exports/raw.db", b"database", "forbidden output suffix"),
        ("assets/bundle.zip.png", _VALID_PNG, "forbidden output suffix"),
        ("private/index.html", "<h1>Private</h1>\n", "forbidden path part"),
        (".OMC/index.html", "<h1>Private</h1>\n", "forbidden path part"),
        ("Node_Modules/index.html", "<h1>Private</h1>\n", "forbidden path part"),
    ],
)
def test_forbidden_output_forms_fail(
    tmp_path: Path,
    path: str,
    content: str | bytes,
    expected: str,
) -> None:
    _write_dist(tmp_path, {path: content})

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance([_output(path, "README.md")]),
    )

    assert result.returncode == 1
    assert f"{path}: {expected}" in result.stderr


@pytest.mark.parametrize(
    "content",
    [
        "api_key=live-value\n",
        "token=live-value\n",
        "secret=live-value\n",
    ],
)
def test_bare_credential_assignments_fail(tmp_path: Path, content: str) -> None:
    _write_dist(tmp_path, {"index.html": content})

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance([_output("index.html", "README.md")]),
    )

    assert result.returncode == 1
    assert "index.html: contains an API-key assignment" in result.stderr


@pytest.mark.parametrize(
    ("path", "content"),
    [
        ("plain", "/home/example/private\n"),
        ("guide.htm", "file:///tmp/synthworld/private\n"),
        ("guide.mdx", "/Users/example/private\n"),
        ("windows.html", "C:\\Users\\Example\\private\n"),
    ],
)
def test_text_outputs_detect_local_path_forms(
    tmp_path: Path,
    path: str,
    content: str,
) -> None:
    _write_dist(tmp_path, {path: content})

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance([_output(path, "README.md")]),
    )

    assert result.returncode == 1
    assert f"{path}: contains a local absolute path" in result.stderr


def test_explicitly_allowlisted_machine_readable_output_passes(tmp_path: Path) -> None:
    _write_dist(tmp_path, {"manifest.json": "{}\n"})

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance([_output("manifest.json", "README.md")]),
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    [
        (
            "exports/raw.zip",
            b"PK\x03\x04",
            "error: policy machine-readable output has a forbidden suffix",
        ),
        (
            "llms-full.txt",
            "draft\n",
            "error: policy machine-readable output has a forbidden name",
        ),
        (
            "assets/site.map",
            "{}\n",
            "error: policy machine-readable output has a forbidden suffix",
        ),
        (
            "private/reference.json",
            "{}\n",
            "error: policy machine-readable output has a forbidden path part",
        ),
    ],
)
def test_machine_output_allowlist_cannot_bypass_other_boundary_rules(
    tmp_path: Path,
    path: str,
    content: str | bytes,
    expected: str,
) -> None:
    _write_dist(tmp_path, {path: content})
    policy = _baseline_policy()
    policy["allowed_machine_readable_outputs"] = [path]

    result = _run_audit(
        tmp_path,
        policy,
        _provenance([_output(path, "README.md")]),
    )

    assert result.returncode == 2
    assert expected in result.stderr


def test_allowlisted_provenanced_valid_png_asset_passes(tmp_path: Path) -> None:
    _write_dist(tmp_path, {"assets/logo.png": _VALID_PNG})

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance([_output("assets/logo.png", "docs/assets/logo.png")]),
    )

    assert result.returncode == 0, result.stderr


def test_unsupported_invalid_binary_fails(tmp_path: Path) -> None:
    _write_dist(tmp_path, {"assets/unknown.bin": b"\xff\xfe\x00"})

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance([_output("assets/unknown.bin", "README.md")]),
    )

    assert result.returncode == 1
    assert (
        "assets/unknown.bin: output is not valid UTF-8 or an approved binary asset"
        in result.stderr
    )


def test_invalid_utf8_html_and_symlink_output_fail(tmp_path: Path) -> None:
    _write_dist(tmp_path, {"invalid.html": b"\xff\xfe"})
    outside = tmp_path / "outside.html"
    outside.write_text("<h1>outside</h1>\n", encoding="utf-8")
    (tmp_path / "dist" / "linked.html").symlink_to(outside)

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance(
            [
                _output("invalid.html", "README.md"),
                _output("linked.html", "README.md"),
            ]
        ),
    )

    assert result.returncode == 1
    assert (
        "invalid.html: output is not valid UTF-8 or an approved binary asset"
        in result.stderr
    )
    assert "linked.html: symlink is not allowed" in result.stderr


def test_empty_dist_fails(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()

    result = _run_audit(tmp_path, _baseline_policy(), _provenance([]))

    assert result.returncode == 1
    assert ".: dist contains no regular files" in result.stderr


def test_diagnostics_are_sorted_and_do_not_disclose_host_paths(tmp_path: Path) -> None:
    _write_dist(
        tmp_path,
        {
            "z-private.html": "/home/example/private\n",
            "forbidden.txt": "draft\n",
        },
    )

    result = _run_audit(
        tmp_path,
        _baseline_policy(),
        _provenance(
            [
                _output("z-private.html", "README.md"),
                _output("forbidden.txt", "README.md"),
            ]
        ),
    )

    assert result.returncode == 1
    diagnostics = [line for line in result.stderr.splitlines() if line]
    assert diagnostics == sorted(diagnostics)
    assert "forbidden.txt: forbidden output name" in result.stderr
    assert "z-private.html: contains a local absolute path" in result.stderr
    assert str(tmp_path) not in result.stderr
    assert "/home/example/private" not in result.stderr
