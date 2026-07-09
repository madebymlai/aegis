"""Pure-domain rebalancer: per-sleeve target weights -> WeightDelta[].

Zero Nautilus, zero sizing.  The rebalancer works entirely in dimensionless
weight space (fractions of NAV); turning a weight delta into a native share
count is a separate concern (``sizing.size_deltas``).

Netting (Slice 2):
- Each sleeve's latest target weights are scaled by the risk-budget allocator.
- Allocator-scaled weights are netted per InstrumentId across all sleeves.
- A non-zero net delta becomes a WeightDelta; its sign is the trade side.
- Two sleeves sharing an instrument collapse to a single delta for the residual.

Realized-book gate (Slice 4):
- Asymmetric drift bands (band_up, band_down) per instrument suppress
  unnecessary trading when the realized position is still within tolerance.
- The realized post-band book is gated against gross/net/per-name caps; the
  gross/net gate is the kernel-owned Exposure Validation module
  (``aegis_runtime.validate_exposure``, root ADR-0008).
- A per-name cap breach triggers deterministic widen-to-compliance (ignore
  bands, trade back to the cap); an unfixable breach raises (fail closed).
- An aggregate drift threshold trips when the book has drifted too far from
  intent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import pandas as pd
from aegis_runtime import DriftBand, validate_exposure
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.domain.allocator import Allocation, SleeveWeightBand, allocate
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.types import SleeveName, WeightDelta

_ZERO_GUARD = 1e-12


@dataclass(frozen=True)
class RebalancePlan:
    """Pure rebalance decision plus sleeve weights applied by the allocator."""

    deltas: tuple[WeightDelta, ...]
    applied_sleeve_weights: Mapping[SleeveName, float]


class PerNameExposureBreach(ValueError):
    """A final or unfixable position exceeds Trader's per-name cap."""


def rebalance(
    sleeve_targets: dict[SleeveName, pd.DataFrame],
    book: BookConfig,
    *,
    instrument_bands: Mapping[InstrumentId, DriftBand],
    band_owners: Mapping[InstrumentId, SleeveName] | None = None,
    realized_weights: dict[InstrumentId, float] | None = None,
    realized_vols: dict[SleeveName, float] | None = None,
    realized_covariance: dict[SleeveName, dict[SleeveName, float]] | None = None,
    previous_sleeve_weights: dict[SleeveName, float] | None = None,
    realized_drawdown: float | None = None,
) -> tuple[WeightDelta, ...]:
    """Net per-sleeve target weights into signed weight deltas to trade."""
    return rebalance_plan(
        sleeve_targets,
        book,
        instrument_bands=instrument_bands,
        band_owners=band_owners,
        realized_weights=realized_weights,
        realized_vols=realized_vols,
        realized_covariance=realized_covariance,
        previous_sleeve_weights=previous_sleeve_weights,
        realized_drawdown=realized_drawdown,
    ).deltas


