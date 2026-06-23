"""Continuous-future wiring in the live RebalanceStrategy (r8b.9 Slice D, Model 2).

The strategy owns one ContinuousFeed per declared bare root: it reads the union of roots off the
sleeve contracts, materializes each feed off-cache at warmup, reads the continuous series through
NautilusMarketData, and drives the feed on each front-leg bar — re-basing the SleeveLedger in
lock-step when a roll shifts the basis (Slice L).  These goldens bind individual strategy methods
to a lightweight harness (the proven pattern in test_strategy_warmup.py), so the wiring is tested
without standing up a live node; the live subscribe/request paths are validated on the gateway.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity

from aegis_runtime import DataContract
from aegis_trader.data import raw_bar_type
from aegis_trader.domain.types import OrderIntent, OrderSide, OrderSource, SleeveName
from aegis_trader.trader.strategy import RebalanceStrategy


def _contract(
    *, futures: tuple[str, ...], instrument_ids: tuple[InstrumentId, ...] = ()
) -> DataContract:
    return DataContract(
        instrument_ids=instrument_ids,
        required_arrays=("Close",),
        base_currency="USD",
        timeframe="1D",
        lookback_bars=5,
        futures=futures,
    )


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


class _RootsHarness:
    def __init__(self, contracts: dict[SleeveName, DataContract]) -> None:
        self._sleeve_to_contract = contracts


def test_declared_roots_is_the_sorted_unique_union_across_sleeves() -> None:
    """D3: the strategy's continuous universe is the union of every sleeve contract's bare roots —
    sorted and de-duplicated, so two sleeves naming the same root share one feed."""
    harness = _RootsHarness(
        {
            SleeveName("trend"): _contract(futures=("ES", "KC")),
            SleeveName("carry"): _contract(futures=("ES", "CL")),
        }
    )
    declared = RebalanceStrategy._declared_roots.__get__(harness, _RootsHarness)

    assert declared() == ("CL", "ES", "KC")


def test_declared_roots_is_empty_without_futures() -> None:
    harness = _RootsHarness({SleeveName("equity"): _contract(futures=())})
    declared = RebalanceStrategy._declared_roots.__get__(harness, _RootsHarness)

    assert declared() == ()


# ── D4: on_bar drives the feed and re-bases the ledger / re-subscribes on a roll ──────────────


class _FakeFeed:
    def __init__(
        self,
        continuous_id: InstrumentId,
        front: InstrumentId,
        *,
        roll_to: InstrumentId | None = None,
        spread: float = 0.0,
    ) -> None:
        self.continuous_id = continuous_id
        self._front = front
        self._roll_to = roll_to
        self._spread = spread
        self.bars: list[object] = []

    def front_contract(self) -> InstrumentId:
        return self._front

    def on_bar(self, bar: object) -> None:
        self.bars.append(bar)
        if self._roll_to is not None:  # simulate the causal roll the real feed performs
            self._front = self._roll_to

    def last_roll_spread(self) -> float:
        return self._spread


class _FakeLedger:
    def __init__(self) -> None:
        self.rebased: list[dict[InstrumentId, float]] = []

    def rebase_closes(self, deltas: dict[InstrumentId, float]) -> None:
        self.rebased.append(dict(deltas))


class _DriveHarness:
    # The production property + sibling methods _drive_feed calls, bound to the harness (the
    # proven harness pattern: exercise the real code path, not a re-implementation).
    sleeve_ledger = RebalanceStrategy.sleeve_ledger
    _drive_feed = RebalanceStrategy._drive_feed
    _on_feed_roll = RebalanceStrategy._on_feed_roll
    _ensure_leg_subscribed = RebalanceStrategy._ensure_leg_subscribed
    _require_book_timeframe = RebalanceStrategy._require_book_timeframe

    def __init__(
        self,
        feed: _FakeFeed,
        ledger: _FakeLedger,
        book_timeframe: str = "1D",
        cache: _FakeCache | None = None,
    ) -> None:
        self._leg_to_feed = {feed.front_contract(): feed}  # routing keyed by the current front leg
        self._sleeve_ledger = ledger
        self._pipeline = None
        self._book_timeframe = book_timeframe
        self.cache = cache or _FakeCache()
        self._pending_leg_subscriptions: set[InstrumentId] = set()
        self.subscribed: list[object] = []
        self.unsubscribed: list[object] = []
        self.requested_instruments: list[InstrumentId] = []

    def subscribe_bars(self, bar_type: object) -> None:
        self.subscribed.append(bar_type)

    def unsubscribe_bars(self, bar_type: object) -> None:
        self.unsubscribed.append(bar_type)

    def request_instrument(self, instrument_id: InstrumentId) -> None:
        self.requested_instruments.append(instrument_id)


def _front_leg_bar(instrument_id: InstrumentId) -> object:
    return SimpleNamespace(bar_type=SimpleNamespace(instrument_id=instrument_id))


def test_on_bar_roll_rebases_the_ledger_and_rolls_to_the_new_front() -> None:
    """D4+G: when a front-leg bar advances the feed's causal front (a roll), the strategy re-bases
    the SleeveLedger by the roll spread (Slice L — keep the allocator basis-consistent) and rolls
    the execution target off the old front leg.  The new front is not preloaded (Slice G), so it is
    dynamically requested (subscription deferred to on_instrument), in lock-step with the data roll."""
    cont = InstrumentId.from_str("ES.XCME")
    old_front = InstrumentId.from_str("ESM4.XCME")
    new_front = InstrumentId.from_str("ESU4.XCME")
    feed = _FakeFeed(cont, old_front, roll_to=new_front, spread=67.0)
    ledger = _FakeLedger()
    harness = _DriveHarness(feed, ledger)  # new_front absent from the (empty) cache

    harness._drive_feed(_front_leg_bar(old_front))

    assert len(feed.bars) == 1  # the bar was folded into the feed
    assert ledger.rebased == [{cont: 67.0}]  # ledger re-based by the uniform roll spread
    assert str(harness.unsubscribed[0]) == str(raw_bar_type(old_front, "1D"))
    assert harness.requested_instruments == [new_front]  # new front loaded on demand
    assert new_front in harness._pending_leg_subscriptions
    assert harness._leg_to_feed == {new_front: feed}  # routing now follows the new front


def test_on_bar_without_a_roll_drives_the_feed_but_does_not_re_subscribe() -> None:
    front = InstrumentId.from_str("ESM4.XCME")
    feed = _FakeFeed(InstrumentId.from_str("ES.XCME"), front)  # no roll_to → front stays put
    ledger = _FakeLedger()
    harness = _DriveHarness(feed, ledger)

    harness._drive_feed(_front_leg_bar(front))

    assert len(feed.bars) == 1
    assert ledger.rebased == []
    assert harness.subscribed == [] and harness.unsubscribed == []
    assert harness._leg_to_feed == {front: feed}


def test_on_bar_ignores_a_bar_that_is_not_a_feeds_front_leg() -> None:
    """A native-instrument (or non-front-leg) bar must never reach a feed — otherwise the feed would
    recompute its causal front off a foreign bar's day and could spuriously roll."""
    front = InstrumentId.from_str("ESM4.XCME")
    feed = _FakeFeed(InstrumentId.from_str("ES.XCME"), front)
    harness = _DriveHarness(feed, _FakeLedger())

    harness._drive_feed(_front_leg_bar(InstrumentId.from_str("AAPL.NASDAQ")))

    assert feed.bars == []


