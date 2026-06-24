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
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest
from aegis_data.rebasing import Rebasing, ratio_rebasing, spread_rebasing
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import SleeveName
from nautilus_trader.model.identifiers import InstrumentId

_MOM = SleeveName("mom")
_ROOT = InstrumentId.from_str("ES.XCME")  # the stable continuous-root id (re-bases at a roll)

# Final-basis (research) continuous closes; a roll occurs before index _ROLL. Returns vary so the
# covariance/skew are non-degenerate.
_RESEARCH_CLOSES = [100.0, 103.0, 101.0, 105.0, 102.0, 106.0, 104.0, 108.0]
_ROLL = 4  # observations [0.._ROLL) are pre-roll; [_ROLL:] are post-roll

# Each case: the Rebasing applied at the roll, and how a final-basis close looks in the OLD (pre-roll)
# basis (the inverse of the carry). spread: old = final − Δ; ratio: old = final / k. Δ/k are large so a
# missed re-base is unmistakable; the ratio factor is a power of two so the round-trip is bit-exact.
_CASES: dict[str, tuple[Rebasing, Callable[[float], float]]] = {
    "spread": (spread_rebasing(50.0), lambda close: close - 50.0),
    "ratio": (ratio_rebasing(2.0), lambda close: close / 2.0),
}


def _record(ledger: SleeveLedger, close: float) -> None:
    """Record one full-weight single-root observation at *close*."""
    ledger.record(
        nav=1_000_000.0,
        realized_weights={_ROOT: 1.0},
        sleeve_targets={_MOM: {_ROOT: 1.0}},
        closes={_ROOT: close},
    )


def _ledger(closes: Sequence[float]) -> SleeveLedger:
    """A single-sleeve, single-root ledger recording one observation per close (full weight)."""
    ledger = SleeveLedger()
    for close in closes:
        _record(ledger, close)
    return ledger


def _live_ledger_across_roll(rebasing: Rebasing, to_old: Callable[[float], float]) -> SleeveLedger:
    """The live ledger: pre-roll closes in the OLD basis, ``rebase_closes`` at the roll (as the feed
    re-materializes the re-based series), then post-roll closes in the new basis."""
    ledger = SleeveLedger()
    for close in _RESEARCH_CLOSES[:_ROLL]:
        _record(ledger, to_old(close))
    ledger.rebase_closes({_ROOT: rebasing})
    for close in _RESEARCH_CLOSES[_ROLL:]:
        _record(ledger, close)
    return ledger


@pytest.mark.parametrize("case", ["spread", "ratio"])
def test_ledger_allocator_input_matches_research_across_a_roll_via_rebase(case: str) -> None:
    """Golden: a live ledger that re-bases its recorded history at the roll (additively for spread,
    multiplicatively for ratio) produces the SAME allocator inputs as the single-basis research ledger —
    byte-identical covariance and book skew, with no cross-basis return at the roll period."""
    rebasing, to_old = _CASES[case]
    live = _live_ledger_across_roll(rebasing, to_old)
    research = _ledger(_RESEARCH_CLOSES)

    live_cov = live.realized_covariance((_MOM,), min_returns=6)
    research_cov = research.realized_covariance((_MOM,), min_returns=6)
    live_skew = live.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6)
    research_skew = research.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6)

    assert live_cov is not None
    assert (live_cov, live_skew) == (research_cov, research_skew)


def test_ledger_is_invariant_when_there_is_no_roll() -> None:
    """GREEN control: with no re-base, live and research record identical closes, so the allocator
    inputs are byte-identical — confirming the construction is otherwise sound."""
    research = _ledger(_RESEARCH_CLOSES)
    live_no_roll = _ledger(_RESEARCH_CLOSES)

    assert live_no_roll.realized_covariance((_MOM,), min_returns=6) == research.realized_covariance(
        (_MOM,), min_returns=6
    )
    assert live_no_roll.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6) == (
        research.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6)
    )
