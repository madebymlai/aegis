# %% component overview
# Market-level catastrophe-bond carry from a pinned Artemis snapshot. No network access
# occurs during a Run. Observations are delayed before use and stale data is explicit.

from pathlib import Path

import numpy as np
import pandas as pd

from research.aegis_research.external_data.artemis import load_snapshot

COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter.cat_bond_market_carry",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["snapshot", "publication_lag_days", "max_age_days", "richness_window", "fund_fee"],
    "output_names": ["cat_bond_net_carry", "cat_bond_risk_multiple", "cat_bond_richness", "cat_bond_data_fresh"],
    "defaults": {"publication_lag_days": 7, "max_age_days": 21, "richness_window": 104, "fund_fee": 1.28},
}


def lookback(**params):
    return 0


def _snapshot_path(value):
    path = Path(value)
    return path if path.is_absolute() else Path(__file__).resolve().parents[4] / path


def _aligned_signal(index, snapshot, lag_days, max_age_days, richness_window, fund_fee):
    frame = load_snapshot(_snapshot_path(snapshot)).frame.copy()
    spread = frame["Insurance Risk Spread"]
    expected_loss = frame["Expected Loss"]
    frame["net"] = frame["Collateral Yield"] + spread - expected_loss - fund_fee
    frame["multiple"] = spread / expected_loss.replace(0.0, np.nan)
    premium = spread - expected_loss
    frame["richness"] = premium.rolling(
        richness_window, min_periods=richness_window
    ).rank(pct=True)
    frame.index = frame.index + pd.Timedelta(days=lag_days)

    dates = pd.DatetimeIndex(index)
    keys = (dates.tz_localize(None) if dates.tz is not None else dates).normalize()
    aligned = frame.reindex(keys, method="ffill")
    latest_source = frame.index.to_series().reindex(keys, method="ffill").to_numpy()
    age = keys.to_numpy() - latest_source
    aligned["fresh"] = (age <= np.timedelta64(max_age_days, "D")).astype(float)
    aligned.index = index
    return aligned


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Align pinned Artemis carry observations to each candidate and traded symbol."""
    close = data.array("Close")
    n_symbols = len(close.columns)
    outputs = {name: np.full((len(close), n_candidates * n_symbols), np.nan) for name in COMPONENT_MANIFEST["output_names"]}
    for candidate in range(n_candidates):
        signal = _aligned_signal(
            close.index,
            param_lists["snapshot"][candidate],
            int(param_lists["publication_lag_days"][candidate]),
            int(param_lists["max_age_days"][candidate]),
            int(param_lists["richness_window"][candidate]),
            float(param_lists["fund_fee"][candidate]),
        )
        start = candidate * n_symbols
        for output, column in {
            "cat_bond_net_carry": "net",
            "cat_bond_risk_multiple": "multiple",
            "cat_bond_richness": "richness",
            "cat_bond_data_fresh": "fresh",
        }.items():
            outputs[output][:, start : start + n_symbols] = signal[column].to_numpy()[:, None]
    return outputs
