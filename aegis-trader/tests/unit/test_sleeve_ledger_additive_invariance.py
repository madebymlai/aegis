"""Ledger additive-invariance golden (r8b.9 §3 — the model-independent must-fix).

A back-adjusted continuous future re-bases its whole price history by a uniform additive
shift Δ at each roll (BACKWARD_SPREAD: newest = offset 0, older segments shift up).  The
``SleeveLedger`` records the absolute close per period and ``_sleeve_period_return`` computes
``curr/prev − 1`` across adjacent periods.  Those returns feed the allocator
(``pipeline.py:252`` → ``realized_covariance`` → covariance-aware ``rebalance_plan``; also
``realized_book_skew``).  If pre-roll closes stayed frozen in the OLD basis while post-roll
closes arrived in the NEW basis, the roll-period return would divide a new-basis ``curr`` by a
frozen old-basis ``prev`` — a cross-basis ratio that desyncs ``live`` from ``research``.

The invariant the r8b.9 additive-invariance AC must hold:

    live (forward-rebasing) ledger allocator inputs  ==  research (single-basis) ledger inputs

This pins it directly on the real ``SleeveLedger`` — no inference about pipeline wiring.  We
feed two ledgers the *same* economic path, differing only in basis bookkeeping:
  - **research** records every period in the final basis (the whole series re-based once);
  - **live** records pre-roll periods in the OLD basis (q − Δ), then — as the feed
    re-materializes the series at the roll — calls ``rebase_closes({root: Δ})`` to shift its
    recorded history into the new basis, then records post-roll periods in the new basis (q).

``rebase_closes`` keeps the whole recorded history in ONE basis, so every return — pre-roll, the
roll period, and after — is computed in a single consistent basis, exactly as research does.  The
golden asserts the resulting allocator inputs are byte-identical.  Two GREEN controls localise the
mechanism to the re-base: restricting the window to post-roll agrees (no re-base needed there), and
a no-roll path agrees (Δ=0) — so the golden's agreement is the re-base, nothing else.
"""

from __future__ import annotations

from collections.abc import Sequence

from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import SleeveName
from nautilus_trader.model.identifiers import InstrumentId

_MOM = SleeveName("mom")
_ROOT = InstrumentId.from_str("ES.XCME")  # the stable continuous-root id (re-bases at a roll)

# Final-basis (research) continuous closes; a roll occurs before index _ROLL with cumulative
# spread shift Δ = _DELTA. Returns vary so the covariance/skew are non-degenerate.
_RESEARCH_CLOSES = [100.0, 103.0, 101.0, 105.0, 102.0, 106.0, 104.0, 108.0]
_ROLL = 4          # observations [0.._ROLL) are pre-roll; [_ROLL:] are post-roll
_DELTA = 50.0      # the roll's cumulative additive re-base (large, so the failure is unmistakable)

# Live records pre-roll periods in the OLD basis (final − Δ), post-roll in the final basis.
_LIVE_CLOSES = [c - _DELTA for c in _RESEARCH_CLOSES[:_ROLL]] + _RESEARCH_CLOSES[_ROLL:]


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


def _live_ledger_across_roll() -> SleeveLedger:
    """The live ledger: pre-roll closes in the OLD basis, ``rebase_closes`` at the roll (as the
    feed re-materializes the re-based series), then post-roll closes in the new basis."""
    ledger = SleeveLedger()
    for close in _LIVE_CLOSES[:_ROLL]:
        _record(ledger, close)
    ledger.rebase_closes({_ROOT: _DELTA})
    for close in _LIVE_CLOSES[_ROLL:]:
        _record(ledger, close)
    return ledger


def test_ledger_allocator_input_matches_research_across_a_roll_via_rebase() -> None:
    """Golden: a forward-rebasing live ledger that re-bases its recorded history at the roll
    produces the SAME allocator inputs as the single-basis research ledger — byte-identical
    covariance and book skew, with no cross-basis return at the roll period."""
    live, research = _live_ledger_across_roll(), _ledger(_RESEARCH_CLOSES)

    # window spans the roll (last 7 of 8 observations -> 6 return rows including the roll pair)
    live_cov = live.realized_covariance((_MOM,), min_returns=6)
    research_cov = research.realized_covariance((_MOM,), min_returns=6)
    live_skew = live.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6)
    research_skew = research.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6)

    assert live_cov is not None
    assert (live_cov, live_skew) == (research_cov, research_skew)


def test_ledger_allocator_input_agrees_when_window_is_entirely_post_roll() -> None:
    """GREEN control: restricted to post-roll observations (all in the final basis on both
    sides), live and research agree exactly — so the divergence above is the roll, not the harness."""
    live, research = _ledger(_LIVE_CLOSES), _ledger(_RESEARCH_CLOSES)

    # last 4 observations are indices 4..7 == post-roll on both ledgers (identical closes)
    live_cov = live.realized_covariance((_MOM,), min_returns=3)
    research_cov = research.realized_covariance((_MOM,), min_returns=3)

    assert live_cov is not None
    assert live_cov == research_cov


def test_ledger_is_additive_invariant_when_there_is_no_roll() -> None:
    """GREEN control: with no re-base (Δ=0), live and research record identical closes, so the
    allocator inputs are byte-identical — confirming the construction is otherwise sound."""
    research = _ledger(_RESEARCH_CLOSES)
    live_no_roll = _ledger(_RESEARCH_CLOSES)  # no basis shift anywhere

    assert live_no_roll.realized_covariance((_MOM,), min_returns=6) == research.realized_covariance(
        (_MOM,), min_returns=6
    )
    assert live_no_roll.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6) == (
        research.realized_book_skew({_MOM: 1.0}, (_MOM,), min_returns=6)
    )
