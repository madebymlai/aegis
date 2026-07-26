from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import raw_bar_type
from aegis_data.marking import DeclaredMarkingResolver
from aegis_trader.bundles.book import AssembledBook
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.book_market_clock import BookMarketClock
from aegis_trader.trader.pipeline import CompletedRebalancePeriod, DueSleeve
from tests.support.factories import assemble_test_book, make_bundle

_DAY_NS = 86_400_000_000_000
_PERIOD_10_START_NS = 864_000_000_000_000
_PERIOD_10_WITHIN_NS = 864_000_000_000_001
_PERIOD_10_US_CLOSE_NS = 880_000_000_000_000
_PERIOD_10_EU_CLOSE_NS = 885_000_000_000_000
_PERIOD_11_START_NS = 950_400_000_000_000
_INSTRUMENT = InstrumentId.from_str("SPY.ARCA")
_SECOND_INSTRUMENT = InstrumentId.from_str("VGK.ARCA")
_CONTINUOUS = InstrumentId.from_str("ES.XCME")
_OLD_FRONT = InstrumentId.from_str("ESM4.XCME")
_NEW_FRONT = InstrumentId.from_str("ESU4.XCME")
_SLEEVE = SleeveName("trend")
_ALPHA = SleeveName("alpha")
_ZETA = SleeveName("zeta")


def test_first_bar_establishes_the_sleeve_period_without_producing_a_due() -> None:
    clock = BookMarketClock(
        book=_cash_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )

    clock.advance(
        raw_bar_type(_INSTRUMENT, "1D"),
        ts_ns=_PERIOD_10_START_NS,
    )
    has_pending_due = clock.has_pending_due
    due = clock.drain()

    assert has_pending_due is False
    assert due == ()


def test_second_bar_within_the_period_produces_no_due() -> None:
    clock = BookMarketClock(
        book=_cash_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )
    bar_type = raw_bar_type(_INSTRUMENT, "1D")

    clock.advance(bar_type, _PERIOD_10_START_NS)
    clock.advance(bar_type, _PERIOD_10_WITHIN_NS)
    has_pending_due = clock.has_pending_due
    due = clock.drain()

    assert has_pending_due is False
    assert due == ()


def test_period_boundary_produces_exactly_one_due() -> None:
    clock = BookMarketClock(
        book=_cash_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )
    bar_type = raw_bar_type(_INSTRUMENT, "1D")
    clock.advance(bar_type, _PERIOD_10_START_NS)

    clock.advance(bar_type, _PERIOD_11_START_NS)
    has_pending_due = clock.has_pending_due
    due = clock.drain()

    assert has_pending_due is True
    assert due == (
        DueSleeve(
            sleeve=_SLEEVE,
            period=CompletedRebalancePeriod(period=10, period_ns=_DAY_NS),
        ),
    )


def test_drain_empties_the_pending_due_set() -> None:
    clock = BookMarketClock(
        book=_cash_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )
    bar_type = raw_bar_type(_INSTRUMENT, "1D")
    clock.advance(bar_type, _PERIOD_10_START_NS)
    clock.advance(bar_type, _PERIOD_11_START_NS)

    first_drain = clock.drain()
    has_pending_due = clock.has_pending_due
    second_drain = clock.drain()

    assert first_drain != ()
    assert has_pending_due is False
    assert second_drain == ()


def test_sleeve_consuming_several_streams_produces_one_due_per_period() -> None:
    clock = BookMarketClock(
        book=_multi_stream_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )
    first = raw_bar_type(_INSTRUMENT, "1D")
    second = raw_bar_type(_SECOND_INSTRUMENT, "1D")
    clock.advance(first, _PERIOD_10_START_NS)
    clock.advance(second, _PERIOD_10_START_NS)

    clock.advance(first, _PERIOD_11_START_NS)
    first_stream_due = clock.drain()
    clock.advance(second, _PERIOD_11_START_NS)
    second_stream_due = clock.drain()

    assert first_stream_due == (
        DueSleeve(
            sleeve=_SLEEVE,
            period=CompletedRebalancePeriod(period=10, period_ns=_DAY_NS),
        ),
    )
    assert second_stream_due == ()


def test_session_close_offsets_within_one_period_produce_no_due() -> None:
    clock = BookMarketClock(
        book=_multi_stream_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )
    first = raw_bar_type(_INSTRUMENT, "1D")
    second = raw_bar_type(_SECOND_INSTRUMENT, "1D")

    clock.advance(first, _PERIOD_10_US_CLOSE_NS)
    clock.advance(second, _PERIOD_10_EU_CLOSE_NS)
    due = clock.drain()

    assert due == ()


def test_drain_orders_due_sleeves_by_name() -> None:
    clock = BookMarketClock(
        book=_two_sleeve_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )
    alpha_bar = raw_bar_type(_INSTRUMENT, "1D")
    zeta_bar = raw_bar_type(_SECOND_INSTRUMENT, "1D")
    clock.advance(zeta_bar, _PERIOD_10_START_NS)
    clock.advance(alpha_bar, _PERIOD_10_START_NS)

    clock.advance(zeta_bar, _PERIOD_11_START_NS)
    clock.advance(alpha_bar, _PERIOD_11_START_NS)
    due = clock.drain()

    assert due == (
        DueSleeve(
            sleeve=_ALPHA,
            period=CompletedRebalancePeriod(period=10, period_ns=_DAY_NS),
        ),
        DueSleeve(
            sleeve=_ZETA,
            period=CompletedRebalancePeriod(period=10, period_ns=_DAY_NS),
        ),
    )


def test_dated_front_legs_advance_the_sleeve_declaring_their_continuous_root() -> None:
    clock = BookMarketClock(
        book=_continuous_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )

    clock.advance(
        raw_bar_type(_OLD_FRONT, "1D"),
        _PERIOD_10_START_NS,
        continuous_id=_CONTINUOUS,
    )
    clock.advance(
        raw_bar_type(_NEW_FRONT, "1D"),
        _PERIOD_11_START_NS,
        continuous_id=_CONTINUOUS,
    )
    due = clock.drain()

    assert due == (
        DueSleeve(
            sleeve=_SLEEVE,
            period=CompletedRebalancePeriod(period=10, period_ns=_DAY_NS),
        ),
    )


def _cash_book() -> AssembledBook:
    return assemble_test_book(
        BookConfig(
            sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
            base_currency="EUR",
        ),
        {"trend.whl": make_bundle(native_instrument_ids=(_INSTRUMENT,))},
    )


def _multi_stream_book() -> AssembledBook:
    return assemble_test_book(
        BookConfig(
            sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
            base_currency="EUR",
        ),
        {
            "trend.whl": make_bundle(
                native_instrument_ids=(_INSTRUMENT, _SECOND_INSTRUMENT)
            )
        },
    )


def _two_sleeve_book() -> AssembledBook:
    return assemble_test_book(
        BookConfig(
            sleeves=(
                SleeveConfig(_ZETA, "zeta.whl", 0.5),
                SleeveConfig(_ALPHA, "alpha.whl", 0.5),
            ),
            base_currency="EUR",
        ),
        {
            "zeta.whl": make_bundle(native_instrument_ids=(_SECOND_INSTRUMENT,)),
            "alpha.whl": make_bundle(native_instrument_ids=(_INSTRUMENT,)),
        },
    )


def _continuous_book() -> AssembledBook:
    return assemble_test_book(
        BookConfig(
            sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
            base_currency="EUR",
        ),
        {
            "trend.whl": make_bundle(
                native_instrument_ids=(),
                continuous_futures={"ES": _CONTINUOUS},
            )
        },
    )
