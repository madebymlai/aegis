"""Authoritative classification of declared market-data Array names."""

from typing import Final


OHLCV_ARRAY_NAMES: Final = ("Open", "High", "Low", "Close", "Volume")


def is_bar_derived_array(array_name: str) -> bool:
    """Return whether ``array_name`` is materialized from a Nautilus bar."""
    return array_name in OHLCV_ARRAY_NAMES
