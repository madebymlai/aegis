"""Per-root roll-sensitivity check for continuous-future bundles (aegis-rd-tkj5.2).

A continuous future is re-based at every roll under the contract-declared
adjustment mode: ``BACKWARD_RATIO`` scales prior history multiplicatively,
``BACKWARD_SPREAD`` shifts it additively. An allocation that reads a root's
absolute price level therefore computes a different value before vs after a
roll and silently desyncs the live book from research.

This module is a deterministic *metamorphic check*, not a proof over arbitrary
Strategy code: for each declared continuous root independently it applies the
mode's transform to that root's native price columns, recomputes the decision
through the caller-supplied composition (currency conversion + Components),
and requires labels, shape, and values to be unchanged. Passing means the
current allocation survived the configured native roll probes; failing
demonstrates observed roll sensitivity.

Roots roll independently, so each root is probed alone — cross-root features
(``ES/NQ`` under a common scale, ``ES-NQ`` under a common shift) that would
survive an all-roots-at-once transform are still rejected.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import numpy as np
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.domain.market_data import MarketDataBundle
from aegis_runtime.domain.rebasing import RebasingParameters, rebasing_for_adjustment

if TYPE_CHECKING:
    import pandas as pd

    from aegis_runtime.execution.bundle import DataContract

# Arrays whose root columns are known to be re-based by a continuous-future roll.
# This is deliberately not currency conversion's denomination rule: unknown Custom
# Data kinds are currently provider-fetched records and are skipped here, while an
# unknown Array with a live FX leg must be refused. That skip ceases to be safe when
# a price-derived Custom Array is introduced; it must then be classified explicitly.
# See ADR-0011.
_ROLL_REBASED_ARRAYS = frozenset({"Open", "High", "Low", "Close"})
_PROBE_REBASING_PARAMETERS = RebasingParameters(
    additive_delta=137.0,
    multiplicative_factor=1.37,
)

# Explicit comparison tolerances, in final weight space.
_RTOL = 0.0
_ATOL = 1e-9


class RollSensitivityError(ValueError):
    """A continuous-root bundle whose allocation moved under a native roll probe."""


def compute_roll_checked_weights(
    *,
    contract: DataContract,
    native_window: MarketDataBundle,
    decide: Callable[[MarketDataBundle], pd.DataFrame],
) -> pd.DataFrame:
    """Decide weights and require them to survive each root's native roll probe.

    ``decide`` is the one composed decision path (native arrays -> currency
    conversion -> Components); the baseline and every probe invoke exactly it,
    so a contract with R roots executes it ``1 + R`` times and an ETF-only
    contract executes it once with no perturbation work.

    The callback inversion is deliberate: this gate owns the baseline/per-root
    evaluation loop, probe exception wrapping, structural/value comparison, and
    operator guidance. Moving that control into the bundle would leak all four
    responsibilities across the boundary and make both modules shallower.
    """
    baseline = decide(native_window)
    roots = contract.continuous_instrument_ids
    if not roots:
        return baseline
    mode = contract.adjustment_mode
    assert mode is not None  # DataContract enforces mode-iff-futures
    failing: list[InstrumentId] = []
    for root in roots:
        perturbed = _perturb_root(native_window, root, mode)
        try:
            probe = decide(perturbed)
        except Exception as error:
            raise RollSensitivityError(
                f"roll-sensitivity probe for continuous root {root.value!r} under "
                f"{mode.value!r} failed to recompute: {error}"
            ) from error
        if not _weights_match(baseline, probe):
            failing.append(root)
    if failing:
        raise RollSensitivityError(_failure_guidance(mode, failing))
    return baseline


def _perturb_root(
    window: MarketDataBundle,
    root: InstrumentId,
    mode: ContinuousFutureAdjustmentType,
) -> MarketDataBundle:
    """Apply the mode's uniform transform to one root's native price columns."""
    rebasing = rebasing_for_adjustment(mode, _PROBE_REBASING_PARAMETERS)
    perturbed: dict[str, pd.DataFrame] = {}
    for name, frame in window.arrays.items():
        if name in _ROLL_REBASED_ARRAYS and root in frame.columns:
            frame = frame.copy()
            frame[root] = frame[root].map(rebasing.apply)
        perturbed[name] = frame
    return MarketDataBundle(perturbed)


def _weights_match(baseline: pd.DataFrame, probe: pd.DataFrame) -> bool:
    if baseline.shape != probe.shape:
        return False
    if not baseline.index.equals(probe.index):
        return False
    if list(baseline.columns) != list(probe.columns):
        return False
    return bool(
        np.allclose(
            baseline.to_numpy(),
            probe.to_numpy(),
            rtol=_RTOL,
            atol=_ATOL,
            equal_nan=True,
        )
    )


def _failure_guidance(
    mode: ContinuousFutureAdjustmentType,
    failing: Sequence[InstrumentId],
) -> str:
    roots = sorted(instrument_id.value for instrument_id in failing)
    if mode.is_ratio:
        guidance = (
            "under ratio re-basing every roll scales the root's prior history, so "
            "the allocation must be multiplicatively stable - use percentage/"
            "return-based or otherwise scale-invariant features."
        )
    else:
        guidance = (
            "under spread re-basing every roll shifts the root's prior history in "
            "its NATIVE quote currency, so the Strategy must be stable under a "
            "native additive re-base after projection through its declared "
            "currency view. Note that with a moving FX rate a base-currency "
            "difference acquires shift * delta(FX) and may correctly fail here."
        )
    return (
        f"metamorphic check failed: observed roll sensitivity for continuous "
        f"root(s) {roots} under declared adjustment mode {mode.value!r}. The "
        f"decided weights changed when the root's native price history was "
        f"re-based the way its next roll will re-base it; {guidance}"
    )


__all__ = ["RollSensitivityError", "compute_roll_checked_weights"]
