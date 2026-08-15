"""The IBKR venue pin — the one symbology decision both IBKR paths share."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def mic_instrument_provider_config(load_ids: Iterable[str] | None = None) -> Any:
    """The IBKR instrument-provider config with the venue pin (r8b.9 Slice F(b)).

    ``convert_exchange_to_mic_venue=True`` qualifies IBKR exchanges to their MIC venues
    (``CME → XCME``, ``NYBOT → IFUS``; gateway probe ``resolved-r8b-9-probe6-ice-venue``),
    so every IBKR contract — a static native, a live subscription, or a discovered
    futures-chain leg — resolves to ONE deterministic venue.  The synthetic continuous-root
    id ``{root}.{venue}`` then inherits it and aegis-data's single-venue chain build holds.
    Shared by the live wiring (:func:`live_clients`) and the historic seed/backfill so
    both sides mint byte-identical ids.  Lazily imports the ibapi-backed config, preserving
    the package's lazy-``ibapi`` boundary.
    """
    from nautilus_trader.adapters.interactive_brokers.config import (
        InteractiveBrokersInstrumentProviderConfig,
    )

    kwargs: dict[str, Any] = {"convert_exchange_to_mic_venue": True}
    if load_ids is not None:
        kwargs["load_ids"] = frozenset(load_ids)
    return InteractiveBrokersInstrumentProviderConfig(**kwargs)
