# %% component overview
# Demeter-EU credit carry — the EU-RETAIL-TRADABLE concave pole, same role as the
# demeter.vol_carry champion (the short-gamma carry mirror of atalanta's long-gamma trend)
# but built only from plain UCITS bond ETFs, so an EU retail investor can actually hold it.
# The VRP champion needs short VIX futures / inverse-vol ETPs, which UCITS bans for retail
# (leveraged-short exposure) — re-mapping cannot rescue it. Credit carry harvests the SAME
# crash-risk premium through a different face of it: Koijen-Moskowitz-Pedersen and Menkhoff
# et al. show credit/FX carry and the variance risk premium load on one volatility factor,
# so long credit IS a diluted-but-real expression of short variance. Validated as a genuine
# concave pole (full-window screening gate, long HY ~ this signal): qskew -0.79, crash
# -0.75%, Sharpe +0.42 — milder than VRP's -1.18 / -0.95% / +0.57 but clears the same gate,
# and unlike VRP it is UCITS-tradable. (See research/vault/runs/demeter/ for the A/B.)
#
# SIGNAL vs EXECUTION are split and hidden here, mirroring demeter.vol_carry:
#   - SIGNAL = the US credit-risk carry, the spread of Moody's Baa corporate yield over the
#     10y Treasury (FRED DBAA - DGS10), pulled INLINE from the FRED API. The carry is the
#     spread RICHNESS: spread / its own trailing mean, clipped >= 0 (lean in when paid more
#     than usual to bear credit risk; never go short credit). NOTE we deliberately do NOT use
#     the ICE BofA OAS series (BAMLH0A0HYM2 etc.): ICE license-clamps those on FRED to the
#     trailing ~3 years, which excludes the 2020/2022 crises a concave pole must be gated on.
#     Baa-minus-Treasury is the non-ICE, full-history, free equivalent.
#   - EXECUTION = long USD credit UCITS ETF(s); the spread sizes the whole credit book and
#     demeter.carryStraddle vol-balances across the legs (HY higher-vol, IG lower-vol).
#
# HOW TO USE / SWITCH THE EXECUTION INSTRUMENT (a one-line config change):
#   The config universe is one or more LONG-credit UCITS ETFs (no signal feeds — the carry
#   feed is the inline FRED pull, not a panel column):
#     symbols: ['IHYU.L', 'LQDE.L', 'IEMB.L']   # USD HY / IG / EM-sovereign, all London
#   Every credit vehicle is held LONG (+1) to earn its spread; _credit_sign validates the
#   ticker against _CREDIT_LONG and raises on an unknown one (fail-loud), so a typo cannot
#   silently weight a non-credit instrument. To trade a new credit ETF, add its ticker to
#   _CREDIT_LONG — that one edit makes the symbol swap correct.

# %% imports
import numpy as np
import pandas as pd

# FRED credit-carry feed (signal-only, pulled inline; never a traded column).
_FRED_KEY = "6b0bb1a2e9343b395c582035dda1e470"  # personal-use key; configs are gitignored
_BAA = "DBAA"     # Moody's Seasoned Baa Corporate Bond Yield (daily, %), full history
_UST10 = "DGS10"  # 10y Treasury constant maturity (daily, %), full history
_FRED_CACHE: dict[str, pd.Series] = {}

# Credit vehicle polarity: every credit instrument is held LONG (+1) to harvest its spread.
# There is no short-credit carry analog (you are paid to BEAR credit risk, not to shed it),
# so unlike vol_carry there is a single polarity set. A column not listed raises in
# _credit_sign rather than being weighted with a guessed sign.
_CREDIT_LONG = frozenset({
    # US-listed (research/backtest, longest history)
    "HYG", "JNK", "HYLD", "LQD", "EMB", "EMHY",
    # EU-retail UCITS (London, USD-denominated)
    "IHYU.L", "LQDE.L", "IEMB.L", "SEMB.L",
    # duration-stripped: iShares $ Corp Bond Interest-Rate-Hedged (long IG, rates removed
    # inside the wrapper) — the carry_duration.yaml pole leg.
    "LQDH.L",
    # The same London UCITS names as venue-qualified Nautilus instrument ids — the column
    # labels the pipeline delivers since the instrument-id rename (matched via str(col)).
    "IHYU.LSEETF", "LQDE.LSEETF", "IEMB.LSEETF", "SEMB.LSEETF", "LQDH.LSEETF",
    # SOTA-pole legs (carry.yaml): short-duration HY (defensive tilt; iShares SDHY /
    # PIMCO STHY) and EM local-currency sovereigns (IEML — the FX-carry skew source). All
    # held LONG to harvest their carry; the common spread richness sizes the whole book.
    "SDHY.L", "SDHY.LSEETF", "STHY.L", "STHY.LSEETF", "IEML.L", "IEML.LSEETF",
    # Subordinated bank capital (archive/carry_sota_at1.yaml): Invesco AT1 EUR-hedged Dist —
    # crash-rent income the defensive axis cannot dilute ([[the-skew-is-the-product]]).
    # XBRU is the MIC the gateway mints for IB primary exchange EBS.
    "XAT1.XBRU", "XAT1.EBS", "XAT1.IBIS2",
})

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter_eu.credit_carry",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["carry_window"],
    "output_names": ["carry_score"],
    "defaults": {"carry_window": 252},
}


