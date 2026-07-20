from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def test_unexplained_skip_makes_a_nested_pytest_run_fail() -> None:
    project_root = Path(__file__).parents[1]
    with TemporaryDirectory(prefix=".honesty-probe-", dir=project_root) as directory:
        probe = Path(directory) / "test_unexplained_skip.py"
        probe.write_text(
            "import pytest\n\n"
            "def test_probe():\n"
            "    pytest.skip('the honesty gate must reject this')\n",
            encoding="utf-8",
        )
        result = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
            [sys.executable, "-m", "pytest", "-q", "--no-cov", str(probe)],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1
    assert "Unexplained skipped tests are forbidden" in output


def test_six_quarantines_make_a_nested_pytest_run_fail_collection() -> None:
    project_root = Path(__file__).parents[1]
    with TemporaryDirectory(prefix=".honesty-probe-", dir=project_root) as directory:
        probe = Path(directory) / "test_quarantine_cap.py"
        probe.write_text(
            "import pytest\n\n"
            "@pytest.mark.parametrize('case', range(6))\n"
            "@pytest.mark.quarantine(issue='HONESTY-GATE-PROBE')\n"
            "def test_probe(case):\n"
            "    assert case >= 0\n",
            encoding="utf-8",
        )
        result = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
            [sys.executable, "-m", "pytest", "-q", "--no-cov", str(probe)],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "quarantine cap exceeded: 6/5" in output
