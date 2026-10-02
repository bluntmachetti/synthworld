"""Fail release publication while candidate-facing instructions remain."""

import re
import tomllib
from datetime import date
from pathlib import Path


def validate_release_ready(root: Path) -> None:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(
        rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})$",
        changelog,
        re.MULTILINE,
    )
    if heading is None:
        raise ValueError(f"date the {version} changelog section before publication")
    date.fromisoformat(heading[1])
    for name in ("README.md", "docs/guides/agent-authorisation-quickstart.md"):
        text = (root / name).read_text(encoding="utf-8")
        if re.search(
            r"\b(candidate|unreleased)\b|not yet published|after publication",
            text,
            re.I,
        ):
            raise ValueError(f"replace candidate instructions in {name}")
        pins = re.findall(r"idcognito-synthworld==([^\s`]+)", text)
        if any(pin != version for pin in pins):
            raise ValueError(f"update stale package pins in {name}")
        if "synthworld-demo run --output" not in text:
            raise ValueError(f"document the installed demo command in {name}")


if __name__ == "__main__":
    validate_release_ready(Path.cwd())
