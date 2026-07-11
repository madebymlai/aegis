# %% component overview
# Demeter-EU credit carry with one packaged put-write satellite. Credit instruments retain
# the Baa-minus-10y-Treasury richness score. E50PW is explicitly admitted but unscored:
# holding the packaged cash-plus-short-put index is the carry expression, so the strategy
# sizes it through putwrite_weight rather than applying a credit spread signal to it.
#
# This is deliberately a standalone variant rather than a shared helper imported by the
# locked champion. Component sources are bundled independently for execution provenance;
# changing the incumbent would break byte-stable lock replay. Duplication isolates this
# challenger and keeps every admitted instrument role fail-loud in its own bundle.

# %% imports
import numpy as np
import pandas as pd

_FRED_KEY = "6b0bb1a2e9343b395c582035dda1e470"
_BAA = "DBAA"
_UST10 = "DGS10"
_FRED_CACHE: dict[str, pd.Series] = {}

_CREDIT_LONG = frozenset(
    {
        "HYG",
        "JNK",
        "HYLD",
        "LQD",
        "EMB",
        "EMHY",
        "IHYU.L",
        "LQDE.L",
        "IEMB.L",
        "SEMB.L",
        "LQDH.L",
        "IHYU.LSEETF",
        "LQDE.LSEETF",
        "IEMB.LSEETF",
        "SEMB.LSEETF",
        "LQDH.LSEETF",
        "SDHY.L",
        "SDHY.LSEETF",
        "STHY.L",
        "STHY.LSEETF",
        "IEML.L",
        "IEML.LSEETF",
        "XAT1.XBRU",
        "XAT1.EBS",
        "XAT1.IBIS2",
    }
)
_PUTWRITE_CARRY = frozenset({"E50PW.EBS", "E50PW.IBIS", "E50PW.XETR"})

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter_eu.credit_carry_putwrite",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["carry_window"],
    "output_names": ["carry_score"],
    "defaults": {"carry_window": 252},
}


# %% parameter space
def param_space():
    """Return candidate windows for the credit-richness signal."""

    from vectorbtpro import vbt

    return {"carry_window": vbt.Param([126, 252, 504])}


# %% lookback
def lookback(**params):
    return int(params["carry_window"])


# %% helpers
def _fred_series(series_id):
    if series_id not in _FRED_CACHE:
        import requests

        response = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": series_id, "api_key": _FRED_KEY, "file_type": "json"},
            timeout=30,
        )
        response.raise_for_status()
        observations = response.json()["observations"]
        _FRED_CACHE[series_id] = pd.Series(
            {
                pd.Timestamp(item["date"]): float(item["value"])
                for item in observations
                if item["value"] not in (".", "")
            }
        ).sort_index()
    return _FRED_CACHE[series_id]


def _credit_sign(column):
    name = str(column)
    if name in _CREDIT_LONG:
        return 1.0
    if name in _PUTWRITE_CARRY:
        return np.nan
    raise ValueError(
        f"demeter_eu.credit_carry_putwrite: {name!r} is neither known credit nor "
        "the packaged put-write leg"
    )


def _credit_carry(close, window):
    spread = (_fred_series(_BAA) - _fred_series(_UST10)).dropna()
    dates = pd.DatetimeIndex(close.index)
    key = (dates.tz_localize(None) if dates.tz is not None else dates).normalize()
    spread = pd.Series(spread.reindex(key).ffill().to_numpy(), index=close.index)
    richness = (spread / spread.rolling(window).mean()).clip(lower=0.0)
    signs = np.array([_credit_sign(column) for column in close.columns])
    scores = richness.to_numpy()[:, None] * signs[None, :]
    scores[:window] = np.nan
    return scores


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Compute credit richness while leaving the packaged put-write leg unscored."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    result = np.full((len(close), n_candidates * n_symbols), np.nan)
    windows = param_lists["carry_window"]
    for window in set(windows):
        scores = _credit_carry(close, int(window))
        for candidate in (i for i in range(n_candidates) if windows[i] == window):
            result[:, candidate * n_symbols : (candidate + 1) * n_symbols] = scores
    return {"carry_score": result}