# ── D5: warmup also requests each feed's front-leg raw bars (for execution marks) ─────────────


class _WarmupFeedHarness:
    _registered_instrument_ids = RebalanceStrategy._registered_instrument_ids
    _warm_startup_cache = RebalanceStrategy._warm_startup_cache

    def __init__(self, contracts: dict[SleeveName, DataContract], feeds: list[_FakeFeed]) -> None:
        self.config = SimpleNamespace(warmup_cache_on_start=True)
        self.clock = _Clock()
        self._sleeve_to_contract = contracts
        self._feeds = {feed.continuous_id: feed for feed in feeds}
        self.requested: list[object] = []

    def request_bars(self, bar_type: object, **_kwargs: object) -> None:
        self.requested.append(bar_type)


def test_warmup_requests_front_leg_bars_alongside_native_instruments() -> None:
    """D5: each feed's front leg is warmed into the live cache (execution marks), in the same
    native request_bars pass as the book's raw instruments — the feed's adjusted series stays
    off-cache, but the front leg's raw bars are needed to value/fill the rolled order target."""
    native = InstrumentId.from_str("VUSA.XLON")
    front = InstrumentId.from_str("ESM4.XCME")
    harness = _WarmupFeedHarness(
        {SleeveName("trend"): _contract(futures=("ES",), instrument_ids=(native,))},
        [_FakeFeed(InstrumentId.from_str("ES.XCME"), front)],
    )

    harness._warm_startup_cache("1D")

    requested = {str(bar_type) for bar_type in harness.requested}
    assert str(raw_bar_type(native, "1D")) in requested
    assert str(raw_bar_type(front, "1D")) in requested


