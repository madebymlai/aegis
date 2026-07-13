# %% component overview
# Point-in-time net YTW and modified duration for Demeter's four UCITS credit buckets.
# Exact UCITS weights are joined by ISIN to first-party iShares security analytics; an
# observation is causal only from the session after its holdings date.

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from research.aegis_research.external_data.ishares_credit import (
    IsharesCreditDataError,
    IsharesCreditSource,
)

COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter.credit_bucket_yield",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["cache_dir", "min_coverage", "max_age_days"],
    "output_names": [
        "credit_net_ytw",
        "credit_modified_duration",
        "credit_data_coverage",
        "credit_data_fresh",
        "credit_rebalance_due",
    ],
    "defaults": {
        "cache_dir": "research/data/cache/ishares/credit-buckets",
        "min_coverage": 0.90,
        "max_age_days": 45,
    },
}

_BUCKETS = frozenset(
    {"SDIG.LSEETF", "LQDE.LSEETF", "SDHY.LSEETF", "IHYU.LSEETF"}
)


def lookback(**params):
    return 0


def _cache_path(value):
    path = Path(value)
    return path if path.is_absolute() else Path(__file__).resolve().parents[4] / path


def _calendar_dates(index):
    dates = pd.DatetimeIndex(index)
    return (dates.tz_localize(None) if dates.tz is not None else dates).normalize()


def _monthly_rebalance(index):
    dates = _calendar_dates(index)
    months = dates.to_period("M")
    due = np.ones(len(dates), dtype=float)
    if len(due) > 1:
        due[1:] = (months[1:] != months[:-1]).astype(float)
    return due


def _align_bucket(index, rows, min_coverage, max_age_days):
    rows = rows.sort_values("available_at").set_index("available_at")
    keys = _calendar_dates(index)
    aligned = rows.reindex(keys, method="ffill")
    source_dates = pd.Series(rows.index, index=rows.index).reindex(keys, method="ffill")
    age = keys.to_numpy() - source_dates.to_numpy()
    fresh = (
        aligned["coverage"].ge(min_coverage)
        & (age <= np.timedelta64(max_age_days, "D"))
    )
    aligned.loc[~fresh, ["net_ytw", "modified_duration"]] = np.nan
    aligned["fresh"] = fresh.astype(float)
    aligned.index = index
    return aligned


def _load_panel(cache_dir, start, end):
    try:
        return IsharesCreditSource(cache_dir).load_window(start, end)
    except (IsharesCreditDataError, requests.RequestException, OSError) as error:
        warnings.warn(
            f"iShares credit data unavailable; using static fallback: {error}",
            stacklevel=2,
        )
        return pd.DataFrame(
            columns=[
                "as_of_date",
                "instrument_id",
                "available_at",
                "net_ytw",
                "modified_duration",
                "coverage",
            ]
        ).set_index(["as_of_date", "instrument_id"])


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Return causal monthly bucket observations for every strategy candidate."""
    close = data.array("Close")
    columns = [str(column) for column in close.columns]
    unknown = sorted(set(columns) - _BUCKETS)
    if unknown:
        raise ValueError(f"demeter.credit_bucket_yield: unsupported instruments: {unknown}")
    n_symbols = len(columns)
    outputs = {
        name: np.full((len(close), n_candidates * n_symbols), np.nan)
        for name in COMPONENT_MANIFEST["output_names"]
    }
    due = _monthly_rebalance(close.index)
    panels = {}
    for candidate in range(n_candidates):
        cache_dir = _cache_path(param_lists["cache_dir"][candidate])
        if cache_dir not in panels:
            panels[cache_dir] = _load_panel(
                cache_dir,
                pd.Timestamp(close.index[0]) - pd.Timedelta(days=45),
                pd.Timestamp(close.index[-1]),
            )
        panel = panels[cache_dir].reset_index()
        start = candidate * n_symbols
        for offset, instrument_id in enumerate(columns):
            rows = panel.loc[panel["instrument_id"] == instrument_id]
            if rows.empty:
                outputs["credit_data_fresh"][:, start + offset] = 0.0
                outputs["credit_rebalance_due"][:, start + offset] = due
                continue
            aligned = _align_bucket(
                close.index,
                rows,
                float(param_lists["min_coverage"][candidate]),
                int(param_lists["max_age_days"][candidate]),
            )
            for output, field in {
                "credit_net_ytw": "net_ytw",
                "credit_modified_duration": "modified_duration",
                "credit_data_coverage": "coverage",
                "credit_data_fresh": "fresh",
            }.items():
                outputs[output][:, start + offset] = aligned[field].to_numpy()
            outputs["credit_rebalance_due"][:, start + offset] = due
    return outputs
