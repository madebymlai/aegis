"""The equity-Book annualization convention (aegis-rd-9qkr.7).

One named internal convention for the currently supported equity Book: daily
realized-risk rows annualize over 252 trading days, and Nautilus annualized
performance statistics are constructed with the same period.  It is not
operator configuration, not an Execution Bundle fact, and never inferred from
Sleeve timeframes, callback counts, or observed timestamp gaps.  A concrete
future Book (e.g. 24/7 venues) may promote a convention into Book Config;
until then this module is the sole owner.
"""

from __future__ import annotations

EQUITY_BOOK_ANNUALIZATION_PERIODS: float = 252.0

__all__ = ["EQUITY_BOOK_ANNUALIZATION_PERIODS"]