def rebalance_plan(
    sleeve_targets: dict[SleeveName, pd.DataFrame],
    book: BookConfig,
    *,
    instrument_bands: Mapping[InstrumentId, DriftBand],
    band_owners: Mapping[InstrumentId, SleeveName] | None = None,
    realized_weights: dict[InstrumentId, float] | None = None,
    realized_vols: dict[SleeveName, float] | None = None,
    realized_covariance: dict[SleeveName, dict[SleeveName, float]] | None = None,
    previous_sleeve_weights: dict[SleeveName, float] | None = None,
    realized_drawdown: float | None = None,
) -> RebalancePlan:
    """Net per-sleeve target weights into a complete rebalance plan.

    *sleeve_targets* maps each sleeve name to its most-recent target-weight
    DataFrame (index=time, columns=InstrumentId).  Only sleeves listed in *book* are
    processed; sleeves missing from the dict or with empty DataFrames are
    silently skipped.

    Each sleeve's latest row is scaled by the risk-budget allocator, then all
    scaled weights are netted per InstrumentId.

    *instrument_bands* maps each current bundle-owned :class:`InstrumentId` to the
    research-validated drift band.  A realised instrument absent from this map is no
    longer in any current bundle and trades straight to its target.

    *band_owners* maps each banded instrument to the sleeve whose bundle carries
    its band.  Bundle bands are calibrated at standalone-sleeve scale (weight
    points of the research book); the allocator scales the owning sleeve's targets
    by its multiplier, so the band is scaled by the same factor before gating —
    research calibration transfers exactly.  Without an owner (or owner map) the
    band applies unscaled.

    *realized_weights* maps each covered :class:`InstrumentId` -> current realized
    weight (signed fraction of NAV).  When supplied, the realised book is gated against
    caps and drift bands before any delta is emitted.

    *realized_covariance* and *realized_vols* are handed to the allocator as-is;
    which estimate refines the configured risk shares (covariance-aware ERC/HRP,
    the diagonal limit, or a cold book on the raw shares) is the allocator's own
    routing (``allocator.allocate``).
    ``realized_drawdown`` is the current
    book drawdown fraction; when the book declares a drawdown-de-lever curve it
    scales the whole allocation down after risk budgeting.

    ``previous_sleeve_weights`` and the sleeve-band parameters carry the
    per-sleeve no-churn bands from the previous rebalance (Slice 4.3).

    Returns the signed weight deltas to trade (fraction of NAV) and the applied
    sleeve weights that Strategy keeps for the next period's sleeve-band check.
    Converting a delta to a share quantity is the sizing step's job
    (``sizing.size_deltas``).
    """
    # -- Step 1: net allocator-scaled target weights across sleeves --
    latest_targets: dict[SleeveName, dict[InstrumentId, float]] = {}
    for sleeve in book.sleeves:
        target = sleeve_targets.get(sleeve.name)
        if target is None or target.empty:
            continue  # silently skip sleeves without data
        latest_targets[sleeve.name] = _latest_target_weights(target)

    allocation = _allocate_sleeves(
        latest_targets,
        book,
        realized_vols=realized_vols,
        realized_covariance=realized_covariance,
        previous_sleeve_weights=previous_sleeve_weights,
        realized_drawdown=realized_drawdown,
    )

    net_target_by_instrument_id: dict[InstrumentId, float] = {}
    for scaled_targets in allocation.scaled_targets.values():
        for instrument_id, scaled in scaled_targets.items():
            if abs(scaled) < _ZERO_GUARD:
                continue
            net_target_by_instrument_id[instrument_id] = (
                net_target_by_instrument_id.get(instrument_id, 0.0) + scaled
            )

    net_target_by_instrument_id = _clamp_to_max_gross(net_target_by_instrument_id, book)

    # -- Step 2: net -> band -> post-execution book projection --
    rw = realized_weights or {}
    # Stable, sorted iteration over the netted-vs-realised instrument union: a bare
    # set union is hash-seed-dependent, which makes the agg-drift float sum and
    # the emitted delta order (hence order-submission sequence) vary run-to-run
    # and the whole backtest non-reproducible (aegis-rd-10d).
    all_instrument_ids = sorted(
        net_target_by_instrument_id.keys() | rw.keys(),
        key=lambda instrument_id: instrument_id.value,
    )
    post_book: dict[InstrumentId, float] = dict(rw)  # start from realised

    # Book-level fidelity trip (ADR-0002): when the realised book has drifted too
    # far from intent — typically many within-band drifts accumulating — force a
    # *fuller cleanup* this rebalance: ignore the per-instrument bands and trade
    # every position back to target.  The hard caps (Steps 3-4) still run, so a
    # book that cannot be made compliant fails closed.
    force_cleanup = False
    if rw and book.aggregate_drift_threshold is not None:
        agg_drift = sum(
            abs(net_target_by_instrument_id.get(instrument_id, 0.0) - rw.get(instrument_id, 0.0))
            for instrument_id in all_instrument_ids
        )
        force_cleanup = agg_drift > book.aggregate_drift_threshold

    deltas: list[WeightDelta] = []

    for instrument_id in all_instrument_ids:
        target_w = net_target_by_instrument_id.get(instrument_id, 0.0)
        realized_w = rw.get(instrument_id, 0.0)

        if abs(target_w) < _ZERO_GUARD and abs(realized_w) < _ZERO_GUARD:
            continue

        # -- band gate (skipped on a forced full cleanup) --
        band = _sleeve_scaled_band(
            instrument_bands.get(instrument_id),
            owner=(band_owners or {}).get(instrument_id),
            multipliers=allocation.multipliers,
            previous_sleeve_weights=previous_sleeve_weights or {},
        )
        resolved_w = (
            target_w
            if force_cleanup or band is None
            else band.resolve(
                realized=realized_w,
                target=target_w,
            )
        )
        delta = resolved_w - realized_w

        # Outside band (or no band) -> trade delta; inside band -> hold realized.
        if abs(delta) < _ZERO_GUARD:
            post_book[instrument_id] = realized_w
            continue

        deltas.append(WeightDelta(instrument_id=instrument_id, delta=delta))
        post_book[instrument_id] = resolved_w

    # -- Step 3: per-name cap gate on the realised book (widen-to-compliance) --
    _gate_per_name_caps(
        rw,
        targets=net_target_by_instrument_id,
        post_book=post_book,
        deltas=deltas,
        book=book,
    )

    # -- Step 3.5: down-only clamp on the PROJECTED book --
    # Step 1 clamps the *target* to max_book_gross, but within-band, untraded
    # names keep their drifted realised weight, so the projected post-execution
    # book can still exceed the ceiling.  Re-apply the same down-only clamp to
    # the projection and re-derive the deltas (the bands yield to the clamp), so
    # the hard gross gate below is not tripped by a vol-target / drift overshoot.
    # Net is intentionally NOT scaled here: a directional (net) breach is an
    # anomaly that must surface at the gate, not be silently shrunk.
    clamped_post_book = _clamp_to_max_gross(post_book, book)
    if clamped_post_book is not post_book:
        post_book = clamped_post_book
        deltas = _deltas_from_realized(post_book, rw)

    # -- Step 4: final planned-book caps --
    _gate_book_caps(post_book, book)

    return RebalancePlan(
        deltas=tuple(deltas),
        applied_sleeve_weights=MappingProxyType(dict(allocation.multipliers)),
    )


