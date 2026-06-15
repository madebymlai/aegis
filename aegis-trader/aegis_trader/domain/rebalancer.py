"""Pure-domain rebalancer: per-sleeve target weights -> WeightDelta[].

Zero Nautilus, zero sizing.  The rebalancer works entirely in dimensionless
weight space (fractions of NAV); turning a weight delta into a native share
count is a separate concern (``sizing.size_deltas``).

Netting (Slice 2):
- Each sleeve's latest target weights are scaled by the risk-budget allocator.
- Allocator-scaled weights are netted per FIGI across all sleeves.
- A non-zero net delta becomes a WeightDelta; its sign is the trade side.
- Two sleeves sharing an instrument collapse to a single delta for the residual.

Realized-book gate (Slice 4):
- Asymmetric drift bands (band_up, band_down) per instrument suppress
  unnecessary trading when the realized position is still within tolerance.
- The realized post-band book is gated against gross/net/per-name caps.
- A per-name cap breach triggers deterministic widen-to-compliance (ignore
  bands, trade back to the cap); an unfixable breach raises (fail closed).
- An aggregate drift threshold trips when the book has drifted too far from
  intent.
"""

from __future__ import annotations

import pandas as pd

from aegis_trader.domain.allocator import (
    allocate_covariance_vol_target,
    allocate_diagonal_vol_target,
)
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.types import Figi, SleeveName, WeightDelta

_ZERO_GUARD = 1e-12


def rebalance(
    sleeve_targets: dict[SleeveName, pd.DataFrame],
    book: BookConfig,
    *,
    realized_weights: dict[str, float] | None = None,
    realized_vols: dict[SleeveName, float] | None = None,
    realized_covariance: dict[SleeveName, dict[SleeveName, float]] | None = None,
    realized_drawdown: float | None = None,
) -> tuple[WeightDelta, ...]:
    """Net per-sleeve target weights into signed weight deltas to trade.

    *sleeve_targets* maps each sleeve name to its most-recent target-weight
    DataFrame (index=time, columns=FIGI).  Only sleeves listed in *book* are
    processed; sleeves missing from the dict or with empty DataFrames are
    silently skipped.

    Each sleeve's latest row is scaled by the risk-budget allocator, then all
    scaled weights are netted per FIGI.

    *realized_weights* maps FIGI string -> current realized weight (signed
    fraction of NAV).  When supplied, the realised book is gated against caps and
    drift bands before any delta is emitted.

    *realized_covariance* is the covariance-aware allocator input.  During
    warmup callers pass ``None`` and the allocator falls back to raw risk
    shares.  ``realized_vols`` is retained for the diagonal tracer path and is
    used only when covariance is absent.  ``realized_drawdown`` is the current
    book drawdown fraction; when the book declares a drawdown-de-lever curve it
    scales the whole allocation down after risk budgeting.

    Returns the signed weight deltas to trade (fraction of NAV); converting a
    delta to a share quantity is the sizing step's job (``sizing.size_deltas``).
    """
    # -- Step 1: net allocator-scaled target weights across sleeves --
    latest_targets: dict[SleeveName, dict[str, float]] = {}
    for sleeve in book.sleeves:
        target = sleeve_targets.get(sleeve.name)
        if target is None or target.empty:
            continue  # silently skip sleeves without data
        latest_targets[sleeve.name] = _latest_target_weights(target)

    risk_shares = {sleeve.name: sleeve.risk_share for sleeve in book.sleeves}
    if realized_covariance is not None:
        allocation = allocate_covariance_vol_target(
            sleeve_targets=latest_targets,
            risk_shares=risk_shares,
            realized_covariance=realized_covariance,
            book_vol_target=book.book_vol_target,
            groups={sleeve.name: sleeve.group for sleeve in book.sleeves},
            realized_drawdown=realized_drawdown,
            drawdown_delever_curve=book.drawdown_delever,
        )
    else:
        allocation = allocate_diagonal_vol_target(
            sleeve_targets=latest_targets,
            risk_shares=risk_shares,
            realized_vols=realized_vols,
            book_vol_target=book.book_vol_target,
            realized_drawdown=realized_drawdown,
            drawdown_delever_curve=book.drawdown_delever,
        )

    net_target_by_figi: dict[str, float] = {}
    for scaled_targets in allocation.scaled_targets.values():
        for figi_key, scaled in scaled_targets.items():
            if abs(scaled) < _ZERO_GUARD:
                continue
            net_target_by_figi[figi_key] = net_target_by_figi.get(figi_key, 0.0) + scaled

    # -- Step 2: net -> band -> post-execution book projection --
    rw = realized_weights or {}
    all_figis = net_target_by_figi.keys() | rw.keys()
    post_book: dict[str, float] = dict(rw)  # start from realised

    # Book-level fidelity trip (ADR-0002): when the realised book has drifted too
    # far from intent — typically many within-band drifts accumulating — force a
    # *fuller cleanup* this rebalance: ignore the per-instrument bands and trade
    # every position back to target.  The hard caps (Steps 3-4) still run, so a
    # book that cannot be made compliant fails closed.
    force_cleanup = False
    if rw and book.aggregate_drift_threshold is not None:
        agg_drift = sum(abs(net_target_by_figi.get(f, 0.0) - rw.get(f, 0.0)) for f in all_figis)
        force_cleanup = agg_drift > book.aggregate_drift_threshold

    deltas: list[WeightDelta] = []

    for figi_key in all_figis:
        target_w = net_target_by_figi.get(figi_key, 0.0)
        realized_w = rw.get(figi_key, 0.0)
        has_realized = figi_key in rw

        if abs(target_w) < _ZERO_GUARD and abs(realized_w) < _ZERO_GUARD:
            continue

        delta = target_w - realized_w

        # -- band gate (skipped on a forced full cleanup) --
        if has_realized and not force_cleanup:
            band_up, band_down = book.band_for(figi_key)

            if delta > 0 and delta <= band_down:
                # realised below target but within lower band -> no trade
                post_book[figi_key] = realized_w
                continue
            if delta < 0 and -delta <= band_up:
                # realised above target but within upper band -> no trade
                post_book[figi_key] = realized_w
                continue

        # Outside band (or no band) -> trade delta.
        if abs(delta) < _ZERO_GUARD:
            post_book[figi_key] = realized_w
            continue

        deltas.append(WeightDelta(figi=Figi(figi_key), delta=delta))
        post_book[figi_key] = target_w

    # -- Step 3: per-name cap gate on the realised book (widen-to-compliance) --
    _gate_per_name_caps(rw, targets=net_target_by_figi, post_book=post_book,
                        deltas=deltas, book=book)

    # -- Step 4: gross / net caps (always checked on post_book; the fidelity
    #    cleanup above stays subordinate to these hard caps — fail closed) --
    _gate_book_caps(post_book, book)

    return tuple(deltas)


