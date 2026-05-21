from __future__ import annotations

import subprocess
from pathlib import Path

from research.aegis_research.component_registry import discover_component_registry


def test_empty_project_component_roots_are_discoverable_and_public_snapshot_is_path_safe() -> None:
    registry = discover_component_registry()

    assert registry.ids("indicators") == ()
    assert registry.ids("strategies") == ()
    assert "repo_relative_path" not in str(registry.public_snapshot())


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
        "indicators": "docs/examples/components/indicator_component_example.py",
        "strategies": "docs/examples/components/strategy_component_example.py",
    }.items():
        readme = Path(f"research/components/{family}/README.md").read_text()

        assert example in readme
        assert "ignored by git" in readme
        assert "not secret management" in readme
