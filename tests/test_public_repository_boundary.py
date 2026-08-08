"""Guard the public repository from local consumer-integration material."""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import cast

_ROOT = Path(__file__).resolve().parents[1]


def _find_git() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git is required for repository-boundary tests")
    return executable


_GIT = _find_git()
_LOCAL_ASSURANCE_ROOT = Path(".local-assurance")
_CONSUMER_MARKER = "id" + "cognito"
_PRIVATE_SYMBOL_MARKERS = (
    "publicidentity" + "discovery",
    "deterministicidentity" + "resolver",
    "identity" + "resolution",
)
_TEXT_SUFFIXES = frozenset(
    {".json", ".jsonl", ".lock", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
)
_ALLOWED_CONSUMER_REFERENCE_PATHS = frozenset(
    {
        Path(".github/DISCUSSION_TEMPLATE/q-a.yml"),
        Path(".github/ISSUE_TEMPLATE/bug_report.yml"),
        Path(".github/workflows/release.yml"),
        Path("CHANGELOG.md"),
        # The worked broker adapter names the consumer once, in its module docstring,
        # to say whose integration pattern it demonstrates - reviewed 2026-08-04 with
        # PR #95, which is the review this allowlist exists to force.
        Path("examples/evaluate_broker_adapter.py"),
        # The external reference runner reads only the public distribution version
        # for receipt provenance; it imports no consumer code or private symbols.
        # Reviewed with the live reference-deployment slice on 2026-08-05.
        Path("agent-authority-contract/reference-deployment/run.py"),
        # The mechanical capability inventory copies the public distribution
        # name from pyproject.toml; it contains no consumer integration material.
        # Reviewed with the capability-governance work package on 2026-08-08.
        Path("docs/_data/capabilities.generated.json"),
        Path("Makefile"),
        Path("README.md"),
        Path("ROADMAP.md"),
        Path("USER_GUIDE.md"),
        Path("huggingface/README.md"),
        Path("pyproject.toml"),
        Path("uv.lock"),
    }
)
_ALLOWED_PUBLIC_ADAPTER_EXAMPLES = frozenset(
    {
        Path("agent-authority-contract/adapter-template/adapter.py"),
        # Public-timeline-only by construction; asserts nothing truth-side is
        # reachable from it. Reviewed 2026-08-04 with PR #95.
        Path("examples/evaluate_broker_adapter.py"),
        Path("src/synthworld/search_adapter.py"),
    }
)


def _tracked_paths() -> tuple[Path, ...]:
    result = subprocess.run(  # noqa: S603 - fixed Git command, no external input
        [_GIT, "ls-files", "-z"],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(Path(item) for item in result.stdout.split("\0") if item)


def _tracked_text(paths: tuple[Path, ...]) -> dict[Path, str]:
    return {
        path: (_ROOT / path).read_text(encoding="utf-8")
        for path in paths
        if path.name == "Makefile" or path.suffix in _TEXT_SUFFIXES
    }


def _configuration() -> dict[str, object]:
    return cast(
        dict[str, object],
        tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8")),
    )


def test_local_assurance_workspace_is_ignored_and_untracked() -> None:
    tracked = _tracked_paths()
    assert not any(
        path == _LOCAL_ASSURANCE_ROOT or _LOCAL_ASSURANCE_ROOT in path.parents
        for path in tracked
    )
    subprocess.run(  # noqa: S603 - fixed Git command, no external input
        [
            _GIT,
            "check-ignore",
            "--quiet",
            "--no-index",
            str(_LOCAL_ASSURANCE_ROOT / "probe"),
        ],
        cwd=_ROOT,
        check=True,
    )


def test_build_configuration_excludes_local_assurance_workspace() -> None:
    configuration = _configuration()
    tool = cast(dict[str, object], configuration["tool"])
    hatch = cast(dict[str, object], tool["hatch"])
    build = cast(dict[str, object], hatch["build"])
    excludes = cast(list[str], build["exclude"])
    assert "/.local-assurance" in excludes

    targets = cast(dict[str, object], build["targets"])
    wheel = cast(dict[str, object], targets["wheel"])
    assert wheel["packages"] == ["src/synthworld"]


def test_code_owner_gate_is_limited_to_boundary_defining_files() -> None:
    lines = (_ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8").splitlines()
    patterns = {
        line.split(maxsplit=1)[0]
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "/src/synthworld/**" not in patterns
    assert {
        "/.github/CODEOWNERS",
        "/.github/workflows/**",
        "/.gitignore",
        "/Makefile",
        "/pyproject.toml",
        "/src/synthworld/**/*adapter*.py",
        "/tests/test_public_repository_boundary.py",
    } <= patterns


def test_consumer_references_stay_in_reviewed_public_metadata() -> None:
    tracked_text = _tracked_text(_tracked_paths())
    observed = {
        path
        for path, content in tracked_text.items()
        if _CONSUMER_MARKER in content.casefold()
    }
    assert observed == _ALLOWED_CONSUMER_REFERENCE_PATHS


def test_private_product_symbols_are_absent_from_tracked_text() -> None:
    tracked_text = _tracked_text(_tracked_paths())
    for path, content in tracked_text.items():
        normalized = content.casefold()
        for marker in _PRIVATE_SYMBOL_MARKERS:
            assert marker not in normalized, path


def test_only_reviewed_public_adapter_examples_are_tracked() -> None:
    observed = {
        path
        for path in _tracked_paths()
        if path.suffix == ".py"
        and any("adapter" in part.casefold() for part in path.parts)
    }
    assert observed == _ALLOWED_PUBLIC_ADAPTER_EXAMPLES


def test_private_consumer_is_not_a_project_dependency() -> None:
    configuration = _configuration()
    project = cast(dict[str, object], configuration["project"])
    specifications = list(cast(list[str], project["dependencies"]))
    groups = cast(dict[str, list[str]], configuration["dependency-groups"])
    for group in groups.values():
        specifications.extend(group)

    for specification in specifications:
        dependency_name = re.split(r"[\s\[<>=!~;@]", specification, maxsplit=1)[0]
        normalized = dependency_name.replace("_", "-").casefold()
        assert not normalized.startswith(_CONSUMER_MARKER)
