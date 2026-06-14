from __future__ import annotations

from types import MappingProxyType
from typing import Any

from vectorbtpro import vbt

LOCAL_DATA_SOURCES = {"synthetic", "csv"}
EXCLUDED_VBT_DATA_CLASSES = {"Data", "SyntheticData", "CSVData"}


def data_sources() -> set[str]:
    return LOCAL_DATA_SOURCES | remote_data_sources()


def remote_data_sources() -> set[str]:
    return set(vbt_data_source_classes())


def vbt_data_source_classes() -> MappingProxyType[str, Any]:
    return MappingProxyType(
        {
            name.removesuffix("Data").lower(): data_class
            for name, data_class in sorted(_iter_vbt_data_classes())
        }
    )


def _iter_vbt_data_classes():
    for name in dir(vbt):
        if name in EXCLUDED_VBT_DATA_CLASSES or not name.endswith("Data"):
            continue
        data_class = getattr(vbt, name)
        if callable(getattr(data_class, "pull", None)):
            yield name, data_class