def test_warmup_warms_front_legs_for_a_futures_only_book() -> None:
    """A book with only continuous roots (no native instruments) still warms its front legs —
    the empty-native early-out must not skip the feeds."""
    front = InstrumentId.from_str("ESM4.XCME")
    harness = _WarmupFeedHarness(
        {SleeveName("trend"): _contract(futures=("ES",))},
        [_FakeFeed(InstrumentId.from_str("ES.XCME"), front)],
    )

    harness._warm_startup_cache("1D")

    assert str(raw_bar_type(front, "1D")) in {str(bar_type) for bar_type in harness.requested}


# ── D6: on_start installs each feed by its continuous id and routes its front leg ─────────────


class _InstallHarness:
    _install_feeds = RebalanceStrategy._install_feeds

    def __init__(self) -> None:
        self._feeds: dict[InstrumentId, _FakeFeed] = {}
        self._leg_to_feed: dict[InstrumentId, _FakeFeed] = {}


def test_install_feeds_registers_by_continuous_id_and_routes_the_front_leg() -> None:
    """D6: a built feed is registered by its synthetic continuous id (so NautilusMarketData reads
    the root from it) and its current front leg is mapped to it (so on_bar routes that leg's bars
    to it)."""
    es = InstrumentId.from_str("ES.XCME")
    es_front = InstrumentId.from_str("ESM4.XCME")
    kc = InstrumentId.from_str("KC.IFUS")
    kc_front = InstrumentId.from_str("KCN4.IFUS")
    harness = _InstallHarness()

    harness._install_feeds([_FakeFeed(es, es_front), _FakeFeed(kc, kc_front)])

    assert set(harness._feeds) == {es, kc}
    assert set(harness._leg_to_feed) == {es_front, kc_front}
    assert harness._feeds[es].continuous_id == es
    assert harness._leg_to_feed[kc_front].continuous_id == kc


# ── E2: orders for a continuous root are submitted on the front leg ───────────────────────────


class _FakeMarketData:
    def __init__(self, front_by_root: dict[InstrumentId, InstrumentId], qty: Quantity) -> None:
        self._front_by_root = front_by_root
        self._qty = qty

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        return self._front_by_root.get(instrument_id, instrument_id)

    def make_quantity(self, instrument_id: InstrumentId, raw_shares: float) -> Quantity:
        return self._qty


class _SubmitHarness:
    _submit_order_intent = RebalanceStrategy._submit_order_intent
    _require_market_data = RebalanceStrategy._require_market_data

    def __init__(self, market_data: _FakeMarketData) -> None:
        self._market_data = market_data
        self.config = SimpleNamespace(fill_time_in_force=None)
        self.log = SimpleNamespace(error=lambda *a: None, info=lambda *a: None)
        self.order_factory = SimpleNamespace(market=lambda **kwargs: kwargs)  # order == its kwargs
        self.submitted: list[dict[str, object]] = []

    def submit_order(self, order: dict[str, object]) -> None:
        self.submitted.append(order)


def test_submit_order_intent_routes_a_continuous_root_to_the_front_leg() -> None:
    """E2: an OrderIntent keyed by the continuous root is submitted on the dated front leg (the
    synthetic root is not tradeable) — the order target rolls in lock-step with the data roll."""
    cont = InstrumentId.from_str("ES.XCME")
    front = InstrumentId.from_str("ESM4.XCME")
    qty = Quantity.from_int(3)
    harness = _SubmitHarness(_FakeMarketData({cont: front}, qty))

    harness._submit_order_intent(
        OrderIntent(instrument_id=cont, side=OrderSide.BUY, quantity=3.0, source=OrderSource.ALPHA)
    )

    order = harness.submitted[0]
    assert order["instrument_id"] == front
    assert order["quantity"] == qty


