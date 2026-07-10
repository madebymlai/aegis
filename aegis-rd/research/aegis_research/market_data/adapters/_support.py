from __future__ import annotations

from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration import DataConfig
from research.aegis_research.market_data import native_metadata as _native_metadata


def local_provider_metadata(native_data: Any, *, source: str) -> dict[str, Any]:
    """Project the metadata sidecar for a local source.

    Local sources (synthetic, csv) carry no provider mappings, so only the
    allowlisted native fields plus ``source``/``class`` are projected.
    """
    return _native_metadata.native_data_metadata(native_data, source=source)


def index_evidence(index: pd.Index, *, source: str) -> dict[str, Any]:
    return {
        "source": source,
        "raw_rows": len(index),
        "raw_index_start": str(index[0]) if len(index) else None,
        "raw_index_end": str(index[-1]) if len(index) else None,
        "raw_index_has_duplicates": bool(index.has_duplicates),
        "raw_index_monotonic_increasing": bool(index.is_monotonic_increasing),
        "raw_index_timezone": str(index.tz)
        if isinstance(index, pd.DatetimeIndex) and index.tz
        else None,
    }


def native_from_array_dict(arrays: dict[str, pd.DataFrame], config: DataConfig) -> Any:
    # Fixed pull policy: the catalog serves clean UTC frames, so only the
    # calendar policy (``missing_index``) is authored; the remaining VBT pull
    # options are pinned to their strict values (v4 reshape — the config knobs
    # for them are retired).
    return vbt.Data.from_data(
        vbt.feature_dict(arrays),
        columns_are_symbols=True,
        missing_index=config.missing_index,
        missing_columns="raise",
        tz_localize=None,
        tz_convert=None,
    )


def native_index(native_data: Any) -> pd.Index:
    try:
        return native_data.index
    except AttributeError:
        pass
    if isinstance(native_data, pd.DataFrame):
        return native_data.index
    if callable(getattr(native_data, "get", None)):
        values = native_data.get()
        if isinstance(values, (pd.Series, pd.DataFrame)):
            return values.index
    return pd.Index([])
