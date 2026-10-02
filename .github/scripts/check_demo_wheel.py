"""Exercise the installed teaching CLI outside a repository checkout."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import synthworld_demo

if "site-packages" not in str(synthworld_demo.__file__):
    raise RuntimeError("demo must be imported from the installed wheel")
executable = shutil.which("synthworld-demo")
if executable is None:
    raise RuntimeError("installed synthworld-demo entry point is missing")
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for name, extra in (("baseline", []), ("broken", ["--omit-delegation-check"])):
        subprocess.run(  # noqa: S603 - fixed interpreter/module, no shell
            [executable, "run", "--output", name, *extra],
            cwd=root,
            check=True,
        )
        report = json.loads(
            (root / name / "results/reports/combined.json").read_bytes()
        )
        metrics = {item["name"]: item["value"] for item in report["metrics"]}
        if metrics["authorization_decision_accuracy"] != (1.0 if not extra else 6 / 7):
            raise RuntimeError("incorrect demonstration accuracy")
        if metrics["excess_authority_rate"] != (0.0 if not extra else 1 / 4):
            raise RuntimeError("incorrect false-allow rate")
        html = (root / name / "results/policy-comparison.html").read_text(
            encoding="utf-8"
        )
        if "Not measured:" not in html or "CONTAINS REFERENCE TRUTH" not in html:
            raise RuntimeError("missing report boundaries")
    public = "world/benchmark/public"
    public_trees = [
        {
            path.relative_to(root / name / public): path.read_bytes()
            for path in (root / name / public).rglob("*")
            if path.is_file()
        }
        for name in ("baseline", "broken")
    ]
    if public_trees[0] != public_trees[1]:
        raise RuntimeError("policy toggle changed the public world")
print(
    "Installed demo: isolated import, both policies, identical public world verified."
)
