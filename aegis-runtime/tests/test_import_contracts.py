"""Architecture contracts run with the ordinary test suite on every CI platform."""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_runtime_import_contracts() -> None:
    project_root = Path(__file__).parents[1]
    result = subprocess.run(
        ["lint-imports", "--config", str(project_root / ".importlinter")],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
