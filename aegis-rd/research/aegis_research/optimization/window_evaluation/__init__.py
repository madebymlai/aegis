"""Window Evaluation: the one deep module for portfolio simulation.

The package interface is exactly two names — :class:`WindowEvaluator`
(``evaluate(range_, **params)`` plus the seam-cost query
``non_executable_rows(window_index)``) and :class:`ResolvedBook` (the
run-constant terms a Run's simulation trades every Candidate's book under,
resolved once from the declared config). Everything else — the VBT engine
wiring, drift-band gating, short financing carry, margin interest,
distributions, terminal liquidation, Exposure Validation wiring, the NoCash
tripwire — is implementation, private to this package (ADR-0026).

The underscore submodules are an internal seam: this module's own mechanics
tests cross it deliberately, because the Portfolio object they assert on never
crosses ``evaluate`` (the evaluator emits metric frames). Production code and
other packages import from this ``__init__`` only; its surface is pinned by a
facade-surface test.
"""

from research.aegis_research.optimization.window_evaluation.evaluator import (
    WindowEvaluator,
)
from research.aegis_research.optimization.window_evaluation.resolved_book import (
    ResolvedBook,
)

__all__ = [
    "ResolvedBook",
    "WindowEvaluator",
]
