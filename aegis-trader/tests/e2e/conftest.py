"""E2E test isolation for Nautilus engine global state."""

from __future__ import annotations

from pathlib import Path

import pytest

_E2E_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run each e2e test in a forked process.

    Nautilus initializes process-global runtime state for engine/node objects.
    Forking e2e tests keeps those globals from poisoning later unit tests that
    construct TradingNodes.
    """
    for item in items:
        if item.path.is_relative_to(_E2E_DIR):
            item.add_marker(pytest.mark.forked)