# %% parameter space
def param_space():
    """Return VBT-native trailing windows for the credit-carry richness baseline.

    The carry is the spread relative to its own trailing mean over ``carry_window`` days;
    a longer window defines a slower "normal" baseline (6m / 1y / 2y).
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "carry_window": vbt.Param([126, 252, 504]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars for credit carry: the trailing-mean window (NaN before a full window)."""
    return int(params["carry_window"])


# %% helpers
def _fred_series(series_id):
    """Full-history daily FRED series as a float Series, pulled once and cached.

    Mirrors convexity's lazy-benchmark pull: a signal-only feed sourced on demand from
    outside the traded panel, rather than required in the config universe.
    """

    if series_id not in _FRED_CACHE:
        import requests

        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {"series_id": series_id, "api_key": _FRED_KEY, "file_type": "json"}
        obs = requests.get(url, params=params, timeout=30).json()["observations"]
        s = pd.Series({
            pd.Timestamp(o["date"]): float(o["value"])
            for o in obs if o["value"] not in (".", "")
        })
        _FRED_CACHE[series_id] = s.sort_index()
    return _FRED_CACHE[series_id]


def _credit_sign(col):
    """Per-column credit polarity: +1 hold LONG. Unknown ticker raises (fail-loud).

    Columns arrive as plain tickers or as Nautilus ``InstrumentId`` objects (whose str
    form is the venue-qualified id); both are matched on their string form.
    """

    if str(col) in _CREDIT_LONG:
        return 1.0
    raise ValueError(
        f"demeter_eu.credit_carry: {col!r} is not a known credit vehicle. Add it to "
        f"_CREDIT_LONG so it is explicitly held long to harvest its spread."
    )


def _credit_carry(close, window):
    """Signed credit-carry score per column from the Baa-Treasury spread richness.

    carry = (Baa - 10y UST) / its trailing ``window``-day mean, clipped >= 0 (lean in when
    the credit spread is rich, never short credit). The macro spread is broadcast to every
    credit column times its polarity sign (+1 long); warmup rows (before a full window) are
    NaN so the strategy's dead-zone excludes them.
    """

    spread = (_fred_series(_BAA) - _fred_series(_UST10)).dropna()
    # Align the (tz-naive, date-keyed) FRED feed to close.index by CALENDAR DATE, regardless
    # of whether close.index is tz-aware (the pipeline delivers UTC-stamped daily bars). Match
    # on normalized naive dates, then restore the original index for downstream alignment.
    dates = pd.DatetimeIndex(close.index)
    key = (dates.tz_localize(None) if dates.tz is not None else dates).normalize()
    spread = pd.Series(spread.reindex(key).ffill().to_numpy(), index=close.index)
    richness = (spread / spread.rolling(window).mean()).clip(lower=0.0)

    signs = np.array([_credit_sign(col) for col in close.columns])
    score_2d = richness.to_numpy()[:, None] * signs[None, :]
    score_2d[:window] = np.where(signs == 0.0, 0.0, np.nan)  # NaN warmup on executables
    return pd.DataFrame(score_2d, index=close.index, columns=close.columns)


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Demeter-EU credit carry for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    windows = param_lists["carry_window"]

    result = np.full((T, n_candidates * n_symbols), np.nan)
    for w in set(windows):
        candidate_indices = [i for i in range(n_candidates) if windows[i] == w]
        arr = _credit_carry(close, int(w)).values
        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"carry_score": result}
