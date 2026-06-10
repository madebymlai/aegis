"""Unit tests for the programmatic ``SignalConfig`` surface.

``SignalConfig`` is constructed in code (not parsed from a Run Config file), so its
catalog membership rules — ``policy ∈ SIGNAL_POLICIES`` and ``execution_timing ∈
SIGNAL_EXECUTION_TIMINGS`` — must be enforced at construction.
"""

from __future__ import annotations

import pytest

from research.aegis_research.configuration import SignalConfig


def test_unknown_signal_policy_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="policy"):
        SignalConfig(policy="momentum_crossover")


def test_unknown_execution_timing_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="execution_timing"):
        SignalConfig(execution_timing="yesterday_close")


def test_default_construction_yields_the_catalog_defaults() -> None:
    config = SignalConfig()

    assert config.policy == "long_only_hysteresis"
    assert config.execution_timing == "next_open"


def test_unknown_field_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="short_entry_threshold"):
        SignalConfig(short_entry_threshold=0.45)
