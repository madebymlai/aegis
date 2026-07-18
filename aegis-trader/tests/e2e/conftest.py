"""Fresh-process isolation for Nautilus engine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

_E2E_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run each e2e test in a fresh Python subprocess.

    Nautilus initializes process-global runtime state for engine/node objects.
    Isolating e2e tests keeps those globals from poisoning other engine tests or
    later unit tests that construct TradingNodes.
    """
    for item in items:
        if item.path.is_relative_to(_E2E_DIR):
            item.add_marker(pytest.mark.isolated)
