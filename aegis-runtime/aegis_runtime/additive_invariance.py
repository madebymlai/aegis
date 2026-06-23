"""Additive-invariance enforcement for continuous-future roots (r8b.9 Slice F).

A continuous future is re-based by a *uniform additive shift* of all prior history at
every roll (``BACKWARD_SPREAD``). A feature read off the **absolute price level** of a
continuous root therefore computes a different value before vs after a roll — it silently
desyncs the live book from research (the ``live@T ≡ research`` contract); a **difference**
feature is invariant, because the shift cancels.

This module turns that from a documented hope into an enforced property: re-base a bundle's
continuous-root price columns by a constant and require the recomputed allocation to be
unchanged. ``ExecutionBundle.compute_weights`` calls it on the real window, so a continuous-
root bundle that allocates off absolute levels fails loudly at the allocation boundary
rather than drifting at the next roll.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import numpy as np
from nautilus_trader.model.identifiers import InstrumentId

if TYPE_CHECKING:
    import pandas as pd

    from aegis_runtime.bundle import MarketDataBundle

# OHLC are absolute price levels that a roll re-bases; Volume is not a price, so it is left
# untouched. The shift is arbitrary — invariance is exact-to-tolerance regardless of size.
_PRICE_ARRAYS = frozenset({"Open", "High", "Low", "Close"})
_REBASE_SHIFT = 137.0
_TOLERANCE = 1e-9


class AbsolutePriceLevelError(ValueError):
    """A continuous-root bundle whose allocation moves under a uniform price re-base."""


def assert_additive_invariance(
    *,
    weights: pd.DataFrame,
    recompute: Callable[[MarketDataBundle], pd.DataFrame],
    window: MarketDataBundle,
    continuous_ids: Sequence[InstrumentId],
) -> None:
    """Require *weights* to survive a uniform re-base of the continuous-root price columns.

    Re-bases *window*'s continuous-root price columns by a constant, recomputes the
    allocation via *recompute*, and raises :class:`AbsolutePriceLevelError` if it differs
    from *weights*. A no-op when *continuous_ids* is empty — native instruments never
    re-base, so an absolute-level feature over them is safe.
    """
    if not continuous_ids:
        return
    rebased = recompute(_rebase(window, continuous_ids))
    if not np.allclose(weights.to_numpy(), rebased.to_numpy(), atol=_TOLERANCE, equal_nan=True):
        roots = sorted({instrument_id.symbol.value for instrument_id in continuous_ids})
        raise AbsolutePriceLevelError(
            f"continuous-future root column(s) {roots} drive an absolute-price-level "
            f"allocation: weights changed under a uniform re-base (+{_REBASE_SHIFT}). A "
            f"continuous future is re-based at every roll, so this silently desyncs "
            f"live-vs-research — use difference-based features."
        )


def _rebase(
    window: MarketDataBundle, continuous_ids: Sequence[InstrumentId]
) -> MarketDataBundle:
    targets = set(continuous_ids)
    rebased: dict[str, pd.DataFrame] = {}
    for name, frame in window.arrays.items():
        if name in _PRICE_ARRAYS:
            frame = frame.copy()
            columns = [column for column in frame.columns if column in targets]
            frame[columns] = frame[columns] + _REBASE_SHIFT
        rebased[name] = frame
    return type(window)(rebased)
