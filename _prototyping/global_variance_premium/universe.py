"""The candidate market universe for the cross-market variance-gap comparison.

Every entry in ``MARKETS`` was verified retrievable via yfinance (real ticker, plausible
vol-index level range, pre-2012 history) before being included — see README.md
"Coverage" for the full probe log. ``FAILED_CANDIDATES`` records every ticker that was
tried and did *not* work, so the failures are part of the reported result, not silently
dropped. Re-run ``--probe`` (see ``__main__.py``) to reproduce both lists live.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketSpec:
    """One market's paired implied-vol index and underlying equity index tickers."""

    label: str
    vol_ticker: str
    equity_ticker: str
    note: str


# Markets with a real, retrievable implied-vol index AND equity index, both with usable
# pre-2012-08 history. Europe (VSTOXX) is deliberately not here: it has no Yahoo ticker
# at all and is loaded from eu_variance_premium's checked-in STOXX fixture instead (see
# __main__.py) — a different loading path, folded into the same per-market report.
MARKETS: tuple[MarketSpec, ...] = (
    MarketSpec(
        label="US (S&P 500)",
        vol_ticker="^VIX",
        equity_ticker="^GSPC",
        note="primary US benchmark — Dew-Becker & Giglio's own market",
    ),
    MarketSpec(
        label="US (Nasdaq 100)",
        vol_ticker="^VXN",
        equity_ticker="^NDX",
        note="US robustness check only — not a distinct country",
    ),
    MarketSpec(
        label="US (Dow)",
        vol_ticker="^VXD",
        equity_ticker="^DJI",
        note="US robustness check only — not a distinct country",
    ),
    MarketSpec(
        label="India (Nifty 50)",
        vol_ticker="^INDIAVIX",
        equity_ticker="^NSEI",
        note="only non-US, non-EU market found with both a real vol index and pre-2012 history",
    ),
    MarketSpec(
        label="Australia (ASX 200)",
        vol_ticker="^AXVI",
        equity_ticker="^AXJO",
        note="S&P/ASX 200 VIX; vol-index history begins 2008, so pre-2012 window is short",
    ),
)

# Tickers tried and confirmed NOT retrievable via yfinance (empty history, delisted, or
# 404), one row per (market, guessed ticker). Kept here — not deleted — because the
# brief asked for failures to be part of the reported coverage, and because a future
# reader should not have to re-derive "no, that one doesn't work either" from scratch.
FAILED_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("UK FTSE 100 vol index", "^VFTSE"),
    ("Germany DAX vol index (VDAX-NEW)", "^VDAX"),
    ("Germany DAX vol index (VDAX-NEW), alt 1", "^V1XI"),
    ("Germany DAX vol index (VDAX-NEW), alt 2", "VDAXNEW.DE"),
    ("Germany DAX vol index, alt ticker", "^VDAXNEW"),
    ("Germany/Europe short-dated vol index", "^V1X"),
    ("Japan Nikkei 225 vol index (Nikkei VI)", "^JNIV"),
    ("Japan Nikkei 225 vol index, alt 1", "^VXJ"),
    ("Japan Nikkei 225 vol index, alt 2", "^N225VI"),
    ("Hong Kong Hang Seng vol index (VHSI)", "^VHSI"),
    ("Korea KOSPI vol index (VKOSPI)", "^VKOSPI"),
    ("Korea KOSPI vol index, alt ticker", "^KOSPIVIX"),
    ("Switzerland SMI vol index (VSMI)", "^VSMI"),
    ("Brazil Bovespa vol index", "^VIBOVESPA"),
    ("Brazil Bovespa vol index, alt ticker", "^VBOV"),
    ("Canada TSX vol index", "^VIXC"),
    ("Canada TSX vol index, alt ticker", "^TSXVIX"),
    ("China CSI/Shanghai vol index (CBOE VXFXI)", "^VXFXI"),  # resolves, 1 obs — junk
    ("Taiwan TAIEX vol index, alt 1", "^TVIX"),  # resolves, 1 obs — junk, not the TAIEX
    ("Taiwan TAIEX vol index, alt 2", "^TAIEXVIX"),
    ("US Russell 2000 vol index (RVX)", "^RVX"),
    ("Emerging-markets ETF vol index (CBOE VXEEM)", "^VXEEM"),  # resolves, 1 obs — junk
    ("Japan ETF vol index (CBOE VXEWJ)", "^VXEWJ"),
    ("Europe VSTOXX, direct ticker guess", "^V2TX"),
    ("Europe VSTOXX, alt ticker guess", "^VSTOXX"),
)

# CBOE does publish ETF-implied-vol indices for a couple of these markets (VXEWZ for
# Brazil via EWZ, VXEFA for developed EAFE ex-US/Canada via EFA), but both series'
# Yahoo history starts 2023-06-26 — entirely post-break — so neither can support a
# pre/post-2012-08 comparison and both are excluded from MARKETS rather than force-fit
# with a break date their data can't test.
TOO_SHORT_FOR_A_PRE_2012_COMPARISON: tuple[tuple[str, str, str], ...] = (
    ("Brazil ETF vol index (CBOE VXEWZ, via EWZ)", "^VXEWZ", "2023-06-26 onward only"),
    ("EAFE ETF vol index (CBOE VXEFA, via EFA)", "^VXEFA", "2023-06-26 onward only"),
)
