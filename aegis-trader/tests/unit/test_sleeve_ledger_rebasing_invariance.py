"""Ledger re-basing invariance (aegis-rd-iwx; was r8b.9 additive-invariance).

A back-adjusted continuous future re-bases its whole price history at each roll — additively under a
spread mode, multiplicatively under a ratio mode.  The ``SleeveLedger`` records the absolute close per
period and ``_sleeve_period_return`` computes ``curr/prev − 1`` across adjacent periods, which feed the
allocator (``realized_covariance`` / ``realized_book_skew``).  If pre-roll closes stayed in the OLD basis
while post-roll closes arrived in the NEW basis, the roll-period return would be a cross-basis ratio that
desyncs ``live`` from ``research``.

``rebase_closes`` carries the recorded history into the new basis via a :class:`Rebasing`, so the invariant

    live (re-basing) ledger allocator inputs  ==  research (single-basis) ledger inputs

holds for BOTH modes — the algebra is the Rebasing's, not the ledger's, so flipping the one adjustment-mode
constant switches the live re-basing with no ledger edit.

How *exact* that agreement is differs by mode, and the test asserts each honestly rather than rigging an
exact match:

  * **Spread** carry is additive (``close + Δ``).  With a tick-valued Δ it introduces no rounding, so the
    live carry reproduces the single-basis research read **bit-for-bit** — asserted with ``==``.
  * **Ratio** carry is multiplicative (``close × factor``).  The materializer quantizes every adjusted
    price to the instrument tick, but the ledger does NOT re-quantize after multiplying its stored closes,
    so the live carry agrees with research only to **floating-point tolerance** — sub-tick, here ≈5e-6 on
    the covariance and ≈3e-5 on the skew, negligible for the allocator but NOT byte-exact.  A power-of-two
    factor would hide this; the deliberately non-dyadic factor below exposes it.  Asserted with
    ``pytest.approx``.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from aegis_data.rebasing import Rebasing, ratio_rebasing, spread_rebasing
from aegis_trader.domain.analytics_horizon import derive_horizon
from aegis_trader.domain.sleeve_ledger import BookObservation, SleeveLedger
from aegis_trader.domain.types import SleeveName
from nautilus_trader.model.identifiers import InstrumentId

_MOM = SleeveName("mom")
_ROOT = InstrumentId.from_str(
    "ES.XCME"
)  # the stable continuous-root id (re-bases at a roll)

_PRECISION = 2  # the instrument tick: the materializer rounds every adjusted close to this many dp
_ROLL = 4  # observations [0.._ROLL) are pre-roll; [_ROLL:] are post-roll
# The un-quantized ratio carry drifts ~2e-4 from the quantized research read (over the completed-day
# EWMA window); this tolerance clears that with margin yet is astronomically below a real cross-basis
# error (order 1), so a missed re-base fails.
_RATIO_CARRY_TOL = 5e-4

# Raw front-leg closes (already tick-valued), one observation per period; the front segment carries no
# adjustment (offset 0 / factor 1), so a period recorded live IS its raw close.  Returns vary so the
# covariance/skew are non-degenerate.
_RAW_CLOSES = [100.00, 103.00, 101.00, 105.00, 102.00, 106.00, 104.00, 108.00]

# The roll's re-basing per mode, and whether the live carry is bit-exact.  spread: a large tick-valued
# additive offset, so the carry round-trips exactly.  ratio: a non-power-of-two factor (≈1.529), so the
# un-quantized carry drifts sub-tick from the quantized research read.  Both are large enough that a
# MISSED re-base is unmistakable, not lost in the tolerance.
_CASES: dict[str, tuple[Rebasing, bool]] = {
    "spread": (spread_rebasing(50.0), True),
    "ratio": (ratio_rebasing(145.70 / 95.30), False),
}


_DAY_NS = 86_400_000_000_000


def _weekday_ns(index: int) -> int:
    weeks, weekday = divmod(index, 5)
    return (4 + weeks * 7 + weekday) * _DAY_NS


def _record(ledger: SleeveLedger, close: float, day: int) -> None:
    """Record one full-weight single-root observation at *close* on *day*."""
    ledger.record(
        BookObservation(
            timestamp_ns=_weekday_ns(day),
            nav=1_000_000.0,
            realized_weights={_ROOT: 1.0},
            sleeve_targets={_MOM: {_ROOT: 1.0}},
            marks={_ROOT: close},
        )
    )


def _ledger(closes: Sequence[float]) -> SleeveLedger:
    """A single-sleeve, single-root ledger recording one observation per close (full weight)."""
    ledger = SleeveLedger(horizon=derive_horizon(("1D",)))
    for day, close in enumerate(closes):
        _record(ledger, close, day)
    return ledger


def _research_closes(rebasing: Rebasing) -> list[float]:
    """The closes a single end-to-end materialization yields: each pre-roll raw close carried into the
    final basis and quantized to the instrument tick (the materializer rounds every adjusted price),
    then the post-roll front closes recorded as-is."""
    pre_roll = [
        round(rebasing.apply(close), _PRECISION) for close in _RAW_CLOSES[:_ROLL]
    ]
    return pre_roll + list(_RAW_CLOSES[_ROLL:])


def _live_ledger_across_roll(rebasing: Rebasing) -> SleeveLedger:
    """The live ledger: pre-roll closes recorded in the OLD basis (the front — offset 0 / factor 1 — so the
    raw close), then ``rebase_closes`` carries the recorded history into the new basis as the feed
    re-materializes; the ledger multiplies/shifts its stored closes and does NOT re-quantize to the tick."""
    ledger = SleeveLedger(horizon=derive_horizon(("1D",)))
    for day, close in enumerate(_RAW_CLOSES[:_ROLL]):
        _record(ledger, close, day)
    ledger.rebase_closes({_ROOT: rebasing})
    for day, close in enumerate(_RAW_CLOSES[_ROLL:], start=_ROLL):
        _record(ledger, close, day)
    return ledger


@pytest.mark.parametrize("case", ["spread", "ratio"])
def test_ledger_allocator_input_matches_research_across_a_roll_via_rebase(
    case: str,
) -> None:
    """Golden: a live ledger that re-bases its recorded history at the roll (additively for spread,
    multiplicatively for ratio) produces the SAME allocator inputs as the single-basis research ledger —
    bit-for-bit for the additive spread carry, to floating-point tolerance for the un-quantized
    multiplicative ratio carry — with no cross-basis return at the roll period."""
    rebasing, bit_exact = _CASES[case]
    live = _live_ledger_across_roll(rebasing)
    research = _ledger(_research_closes(rebasing))

    live_cov = live.realized_covariance((_MOM,), min_returns=6)
    research_cov = research.realized_covariance((_MOM,), min_returns=6)
    live_skew = live.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6)
    research_skew = research.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6)

    assert live_cov is not None
    assert research_cov is not None
    if bit_exact:
        assert (live_cov, live_skew) == (research_cov, research_skew)
        return
    for sleeve, row in live_cov.items():
        assert row == pytest.approx(research_cov[sleeve], rel=_RATIO_CARRY_TOL)
    assert live_skew == pytest.approx(research_skew, rel=_RATIO_CARRY_TOL)


def test_ledger_is_invariant_when_there_is_no_roll() -> None:
    """GREEN control: with no re-base, live and research record identical closes, so the allocator
    inputs are byte-identical — confirming the construction is otherwise sound."""
    research = _ledger(_RAW_CLOSES)
    live_no_roll = _ledger(_RAW_CLOSES)

    assert live_no_roll.realized_covariance(
        (_MOM,), min_returns=6
    ) == research.realized_covariance((_MOM,), min_returns=6)
    assert live_no_roll.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6) == (
        research.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6)
    )