def _sleeve_scaled_band(
    band: DriftBand | None,
    *,
    owner: SleeveName | None,
    multipliers: Mapping[SleeveName, float],
    previous_sleeve_weights: Mapping[SleeveName, float],
) -> DriftBand | None:
    """The bundle band at the owning sleeve's current book scale.

    A bundle band is absolute weight points of the *standalone research book*;
    the allocator scales the sleeve's targets by its multiplier, so gating with
    the unscaled band blocks every open once the sleeve runs severalfold
    smaller (aegis-rd-reyj).  A sleeve absent from this period's allocation
    falls back to its previously applied weight; with no owner at all the band
    applies unscaled.
    """
    if band is None or owner is None:
        return band
    scale = multipliers.get(owner)
    if scale is None:
        scale = previous_sleeve_weights.get(owner, 1.0)
    return DriftBand(
        up=band.up * scale,
        down=band.down * scale,
        destination_fraction=band.destination_fraction,
    )


def _allocate_sleeves(
    latest_targets: dict[SleeveName, dict[InstrumentId, float]],
    book: BookConfig,
    *,
    realized_vols: dict[SleeveName, float] | None,
    realized_covariance: dict[SleeveName, dict[SleeveName, float]] | None,
    previous_sleeve_weights: dict[SleeveName, float] | None,
    realized_drawdown: float | None = None,
) -> Allocation:
    """Adapt *book* facts to allocator kwargs; the allocator owns the routing."""
    return allocate(
        sleeve_targets=latest_targets,
        risk_shares=book.allocator_risk_shares(),
        book_vol_target=book.book_vol_target,
        realized_vols=realized_vols,
        realized_covariance=realized_covariance,
        groups={sleeve.name: sleeve.group for sleeve in book.sleeves},
        previous_multipliers=previous_sleeve_weights,
        sleeve_weight_bands=_sleeve_weight_bands(book),
        sleeve_reversion_fraction=book.sleeve_reversion_fraction,
        realized_drawdown=realized_drawdown,
        drawdown_delever_curve=book.drawdown_delever,
    )


def _sleeve_weight_bands(book: BookConfig) -> dict[SleeveName, SleeveWeightBand]:
    return {
        sleeve.name: SleeveWeightBand(
            down=sleeve.weight_band_down,
            up=sleeve.weight_band_up,
        )
        for sleeve in book.sleeves
    }


def _latest_target_weights(target: pd.DataFrame) -> dict[InstrumentId, float]:
    latest = target.iloc[-1]
    return {_target_instrument_id(col): float(latest[col]) for col in latest.index}


def _target_instrument_id(column: object) -> InstrumentId:
    if isinstance(column, InstrumentId):
        return column
    raise ValueError(f"target weight columns must be InstrumentId values; got {column!r}")


