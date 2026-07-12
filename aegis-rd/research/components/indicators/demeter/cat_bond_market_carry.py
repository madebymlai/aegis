# %% component overview
# Market-level catastrophe-bond carry refreshed from Artemis into a content-addressed cache.
# A validated runtime cache is the offline fallback; lag and staleness remain explicit.

from pathlib import Path

import numpy as np
import pandas as pd

from research.aegis_research.external_data.artemis import ArtemisMarketYieldSource

COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter.cat_bond_market_carry",
    "version": "2.0.0",
    "input_names": ["Close"],
    "param_names": [
        "cache_dir",
        "publication_lag_days",
        "max_age_days",
        "richness_window",
        "fund_fee",
    ],
    "output_names": ["cat_bond_net_carry", "cat_bond_risk_multiple", "cat_bond_richness", "cat_bond_data_fresh"],
    "defaults": {
        "cache_dir": "research/data/cache/artemis/cat-bond-market-yield",
        "publication_lag_days": 7,
        "max_age_days": 21,
        "richness_window": 104,
        "fund_fee": 1.28,
    },
}


def lookback(**params):
    return 0


def _snapshot_path(value):
    path = Path(value)
    return path if path.is_absolute() else Path(__file__).resolve().parents[4] / path


def _aligned_signal(index, snapshot, lag_days, max_age_days, richness_window, fund_fee):
    frame = snapshot.frame.copy()
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
    """Refresh and align Artemis market carry to each candidate and traded symbol."""
    close = data.array("Close")
    n_symbols = len(close.columns)
    outputs = {name: np.full((len(close), n_candidates * n_symbols), np.nan) for name in COMPONENT_MANIFEST["output_names"]}
    snapshots = {}
    for candidate in range(n_candidates):
        key = str(_snapshot_path(param_lists["cache_dir"][candidate]))
        if key not in snapshots:
            snapshots[key] = ArtemisMarketYieldSource(Path(key)).refresh_and_load()
        signal = _aligned_signal(
            close.index,
            snapshots[key],
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
