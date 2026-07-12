# %% component overview
# CATB-specific carry from whole-portfolio HANetf/King Ridge manager statistics.
# Reports become usable on publication, never on their earlier portfolio as-of date.

from pathlib import Path

import numpy as np
import pandas as pd

from research.aegis_research.external_data.catb_manager_report import current_and_cached_reports

COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter.cat_bond_portfolio_carry",
    "version": "3.0.0",
    "input_names": ["Close"],
    "param_names": [
        "cache_dir",
        "history_dir",
        "max_age_days",
    ],
    "output_names": [
        "cat_bond_loss_adjusted_yield",
        "cat_bond_insurance_spread",
        "cat_bond_expected_loss",
        "cat_bond_risk_multiple",
        "cat_bond_weighted_maturity_years",
        "cat_bond_data_fresh",
    ],
    "defaults": {
        "cache_dir": "research/data/cache/hanetf/catb-reports",
        "history_dir": "research/data/hanetf/catb-reports",
        "max_age_days": 120,
    },
}


def lookback(**params):
    return 0


def _project_path(value):
    path = Path(value)
    return path if path.is_absolute() else Path(__file__).resolve().parents[4] / path


def _aligned_metrics(index, observations, max_age_days):
    if max_age_days < 0:
        raise ValueError("demeter.cat_bond_portfolio_carry: max_age_days must be non-negative")
    dates = pd.DatetimeIndex(index)
    keys = (dates.tz_localize(None) if dates.tz is not None else dates).normalize()
    rows = [
        {
            "available": (
                pd.Timestamp(metrics.available_at).tz_localize(None).normalize()
                + pd.Timedelta(days=1)
            ),
            "cat_bond_loss_adjusted_yield": metrics.loss_adjusted_yield,
            "cat_bond_insurance_spread": metrics.insurance_spread,
            "cat_bond_expected_loss": metrics.expected_loss,
            "cat_bond_risk_multiple": metrics.risk_multiple,
            "cat_bond_weighted_maturity_years": metrics.weighted_maturity_years,
        }
        for metrics in observations
    ]
    frame = pd.DataFrame(rows).drop_duplicates("available", keep="last").set_index("available")
    aligned = frame.reindex(keys, method="ffill")
    latest = frame.index.to_series().reindex(keys, method="ffill").to_numpy()
    age = keys.to_numpy() - latest
    usable = age <= np.timedelta64(max_age_days, "D")
    aligned.loc[~usable, :] = np.nan
    result = {name: aligned[name].to_numpy() for name in aligned.columns}
    result["cat_bond_data_fresh"] = usable.astype(float)
    return result


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Refresh CATB manager reports and align observations from publication time."""
    close = data.array("Close")
    n_symbols = len(close.columns)
    outputs = {
        name: np.full((len(close), n_candidates * n_symbols), np.nan)
        for name in COMPONENT_MANIFEST["output_names"]
    }
    observations_by_params = {}
    for candidate in range(n_candidates):
        key = (
            str(_project_path(param_lists["cache_dir"][candidate])),
            str(_project_path(param_lists["history_dir"][candidate])),
        )
        if key not in observations_by_params:
            observations_by_params[key] = current_and_cached_reports(
                Path(key[0]), history_dir=Path(key[1])
            )
        aligned = _aligned_metrics(
            close.index,
            observations_by_params[key],
            int(param_lists["max_age_days"][candidate]),
        )
        start = candidate * n_symbols
        for output, values in aligned.items():
            outputs[output][:, start : start + n_symbols] = values[:, None]
    return outputs