def test_submit_order_intent_leaves_a_native_instrument_untouched() -> None:
    native = InstrumentId.from_str("VUSA.XLON")
    qty = Quantity.from_int(5)
    harness = _SubmitHarness(_FakeMarketData({}, qty))

    harness._submit_order_intent(
        OrderIntent(instrument_id=native, side=OrderSide.SELL, quantity=5.0, source=OrderSource.ALPHA)
    )

    assert harness.submitted[0]["instrument_id"] == native


# ── G: dynamic mid-run leg loading (request_instrument → on_instrument → subscribe) ───────────


class _FakeCache:
    def __init__(self, present: tuple[InstrumentId, ...] = ()) -> None:
        self._present = set(present)

    def instrument(self, instrument_id: InstrumentId) -> object | None:
        return object() if instrument_id in self._present else None


class _LegLoadHarness:
    _ensure_leg_subscribed = RebalanceStrategy._ensure_leg_subscribed
    on_instrument = RebalanceStrategy.on_instrument
    _require_book_timeframe = RebalanceStrategy._require_book_timeframe

    def __init__(self, cache: _FakeCache, book_timeframe: str = "1D") -> None:
        self.cache = cache
        self._book_timeframe = book_timeframe
        self._pending_leg_subscriptions: set[InstrumentId] = set()
        self.requested_instruments: list[InstrumentId] = []
        self.subscribed: list[object] = []

    def request_instrument(self, instrument_id: InstrumentId) -> None:
        self.requested_instruments.append(instrument_id)

    def subscribe_bars(self, bar_type: object) -> None:
        self.subscribed.append(bar_type)


def test_ensure_leg_subscribed_dynamically_loads_an_uncached_leg() -> None:
    """G: a leg that is not yet in the cache (no preloaded horizon — IB has no load_all) is loaded
    at runtime via request_instrument; the subscription is deferred to on_instrument, since
    subscribe/order methods require the instrument to be present first."""
    leg = InstrumentId.from_str("ESU4.XCME")
    harness = _LegLoadHarness(_FakeCache())

    harness._ensure_leg_subscribed(leg)

    assert harness.requested_instruments == [leg]
    assert leg in harness._pending_leg_subscriptions
    assert harness.subscribed == []  # not subscribed until the definition arrives


def test_ensure_leg_subscribed_subscribes_an_already_cached_leg_immediately() -> None:
    """A leg whose definition is already present (preloaded or loaded by an earlier roll) is
    subscribed straight away — no redundant request_instrument."""
    leg = InstrumentId.from_str("ESM4.XCME")
    harness = _LegLoadHarness(_FakeCache(present=(leg,)))

    harness._ensure_leg_subscribed(leg)

    assert harness.requested_instruments == []
    assert harness._pending_leg_subscriptions == set()
    assert str(harness.subscribed[0]) == str(raw_bar_type(leg, "1D"))


def test_on_instrument_subscribes_a_pending_leg_when_its_definition_arrives() -> None:
    """G: the async on_instrument callback completes the deferred subscription for a leg we
    requested, then clears it from the pending set."""
    leg = InstrumentId.from_str("ESU4.XCME")
    harness = _LegLoadHarness(_FakeCache())
    harness._pending_leg_subscriptions.add(leg)

    harness.on_instrument(SimpleNamespace(id=leg))

    assert str(harness.subscribed[0]) == str(raw_bar_type(leg, "1D"))
    assert leg not in harness._pending_leg_subscriptions


def test_on_instrument_ignores_an_instrument_we_did_not_request() -> None:
    """Reconciled venue instruments (and anything else we did not dynamically request) arrive via
    on_instrument too — they must not trigger a spurious bar subscription."""
    other = InstrumentId.from_str("VUSA.XLON")
    harness = _LegLoadHarness(_FakeCache())

    harness.on_instrument(SimpleNamespace(id=other))

    assert harness.subscribed == []