def _gate_per_name_caps(
    realized: dict[InstrumentId, float],
    targets: dict[InstrumentId, float],
    post_book: dict[InstrumentId, float],
    deltas: list[WeightDelta],
    book: BookConfig,
) -> None:
    """Remediate realized breaches, then gate every planned position.

    If a realised position breaches the per-name cap and no corrective delta was
    emitted (because the band suppressed it), widen-to-compliance: insert a
    corrective delta that brings the position to the cap boundary.  Being at the
    cap is acceptable in a breach situation — we don't demand the full target.

    If the target itself exceeds the cap (unfixable), raise.
    """
    if book.per_name_cap is None:
        return

    for instrument_id, real_w in realized.items():
        if abs(real_w) <= book.per_name_cap + _ZERO_GUARD:
            continue

        # Breach: realised |weight| > per_name_cap.
        target_w = targets.get(instrument_id, 0.0)

        # If target itself exceeds cap -> unfixable, fail closed.
        if abs(target_w) > book.per_name_cap + _ZERO_GUARD:
            raise PerNameExposureBreach(
                f"InstrumentId {instrument_id.value}: target weight {abs(target_w):.6f} exceeds "
                f"per-name cap {book.per_name_cap:.6f} — unfixable"
            )

        # Check if a corrective delta already exists (from the band gate).
        already_correcting = any(d.instrument_id == instrument_id for d in deltas)
        if already_correcting:
            pw = post_book.get(instrument_id, 0.0)
            if abs(pw) > book.per_name_cap + _ZERO_GUARD:
                raise PerNameExposureBreach(
                    f"InstrumentId {instrument_id.value} cap breach ({abs(real_w):.6f} > "
                    f"{book.per_name_cap:.6f}) cannot be remedied: "
                    f"post-execution weight {abs(pw):.6f} still exceeds cap"
                )
            continue

        # No corrective delta — widen: bring to the cap boundary.
        cap_w = book.per_name_cap if real_w > 0 else -book.per_name_cap
        delta = cap_w - real_w
        if abs(delta) < _ZERO_GUARD:
            continue

        deltas.append(WeightDelta(instrument_id=instrument_id, delta=delta))
        post_book[instrument_id] = cap_w

    for instrument_id, weight in post_book.items():
        if abs(weight) > book.per_name_cap + _ZERO_GUARD:
            raise PerNameExposureBreach(
                f"InstrumentId {instrument_id.value}: projected weight {abs(weight):.6f} "
                f"exceeds per-name cap {book.per_name_cap:.6f}"
            )


def _clamp_to_max_gross(
    net_target_by_instrument_id: dict[InstrumentId, float], book: BookConfig
) -> dict[InstrumentId, float]:
    """Down-only vol-target clamp (ADR-0004 amendment).

    Vol-targeting may over-lever an unlevered book when realized volatilities are
    low.  Scale the netted book down so its gross does not exceed
    ``max_book_gross``; never scale it up — when the book is already within the
    ceiling it is returned unchanged.  The gross/net cap gate downstream remains
    the authoritative hard backstop.
    """
    gross = sum(abs(w) for w in net_target_by_instrument_id.values())
    if gross <= book.max_book_gross:
        return net_target_by_instrument_id
    clamp = book.max_book_gross / gross
    return {
        instrument_id: weight * clamp
        for instrument_id, weight in net_target_by_instrument_id.items()
    }


def _deltas_from_realized(
    post_book: dict[InstrumentId, float], realized: dict[InstrumentId, float]
) -> list[WeightDelta]:
    """Signed weight deltas to move from *realized* to *post_book* (all names).

    Used after the projected book is clamped down to the gross ceiling: every
    position — including previously within-band ones — gets the corrective trade
    that realises the clamped book.
    """
    deltas: list[WeightDelta] = []
    for instrument_id, weight in post_book.items():
        delta = weight - realized.get(instrument_id, 0.0)
        if abs(delta) >= _ZERO_GUARD:
            deltas.append(WeightDelta(instrument_id=instrument_id, delta=delta))
    return deltas


def _gate_book_caps(
    post_book: dict[InstrumentId, float],
    book: BookConfig,
) -> None:
    """Gate the post-execution book through the kernel Exposure Validation module.

    The Rebalancer owns projection and remediation (bands, clamps,
    widen-to-compliance); the gross/net inequalities, tolerance, and error
    vocabulary are the kernel gate's (root ADR-0008, Trader ADR-0002).  Always
    checked, regardless of whether realised positions are supplied; breaches
    raise ``GrossExposureBreach`` / ``NetExposureBreach``.
    """
    validate_exposure(pd.DataFrame([post_book]), book.exposure_limits)
