"""Cross-market comparison of the variance-gap structural break.

Question this module answers: given a per-market ``StructuralBreakResult`` (each
market's own pre/post-2012-08 raw variance-gap means — computed by
``eu_variance_premium.model.structural_break_test``, reused here rather than
reimplemented), is one market's change across the break distinguishable from
another's? That is the cross-sectional question the brief asks: does the US flatten
uniquely, or do other markets flatten too?

This treats each market's break test as statistically independent of every other's,
purely for lack of a joint estimate. That is an approximation, and probably an
optimistic one: equity variance genuinely co-moves across markets (a global vol spike
shows up in the VIX, VSTOXX, and India VIX the same week), so the combined standard
error below understates the truly joint one and overstates how distinguishable two
markets' changes are. There is no accessible free-data way to estimate the cross-market
covariance of these changes, so this comparison is directional evidence, not a
rigorously joint test — the README states this every time the comparison is reported.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from _prototyping.eu_variance_premium.model import StructuralBreakResult


@dataclass(frozen=True)
class ChangeComparison:
    """Whether ``other``'s break-change is distinguishable from ``reference``'s."""

    reference_label: str
    other_label: str
    reference_change: float
    other_change: float
    difference_of_changes: float
    z_statistic: float
    p_value: float


def compare_break_changes(
    reference: StructuralBreakResult,
    other: StructuralBreakResult,
    *,
    reference_label: str,
    other_label: str,
) -> ChangeComparison:
    """Compare two markets' post-minus-pre changes via an independent-samples z-test.

    Each side's own change already carries a standard error, implicit in
    ``structural_break_test``'s own pre/post Newey-West standard errors; this combines
    those two (assumed independent — see the module docstring) rather than recomputing
    anything HAC-related from scratch.
    """
    reference_se = _difference_standard_error(reference)
    other_se = _difference_standard_error(other)
    difference_of_changes = other.difference - reference.difference
    combined_se = float(np.sqrt(reference_se**2 + other_se**2))
    z_statistic = (
        difference_of_changes / combined_se if combined_se > 0.0 else float("nan")
    )
    p_value = (
        float(2.0 * stats.norm.sf(abs(z_statistic)))
        if np.isfinite(z_statistic)
        else float("nan")
    )
    return ChangeComparison(
        reference_label=reference_label,
        other_label=other_label,
        reference_change=reference.difference,
        other_change=other.difference,
        difference_of_changes=difference_of_changes,
        z_statistic=z_statistic,
        p_value=p_value,
    )


def _difference_standard_error(result: StructuralBreakResult) -> float:
    """The standard error of ``result.difference`` — the same quantity
    ``structural_break_test`` computes internally to test that difference against zero,
    recomputed here (one line, from its already-public pre/post fields) rather than
    changing that function's return type to expose it."""
    return float(np.sqrt(result.pre.standard_error**2 + result.post.standard_error**2))
