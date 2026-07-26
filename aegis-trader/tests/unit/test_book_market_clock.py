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

    clock.advance(raw_bar_type(_INSTRUMENT, "1D"), 10 * _DAY_NS)

    assert clock.has_pending_due is False
    assert clock.drain() == ()


def test_period_boundary_produces_one_due_and_drain_empties_the_clock() -> None:
    clock = BookMarketClock(
        book=_cash_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )
    bar_type = raw_bar_type(_INSTRUMENT, "1D")
    clock.advance(bar_type, 10 * _DAY_NS)
    clock.advance(bar_type, 10 * _DAY_NS + 1)

    clock.advance(bar_type, 11 * _DAY_NS)

    assert clock.has_pending_due is True
    assert clock.drain() == (
        DueSleeve(
            sleeve=_SLEEVE,
            period=CompletedRebalancePeriod(period=10, period_ns=_DAY_NS),
        ),
    )
    assert clock.has_pending_due is False
    assert clock.drain() == ()


def test_several_streams_and_session_closes_produce_one_due_per_period() -> None:
    clock = BookMarketClock(
        book=_multi_stream_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )
    first = raw_bar_type(_INSTRUMENT, "1D")
    second = raw_bar_type(_SECOND_INSTRUMENT, "1D")
    clock.advance(first, 10 * _DAY_NS + 16_000_000_000_000)
    clock.advance(second, 10 * _DAY_NS + 21_000_000_000_000)

    clock.advance(first, 11 * _DAY_NS + 16_000_000_000_000)
    clock.advance(second, 11 * _DAY_NS + 21_000_000_000_000)

    assert clock.drain() == (
        DueSleeve(
            sleeve=_SLEEVE,
            period=CompletedRebalancePeriod(period=10, period_ns=_DAY_NS),
        ),
    )


def test_drain_orders_due_sleeves_by_name() -> None:
    clock = BookMarketClock(
        book=_two_sleeve_book(),
        bar_type_resolver=DeclaredMarkingResolver(),
    )
    alpha_bar = raw_bar_type(_INSTRUMENT, "1D")
    zeta_bar = raw_bar_type(_SECOND_INSTRUMENT, "1D")
    clock.advance(zeta_bar, 10 * _DAY_NS)
    clock.advance(alpha_bar, 10 * _DAY_NS)

    clock.advance(zeta_bar, 11 * _DAY_NS)
    clock.advance(alpha_bar, 11 * _DAY_NS)

    assert clock.drain() == (
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
        10 * _DAY_NS,
        continuous_id=_CONTINUOUS,
    )
    clock.advance(
        raw_bar_type(_NEW_FRONT, "1D"),
        11 * _DAY_NS,
        continuous_id=_CONTINUOUS,
    )

    assert clock.drain() == (
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
