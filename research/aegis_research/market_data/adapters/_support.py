from __future__ import annotations

from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration.schema import DataConfig
from research.aegis_research.market_data import safety as _safety


def safe_provider_metadata(native_data: Any, *, source: str) -> dict[str, Any]:
    """Project safe, public-shareable provider metadata for a local source.

    Local sources (synthetic, csv) never carry provider credentials, so no
    allowlist projection of ``fetch_kwargs``/``returned_kwargs`` is applied —
    only the safe native fields plus ``source``/``class``.
    """
    return _safety.safe_native_data_metadata(native_data, source=source)


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


def native_from_feature_data(feature_data: dict[str, pd.DataFrame], config: DataConfig) -> Any:
    return vbt.Data.from_data(
        vbt.feature_dict(feature_data),
        columns_are_symbols=True,
        missing_index=config.missing_index,
        missing_columns=config.missing_columns,
        tz_localize=config.tz_localize,
        tz_convert=config.tz_convert,
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
