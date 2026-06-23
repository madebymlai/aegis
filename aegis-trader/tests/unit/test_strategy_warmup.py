from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import DataContract
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.strategy import RebalanceStrategy


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


class _WarmupHarness:
    def __init__(self) -> None:
        self.config = SimpleNamespace(warmup_cache_on_start=True)
        self.clock = _Clock()
        self._feeds: dict[object, object] = {}  # no continuous feeds in this native-only book
        self.calls: list[tuple[tuple, dict]] = []
        self._sleeve_to_contract = {
            SleeveName("trend"): DataContract(
                instrument_ids=(InstrumentId.from_str("VUSA.XLON"),),
                required_arrays=("Close",),
                base_currency="EUR",
                timeframe="1D",
                lookback_bars=20,
            )
        }

    def request_bars(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))

    # Bound from the real strategy so the warmup runs against the production
    # instrument-id resolution, not a re-implementation.
    _registered_instrument_ids = RebalanceStrategy._registered_instrument_ids


def test_startup_warmup_requests_native_catalog_bars() -> None:
    """The startup warmup issues the plain native ``request_bars(update_catalog=
    True)`` (catalog-served + IBKR-tail, ADR-0006) over the lookback window —
    LAST-EXTERNAL, no bespoke provider loop."""
    harness = _WarmupHarness()
    warm = RebalanceStrategy._warm_startup_cache.__get__(harness, _WarmupHarness)

    warm("1D")

    args, kwargs = harness.calls[0]
    assert str(args[0]) == "VUSA.XLON-1-DAY-LAST-EXTERNAL"
    assert kwargs["update_catalog"] is True
    assert kwargs["end"] == datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    assert kwargs["start"] == datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
