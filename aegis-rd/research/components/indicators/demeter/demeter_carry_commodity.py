# %% component overview
# Demeter-EU credit carry, COMMODITY-TOLERANT variant (aegis-rd-bkom) — identical to
# demeter_eu.credit_carry except it admits a market-neutral commodity-carry breadth leg
# (UBS CMCI Commodity Carry SF UCITS ETF, UEQC) as a NON-CREDIT column: the leg is a
# packaged carry play held as a fixed breadth share, not scored off the credit spread, so
# it emits a NaN carry_score and the strategy's spread-richness lean (a credit-only mean)
# excludes it by construction.
#
# Why a variant rather than an edit to demeter_eu.credit_carry: the champion indicator is
# fail-loud on any non-credit ticker (a typo must never silently weight a non-credit name),
# and it feeds a LOCKED champion whose replay must stay byte-stable. This variant keeps the
# same fail-loud guard for genuinely unknown tickers; it only adds an explicit commodity
# set whose columns are scored NaN (excluded, never guessed).
#
# SIGNAL is unchanged for the credit legs: the US credit-risk carry, the Baa-minus-10y-UST
# spread richness (FRED DBAA - DGS10), pulled inline and broadcast to every credit column
# times its polarity sign (+1 long). The commodity leg carries no credit spread, so its
# score is NaN (the strategy leans EXPOSURE on the credit richness only).

# %% imports
import numpy as np
import pandas as pd

# FRED credit-carry feed (signal-only, pulled inline; never a traded column).
_FRED_KEY = "6b0bb1a2e9343b395c582035dda1e470"  # personal-use key; configs are gitignored
_BAA = "DBAA"     # Moody's Seasoned Baa Corporate Bond Yield (daily, %), full history
_UST10 = "DGS10"  # 10y Treasury constant maturity (daily, %), full history
_FRED_CACHE: dict[str, pd.Series] = {}

# Credit vehicle polarity: every credit instrument is held LONG (+1) to harvest its spread.
# A column not listed here and not in _COMMODITY_CARRY raises in _credit_sign (fail-loud).
_CREDIT_LONG = frozenset({
    # US-listed (research/backtest, longest history)
    "HYG", "JNK", "HYLD", "LQD", "EMB", "EMHY",
    # EU-retail UCITS (London, USD-denominated)
    "IHYU.L", "LQDE.L", "IEMB.L", "SEMB.L",
    "LQDH.L",
    "IHYU.LSEETF", "LQDE.LSEETF", "IEMB.LSEETF", "SEMB.LSEETF", "LQDH.LSEETF",
    "SDHY.L", "SDHY.LSEETF", "STHY.L", "STHY.LSEETF", "IEML.L", "IEML.LSEETF",
    "XAT1.XBRU", "XAT1.EBS", "XAT1.IBIS2",
})

# Market-neutral commodity-carry breadth leg (aegis-rd-bkom): the UBS CMCI Commodity Carry
# SF UCITS ETF (ISIN IE00BKFB6L02, EUR-native, accumulating). Held as a fixed breadth share
# by the strategy, NOT scored off the credit spread, so its carry_score is NaN. Both id
# spellings the pipeline may deliver: the raw IB primary-exchange line and its MIC canon.
_COMMODITY_CARRY = frozenset({"UEQC.IBIS", "UEQC.XETR"})

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter_eu.credit_carry_commodity",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["carry_window"],
    "output_names": ["carry_score"],
    "defaults": {"carry_window": 252},
}


# %% parameter space
def param_space():
    """Return VBT-native trailing windows for the credit-carry richness baseline."""

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
    """Full-history daily FRED series as a float Series, pulled once and cached."""

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
    """Per-column polarity: +1 hold LONG (credit), NaN unscored (commodity breadth leg).

    An unknown ticker raises (fail-loud): a typo must never silently weight a non-credit
    instrument, and a scored-but-unknown name must never pollute the credit richness mean.
    """

    name = str(col)
    if name in _CREDIT_LONG:
        return 1.0
    if name in _COMMODITY_CARRY:
        return np.nan  # a fixed-share breadth leg; not sized off the credit spread
    raise ValueError(
        f"demeter_eu.credit_carry_commodity: {col!r} is neither a known credit vehicle "
        f"(_CREDIT_LONG) nor the commodity breadth leg (_COMMODITY_CARRY). Add it so its "
        f"role is explicit."
    )


def _credit_carry(close, window):
    """Signed credit-carry score per column from the Baa-Treasury spread richness.

    carry = (Baa - 10y UST) / its trailing ``window``-day mean, clipped >= 0. Broadcast to
    every credit column times its polarity sign (+1 long); the commodity leg's NaN sign
    makes its column NaN (excluded from the strategy's richness mean). Warmup rows are NaN.
    """

    spread = (_fred_series(_BAA) - _fred_series(_UST10)).dropna()
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
    """Vectorized Demeter-EU credit carry (commodity-tolerant) for all candidates."""

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
