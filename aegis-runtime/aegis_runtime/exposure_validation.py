"""Fail-closed Exposure Validation gate for signed target-weight frames.

A **Strategy** speaks final **signed** target weights (positive = long, negative =
short); there is nothing left to normalize, so this module neither sizes nor mutates
weights. It only gates each rebalance row against the **Exposure Limits**: **gross**
(``Σ|wᵢ| ≤ gross_cap``), **net** (``|Σwᵢ| ≤ net_cap``), and the admissible
**Direction** sign. A market-neutral book is ``net_cap ≈ 0``.

This is the single home of the gate semantics on both sides of the Execution Bundle
seam: the bundle gates a single book before weights leave it, and research gates
candidate-expanded frames before simulation by passing ``group_by`` — an opaque
per-column label array reduced independently per group. The kernel never learns what
a group *is*; ``describe_group`` lets the caller phrase the offender in its own
vocabulary (e.g. ``candidate 'x'``).
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

_EXPOSURE_TOLERANCE = 1e-9
# A declared Direction fixes the admissible sign of every emitted weight, mirroring
# VBT's ``Direction`` enum (the same string is passed to ``from_optimizer``). ``both``
# admits either sign; ``longonly``/``shortonly`` are the fail-closed sign guard that the
# gross/net caps cannot supply — a ``[+.5,+.5] → [-.5,+.5]`` flip keeps gross = 1 and
# net = 0, so only this sign check catches it.
_SIGN_GUARDS: dict[str, str] = {"longonly": "≥ 0", "shortonly": "≤ 0", "both": "any"}


@dataclass(frozen=True)
class ExposureLimits:
    """Validated Exposure Limits: the caps a signed target-weight book must satisfy.

    An instance is proof the triple is legal: ``gross_cap > 0``, ``direction`` is one
    of ``longonly``/``shortonly``/``both``, and an omitted ``net_cap`` resolves to
    ``gross_cap`` (a no-op bound, since ``|Σwᵢ| ≤ Σ|wᵢ| ≤ gross_cap``).
    """

    gross_cap: float
    net_cap: float | None = None
    direction: str = "both"

    def __post_init__(self) -> None:
        gross_cap = float(self.gross_cap)
        if gross_cap <= 0:
            raise ValueError(f"gross_cap must be > 0; got {self.gross_cap!r}")
        if self.direction not in _SIGN_GUARDS:
            raise ValueError(
                f"direction must be one of {sorted(_SIGN_GUARDS)}; got {self.direction!r}"
            )
        net_cap = gross_cap if self.net_cap is None else float(self.net_cap)
        object.__setattr__(self, "gross_cap", gross_cap)
        object.__setattr__(self, "net_cap", net_cap)


def validate_exposure(
    allocations: pd.DataFrame,
    limits: ExposureLimits,
    *,
    group_by: pd.Index | Sequence[Hashable] | None = None,
    describe_group: Callable[[Hashable], str] | None = None,
) -> None:
    """Fail-closed gross/net/sign gate over a signed target-weight frame.

    Pure validation — never mutates the frame; an empty or columnless frame is a
    no-op. The sign guard runs over the whole frame first, then gross, then net.

    ``group_by=None`` gates the frame as one book. A label array (one hashable per
    column) gates each distinct label's columns independently — vectorized, one
    groupby pass — and a breach names the worst offender via ``describe_group``
    (default ``group {key!r}``). All breaches raise ``ValueError``.
    """
    if allocations.empty or len(allocations.columns) == 0:
        return
    _assert_sign_consistent(allocations.to_numpy(dtype=float, copy=False), limits.direction)
    if group_by is None:
        gross = allocations.abs().sum(axis=1)
        if (gross > limits.gross_cap + _EXPOSURE_TOLERANCE).any():
            raise ValueError(
                f"gross exposure Σ|wᵢ| {float(gross.max())} exceeds gross_cap {limits.gross_cap}"
            )
        net = allocations.sum(axis=1).abs()
        if (net > limits.net_cap + _EXPOSURE_TOLERANCE).any():
            raise ValueError(
                f"net exposure |Σwᵢ| {float(net.max())} exceeds net_cap {limits.net_cap}"
            )
        return
    labels = np.asarray(group_by, dtype=object)
    if len(labels) != len(allocations.columns):
        raise ValueError(
            f"group_by has {len(labels)} labels; allocations has "
            f"{len(allocations.columns)} columns"
        )
    describe = describe_group if describe_group is not None else _describe_group
    gross = allocations.abs().T.groupby(labels, sort=False).sum().T
    net = allocations.T.groupby(labels, sort=False).sum().T.abs()
    _assert_group_cap(gross, limits.gross_cap, "gross", "Σ|wᵢ|", describe)
    _assert_group_cap(net, limits.net_cap, "net", "|Σwᵢ|", describe)


def _describe_group(key: Hashable) -> str:
    return f"group {key!r}"


def _assert_group_cap(
    per_group: pd.DataFrame,
    cap: float,
    name: str,
    expr: str,
    describe: Callable[[Hashable], str],
) -> None:
    """Raise, naming the worst-offending group, when a per-group cap is breached."""
    worst_per_group = per_group.max(axis=0)
    if (worst_per_group > cap + _EXPOSURE_TOLERANCE).any():
        offender = worst_per_group.idxmax()
        raise ValueError(
            f"{describe(offender)} {name} exposure {expr} "
            f"{float(worst_per_group.max())} exceeds {name}_cap {cap}"
        )


def _assert_sign_consistent(decided: np.ndarray, direction: str) -> None:
    """Fail closed when a weight's sign contradicts the declared Direction."""
    if direction == "longonly":
        offenders = decided < -_EXPOSURE_TOLERANCE
    elif direction == "shortonly":
        offenders = decided > _EXPOSURE_TOLERANCE
    else:
        return
    if offenders.any():
        offending = float(decided[offenders][0])
        raise ValueError(
            f"target_weights has weight {offending} violating direction "
            f"{direction!r} (requires wᵢ {_SIGN_GUARDS[direction]})"
        )
