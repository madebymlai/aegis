# %% component overview
# Vanguard 3-regime canary rotation strategy with turnover gate.
# Regime detection via SPY/TLT canary pair determines offensive/defensive budget split.
# Offensive sleeve: top-N by momentum, inverse-vol sized.
# Defensive sleeve: top-K by momentum, equal-weighted.

# %% imports
import numpy as np
from nautilus_trader.model.identifiers import InstrumentId
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "tests.momentum_rotator",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["top_n", "top_k_defensive", "tau"],
    "output_name": "target_weights",
    "consumes_outputs": ["momentum_score", "realized_vol"],
    "defaults": {
        "top_n": 3,
        "top_k_defensive": 1,
        "tau": 0.08,
    },
    "owns_portfolio": False,
}

# %% instrument sleeves
def _id(value):
    return InstrumentId.from_str(value)


_CANARY_INSTRUMENT_IDS = (_id("SPY.XNAS"), _id("TLT.XNAS"))
_OFFENSIVE_INSTRUMENT_IDS = (
    _id("IWM.XNAS"),
    _id("EEM.XNAS"),
    _id("GLD.XNAS"),
    _id("DBC.XNAS"),
    _id("VNQ.XNAS"),
    _id("XLE.XNAS"),
    _id("XLU.XNAS"),
)
_DEFENSIVE_INSTRUMENT_IDS = (_id("TLT.XNAS"), _id("GLD.XNAS"), _id("UUP.XNAS"))

# Regime codes
_RISK_ON = 2
_MIXED = 1
_RISK_OFF = 0


# %% parameter space
def param_space():
    """Return VBT-native momentum rotator params for optimization."""

    return {
        "top_n": vbt.Param([2, 3, 4]),
        "top_k_defensive": vbt.Param([1, 2]),
        "tau": vbt.Param([0.05, 0.08, 0.10, 0.15, 0.20]),
    }


# %% helpers
def _find_indices(columns, instrument_ids):
    """Return array of column indices for the given native instrument IDs."""

    col_list = list(columns)
    indices = []
    for current_id in instrument_ids:
        indices.append(col_list.index(current_id))
    return np.array(indices, dtype=int)


def _detect_regime(canary_momentum):
    """Classify regime from canary momentum signs.

    Parameters
    ----------
    canary_momentum : ndarray of shape (n_canary,)
        Momentum scores for canary assets at a single bar.

    Returns
    -------
    int
        _RISK_ON (2), _MIXED (1), or _RISK_OFF (0).
    """

    n_positive = np.sum(canary_momentum > 0)
    n_canary = len(canary_momentum)
    if n_positive == n_canary:
        return _RISK_ON
    if n_positive == 0:
        return _RISK_OFF
    return _MIXED


def _offensive_weights(momentum_off, vol_off, top_n):
    """Compute inverse-vol weighted allocation for offensive sleeve.

    Parameters
    ----------
    momentum_off : ndarray of shape (n_offensive,)
    vol_off : ndarray of shape (n_offensive,)
    top_n : int

    Returns
    -------
    ndarray of shape (n_offensive,)
        Weights summing to 1.0 (or less if gated to cash).
    """

    n = len(momentum_off)
    weights = np.zeros(n)

    # Rank by momentum descending; pick top_n
    order = np.argsort(-momentum_off, kind="stable")
    selected = order[:top_n]

    # Gate: negative momentum -> cash (skip)
    survivors = selected[momentum_off[selected] > 0]
    if len(survivors) == 0:
        return weights

    inv_vol = np.where(vol_off[survivors] > 0, 1.0 / vol_off[survivors], 0.0)
    total = inv_vol.sum()
    if total > 0:
        weights[survivors] = inv_vol / total
    return weights


def _defensive_weights(momentum_def, top_k):
    """Compute equal-weighted allocation for defensive sleeve.

    Parameters
    ----------
    momentum_def : ndarray of shape (n_defensive,)
    top_k : int

    Returns
    -------
    ndarray of shape (n_defensive,)
        Weights summing to 1.0 (or 0 if gated to cash).
    """

    n = len(momentum_def)
    weights = np.zeros(n)

    order = np.argsort(-momentum_def, kind="stable")
    selected = order[:top_k]

    # Gate: if best has negative momentum, go to cash
    if momentum_def[selected[0]] <= 0:
        return weights

    survivors = selected[momentum_def[selected] > 0]
    if len(survivors) == 0:
        return weights

    weights[survivors] = 1.0 / len(survivors)
    return weights


def _compute_target_weights(
    mom_row, vol_row, regime,
    offensive_idx, defensive_idx,
    top_n, top_k_defensive,
):
    """Compute target weights for a single bar given the regime."""

    n_symbols = len(mom_row)
    weights = np.zeros(n_symbols)

    if regime == _RISK_ON:
        off_budget, def_budget = 1.0, 0.0
    elif regime == _RISK_OFF:
        off_budget, def_budget = 0.0, 1.0
    else:
        off_budget, def_budget = 0.5, 0.5

    if off_budget > 0:
        off_mom = mom_row[offensive_idx]
        off_vol = vol_row[offensive_idx]
        if not np.any(np.isnan(off_mom)):
            off_w = _offensive_weights(off_mom, off_vol, top_n)
            weights[offensive_idx] += off_w * off_budget

    if def_budget > 0:
        def_mom = mom_row[defensive_idx]
        if not np.any(np.isnan(def_mom)):
            def_w = _defensive_weights(def_mom, top_k_defensive)
            weights[defensive_idx] += def_w * def_budget

    return weights


# %% lookback
def lookback(**params):
    """Strategy has no additional warmup beyond what its indicators need.

    The bundle will compute lookback_bars as the max over all components;
    for the strategy itself the warmup is 0 (the strategy's indicators
    already declare their own lookback).
    """
    return 0


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized regime rotation for all candidates in a single call."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)
    columns = close.columns

    momentum_arr = inputs.indicators["momentum_score"]
    vol_arr = inputs.indicators["realized_vol"]

    top_ns = param_lists["top_n"]
    top_ks = param_lists["top_k_defensive"]
    taus = param_lists["tau"]

    mom_3d = momentum_arr.reshape(T, n_candidates, n_symbols)
    vol_3d = vol_arr.reshape(T, n_candidates, n_symbols)

    canary_idx = _find_indices(columns, _CANARY_INSTRUMENT_IDS)
    offensive_idx = _find_indices(columns, _OFFENSIVE_INSTRUMENT_IDS)
    defensive_idx = _find_indices(columns, _DEFENSIVE_INSTRUMENT_IDS)

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)

    for ci in range(n_candidates):
        tn = int(top_ns[ci])
        tk = int(top_ks[ci])
        tau_val = float(taus[ci])

        mom_2d = mom_3d[:, ci, :]
        vol_2d = vol_3d[:, ci, :]

        prev_regime = None
        last_weights = np.zeros(n_symbols)

        for t in range(T):
            canary_mom = mom_2d[t, canary_idx]
            if np.any(np.isnan(canary_mom)):
                continue

            regime = _detect_regime(canary_mom)
            regime_changed = prev_regime is not None and regime != prev_regime

            weights = _compute_target_weights(
                mom_2d[t], vol_2d[t], regime,
                offensive_idx, defensive_idx,
                tn, tk,
            )

            first_bar = prev_regime is None
            turnover = np.abs(weights - last_weights).sum()
            if not first_bar and not regime_changed and turnover < tau_val:
                prev_regime = regime
                continue

            result_3d[t, ci, :] = weights
            last_weights = weights
            prev_regime = regime

    return result_3d.reshape(T, n_candidates * n_symbols)
