from __future__ import annotations

import subprocess
from pathlib import Path


def test_component_roots_ignore_local_files_except_readme_placeholders() -> None:
    for family in ("indicators", "strategies"):
        ignored_python = subprocess.run(
            [
                "git",
                "check-ignore",
                "--no-index",
                "--quiet",
                f"research/components/{family}/local.py",
            ],
            check=False,
        )
        ignored_readme = subprocess.run(
            [
                "git",
                "check-ignore",
                "--no-index",
                "--quiet",
                f"research/components/{family}/README.md",
            ],
            check=False,
        )

        assert ignored_python.returncode == 0
        assert ignored_readme.returncode == 1

    assert Path("research/components/indicators/README.md").is_file()
    assert Path("research/components/strategies/README.md").is_file()


def test_component_readme_placeholders_point_to_examples_and_warn_about_ignored_files() -> None:
    for family, example in {
        "indicators": "research/aegis_research/component_registry/indicator_example.py",
        "strategies": "research/aegis_research/component_registry/strategy_example.py",
    }.items():
        readme = Path(f"research/components/{family}/README.md").read_text()

        assert example in readme
        assert "ignored by git" in readme
        assert "not secret management" in readme
