"""Validate the configured PyPI README source and Warehouse rendering."""

import tomllib
from pathlib import Path

EXPECTED_README = "README.md"
EXPECTED_CONTENT_TYPE = "text/markdown"


def resolve_readme_source(readme: object) -> Path:
    """Resolve supported PEP 621 README forms to the canonical README path."""
    if isinstance(readme, str):
        readme_file = readme
        content_type = (
            EXPECTED_CONTENT_TYPE if readme.lower().endswith(".md") else None
        )
    elif isinstance(readme, dict):
        readme_file = readme.get("file")
        content_type = readme.get("content-type")
    else:
        raise ValueError(f"unexpected project.readme configuration: {readme!r}")

    if readme_file != EXPECTED_README or content_type != EXPECTED_CONTENT_TYPE:
        raise ValueError(f"unexpected project.readme configuration: {readme!r}")

    return Path(readme_file)


def configured_readme_source(pyproject: Path = Path("pyproject.toml")) -> Path:
    """Load pyproject.toml and return the canonical README source path."""
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    return resolve_readme_source(project.get("readme"))


def main() -> None:
    from readme_renderer.markdown import render

    try:
        readme_path = configured_readme_source()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    source = readme_path.read_text(encoding="utf-8")
    if render(source) is None:
        raise SystemExit(f"{readme_path} failed Warehouse Markdown rendering")


if __name__ == "__main__":
    main()