def _latest_target_weights(target: pd.DataFrame) -> dict[str, float]:
    latest = target.iloc[-1]
    return {str(col): float(latest[col]) for col in latest.index}


def _gate_per_name_caps(
    realized: dict[str, float],
    targets: dict[str, float],
    post_book: dict[str, float],
    deltas: list[WeightDelta],
    book: BookConfig,
) -> None:
    """Gate realised positions against the per-name cap.

    If a realised position breaches the per-name cap and no corrective delta was
    emitted (because the band suppressed it), widen-to-compliance: insert a
    corrective delta that brings the position to the cap boundary.  Being at the
    cap is acceptable in a breach situation — we don't demand the full target.

    If the target itself exceeds the cap (unfixable), raise.
    """
    if book.per_name_cap is None or not realized:
        return

    for figi_key, real_w in realized.items():
        if abs(real_w) <= book.per_name_cap + _ZERO_GUARD:
            continue

        # Breach: realised |weight| > per_name_cap.
        target_w = targets.get(figi_key, 0.0)

        # If target itself exceeds cap -> unfixable, fail closed.
        if abs(target_w) > book.per_name_cap + _ZERO_GUARD:
            raise ValueError(
                f"FIGI {figi_key}: target weight {abs(target_w):.6f} exceeds "
                f"per-name cap {book.per_name_cap:.6f} — unfixable"
            )

        # Check if a corrective delta already exists (from the band gate).
        already_correcting = any(d.figi.value == figi_key for d in deltas)
        if already_correcting:
            pw = post_book.get(figi_key, 0.0)
            if abs(pw) > book.per_name_cap + _ZERO_GUARD:
                raise ValueError(
                    f"FIGI {figi_key} cap breach ({abs(real_w):.6f} > "
                    f"{book.per_name_cap:.6f}) cannot be remedied: "
                    f"post-execution weight {abs(pw):.6f} still exceeds cap"
                )
            continue

        # No corrective delta — widen: bring to the cap boundary.
        cap_w = book.per_name_cap if real_w > 0 else -book.per_name_cap
        delta = cap_w - real_w
        if abs(delta) < _ZERO_GUARD:
            continue

        deltas.append(WeightDelta(figi=Figi(figi_key), delta=delta))
        post_book[figi_key] = cap_w


def _gate_book_caps(
    post_book: dict[str, float],
    book: BookConfig,
) -> None:
    """Gate the post-execution book against gross and net caps.

    Always checked, regardless of whether realised positions are supplied.
    """
    if book.gross_cap is not None:
        gross = sum(abs(w) for w in post_book.values())
        if gross > book.gross_cap + _ZERO_GUARD:
            raise ValueError(
                f"Gross exposure {gross:.6f} exceeds cap {book.gross_cap:.6f}"
            )

    if book.net_cap is not None:
        net = abs(sum(post_book.values()))
        if net > book.net_cap + _ZERO_GUARD:
            raise ValueError(
                f"Net exposure {net:.6f} exceeds cap {book.net_cap:.6f}"
            )
