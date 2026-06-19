"""IB InstrumentProvider wiring for live/paper instrument identity.

ListedRef and FuturesRef resolution is vendor-native: the mode layer asks IB's
InstrumentProvider to load provider-qualified contracts, then the strategy
records the returned Nautilus InstrumentId from the reconciled cache.  This
module owns the small IB-shaped config dictionaries and the cache metadata read
needed to build that boot bimap.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Protocol

from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.roll import DatedContract, roll_schedule
from aegis_runtime import FuturesRef, InstrumentRef, ListedRef
from aegis_runtime.currency import major_currency
from aegis_trader.execution.figi_resolver import FigiResolutionError

IB_LISTED_EXCHANGE = "SMART"
IB_LISTED_SEC_TYPE = "STK"
IB_LISTED_SEC_ID_TYPE = "FIGI"
IB_FUTURES_SEC_TYPE = "FUT"
IB_FUTURES_EXCHANGE = "CME"

# Nautilus's IB provider accepts symbol-prefix/exchange-code -> MIC overrides.
# IB sometimes reports London ETF listings on raw pseudo-venues (spike:
# IGLN.LSEETF), and COMEX metals on raw COMEX; the overrides pin those known
# provider codes to the listing MIC returned by IB.
IB_LISTED_MIC_OVERRIDES: dict[str, str] = {"IGLN": "XLON"}
IB_FUTURES_MIC_OVERRIDES: dict[str, str] = {"COMEX": "XCEC"}

IBContractConfig = dict[str, str]
FuturesContractChains = Mapping[str, Sequence[DatedContract]]


class LoadedInstrument(Protocol):
    """Cache instrument fields needed to recover a provider-qualified contract."""

    id: InstrumentId
    info: object


class _RefContract(Protocol):
    refs: tuple[InstrumentRef, ...]


class BundleCurrencyPlan(Protocol):
    """ExecutionBundle surface that carries the locked quote-currency plan."""

    contract: _RefContract
    symbols: tuple[str, ...]
    currency_by_symbol: Mapping[str, str]


def listed_ref_ib_contracts(refs: Iterable[InstrumentRef]) -> list[IBContractConfig]:
    """IBContract-shaped dictionaries for loading ListedRefs by FIGI."""
    listed_refs = sorted({ref for ref in refs if isinstance(ref, ListedRef)})
    return [
        {
            "secType": IB_LISTED_SEC_TYPE,
            "secIdType": IB_LISTED_SEC_ID_TYPE,
            "secId": ref.figi,
            "exchange": IB_LISTED_EXCHANGE,
        }
        for ref in listed_refs
    ]


def select_front_futures_contract(
    ref: FuturesRef,
    as_of: date,
    contracts: Sequence[DatedContract],
    *,
    roll_lead_days: int = 5,
) -> DatedContract:
    """Select the dated contract a FuturesRef represents on *as_of*.

    The live path keys only on the futures root plus roll rule.  ``dataset`` and
    ``adjustment`` are research-source metadata and are intentionally not read.
    Eligible dated contracts and expiries are supplied by the caller (IBKR chain
    at live, Databento definitions at research), so the same expiry-driven rule
    reproduces on both sides without a per-root month table.
    """
    if ref.roll_rule != "calendar":
        raise FigiResolutionError(
            f"unsupported futures roll rule {ref.roll_rule!r}; expected 'calendar'"
        )
    if not contracts:
        raise FigiResolutionError(f"FuturesRef root {ref.root!r} has no dated contracts")

    ordered = tuple(sorted(contracts, key=lambda contract: contract.last_trade))
    end = ordered[-1].last_trade
    schedule = roll_schedule(ordered, as_of, end, roll_lead_days=roll_lead_days)
    if not schedule.symbols:
        raise FigiResolutionError(
            f"FuturesRef root {ref.root!r} has no dated contract active on {as_of}"
        )

    symbol_to_contract = {contract.symbol: contract for contract in ordered}
    for symbol, roll_date in zip(schedule.symbols, schedule.roll_dates, strict=False):
        if as_of < roll_date:
            return symbol_to_contract[symbol]
    return symbol_to_contract[schedule.symbols[-1]]


def futures_ref_ib_contracts(
    refs: Iterable[InstrumentRef],
    *,
    as_of: date,
    contract_chains: FuturesContractChains,
    roll_lead_days: int = 5,
) -> list[IBContractConfig]:
    """IBContract-shaped dictionaries for loading FuturesRefs by localSymbol.

    The contracts intentionally use IB's exchange-native Globex ``localSymbol``
    and do not mention Databento/yfinance identifiers.
    """
    selected = _selected_futures_contracts(
        _unique_futures_refs(refs),
        as_of=as_of,
        contract_chains=contract_chains,
        roll_lead_days=roll_lead_days,
    )
    contracts_by_symbol = {
        contract.symbol: _ib_futures_contract(contract)
        for contract in selected.values()
    }
    return [contracts_by_symbol[symbol] for symbol in sorted(contracts_by_symbol)]


def loaded_listed_ref_bimap(
    refs: Iterable[ListedRef],
    instruments: Iterable[LoadedInstrument],
) -> dict[ListedRef, InstrumentId]:
    """Map requested ListedRefs to the InstrumentIds IB actually loaded.

    IB's InstrumentProvider qualifies the FIGI contracts and stores the returned
    Nautilus instruments in the cache.  The cache instrument's ``info`` carries
    the qualified IB contract metadata, including the request FIGI.  Missing or
    duplicate matches are closed failures: the book must not trade an unidentified
    or ambiguous listing.
    """
    requested = set(refs)
    if not requested:
        return {}

    by_figi = {ref.figi: ref for ref in requested}
    bimap: dict[ListedRef, InstrumentId] = {}
    duplicates: list[str] = []
    for instrument in instruments:
        figi = _instrument_figi(instrument)
        if figi is None or figi not in by_figi:
            continue
        ref = by_figi[figi]
        if ref in bimap:
            duplicates.append(figi)
            continue
        bimap[ref] = instrument.id

    if duplicates:
        joined = ", ".join(sorted(set(duplicates)))
        raise FigiResolutionError(f"ListedRef FIGI(s) {joined} loaded more than once by IB")

    missing = sorted(ref.figi for ref in requested if ref not in bimap)
    if missing:
        joined = ", ".join(missing)
        raise FigiResolutionError(
            f"ListedRef FIGI(s) {joined} were not loaded by the IB InstrumentProvider"
        )
    return bimap


def loaded_futures_ref_bimap(
    refs: Iterable[FuturesRef],
    instruments: Iterable[LoadedInstrument],
    *,
    as_of: date,
    contract_chains: FuturesContractChains,
    roll_lead_days: int = 5,
) -> dict[FuturesRef, InstrumentId]:
    """Map requested FuturesRefs to the IB-loaded dated contracts.

    The roll rule selects each front ``localSymbol``; the provider-loaded cache
    tells us the actual Nautilus ``InstrumentId`` and MIC venue IB returned.
    """
    requested = set(refs)
    if not requested:
        return {}

    selected = _selected_futures_contracts(
        sorted(requested),
        as_of=as_of,
        contract_chains=contract_chains,
        roll_lead_days=roll_lead_days,
    )
    by_local_symbol: dict[str, FuturesRef] = {}
    for ref, contract in selected.items():
        previous = by_local_symbol.get(contract.symbol)
        if previous is not None and previous != ref:
            raise FigiResolutionError(
                f"FuturesRefs {previous.value!r} and {ref.value!r} both resolve to "
                f"{contract.symbol!r}; inverse mapping would be ambiguous"
            )
        by_local_symbol[contract.symbol] = ref

    bimap: dict[FuturesRef, InstrumentId] = {}
    duplicates: list[str] = []
    for instrument in instruments:
        local_symbol = _instrument_local_symbol(instrument)
        if local_symbol is None or local_symbol not in by_local_symbol:
            continue
        ref = by_local_symbol[local_symbol]
        if ref in bimap:
            duplicates.append(local_symbol)
            continue
        bimap[ref] = instrument.id

    if duplicates:
        joined = ", ".join(sorted(set(duplicates)))
        raise FigiResolutionError(
            f"Futures contract(s) {joined} loaded more than once by IB"
        )

    missing = sorted(
        symbol for symbol, ref in by_local_symbol.items() if ref not in bimap
    )
    if missing:
        joined = ", ".join(missing)
        raise FigiResolutionError(
            f"Futures contract(s) {joined} were not loaded by the IB InstrumentProvider"
        )
    return bimap


def declared_ref_currencies(bundles: Iterable[BundleCurrencyPlan]) -> dict[InstrumentRef, str]:
    """Return bundle-declared quote currencies keyed by InstrumentRef.

    Runtime contracts carry refs only; the locked execution plan keeps the
    per-symbol quote tokens (including minor units like GBp).  Use that metadata
    only to reconcile IB's major-currency reporting back to the quote token the
    bundle was minted against.
    """
    currencies: dict[InstrumentRef, str] = {}
    for bundle in bundles:
        for ref, symbol in zip(bundle.contract.refs, bundle.symbols, strict=True):
            currency = bundle.currency_by_symbol[symbol]
            previous = currencies.get(ref)
            if previous is not None and previous != currency:
                raise FigiResolutionError(
                    f"InstrumentRef {ref.value!r} has conflicting bundle quote currencies "
                    f"{previous!r} and {currency!r}"
                )
            currencies[ref] = currency
    return currencies


def reconcile_quote_currency(
    ref: InstrumentRef,
    provider_currency: str,
    declared_currencies: Mapping[InstrumentRef, str],
) -> str:
    """Reconcile provider currency with the bundle's quote token.

    IB reports LSE pence instruments as GBP; RD/bundle data correctly records the
    quote token as GBp.  When the declared token's major currency matches the
    provider major currency, keep the declared token so sizing applies the pence
    factor.  A true currency mismatch fails closed.
    """
    declared = declared_currencies.get(ref)
    if declared is None:
        return provider_currency
    if declared == provider_currency:
        return declared

    declared_major = major_currency(declared)
    provider_major = major_currency(provider_currency)
    if declared_major == provider_currency:
        return declared
    if provider_major == declared:
        return provider_currency
    raise FigiResolutionError(
        f"InstrumentRef {ref.value!r} bundle quote currency {declared!r} "
        f"disagrees with provider currency {provider_currency!r}"
    )


def _selected_futures_contracts(
    refs: Iterable[FuturesRef],
    *,
    as_of: date,
    contract_chains: FuturesContractChains,
    roll_lead_days: int,
) -> dict[FuturesRef, DatedContract]:
    selected: dict[FuturesRef, DatedContract] = {}
    for ref in refs:
        chain = _contract_chain_for(ref, contract_chains)
        selected[ref] = select_front_futures_contract(
            ref, as_of, chain, roll_lead_days=roll_lead_days
        )
    return selected


def _unique_futures_refs(refs: Iterable[InstrumentRef]) -> tuple[FuturesRef, ...]:
    return tuple(sorted({ref for ref in refs if isinstance(ref, FuturesRef)}))


def _ib_futures_contract(contract: DatedContract) -> IBContractConfig:
    return {
        "secType": IB_FUTURES_SEC_TYPE,
        "localSymbol": contract.symbol,
        "exchange": IB_FUTURES_EXCHANGE,
    }


def _contract_chain_for(
    ref: FuturesRef, contract_chains: FuturesContractChains
) -> Sequence[DatedContract]:
    try:
        return contract_chains[ref.root]
    except KeyError:
        raise FigiResolutionError(
            f"FuturesRef root {ref.root!r} has no IBKR contract chain"
        ) from None


def _instrument_figi(instrument: LoadedInstrument) -> str | None:
    contract = _instrument_contract_info(instrument)
    if contract is None:
        return None
    sec_id_type = contract.get("secIdType")
    if not isinstance(sec_id_type, str) or sec_id_type.upper() != IB_LISTED_SEC_ID_TYPE:
        return None
    sec_id = contract.get("secId")
    return sec_id if isinstance(sec_id, str) and sec_id else None


def _instrument_local_symbol(instrument: LoadedInstrument) -> str | None:
    contract = _instrument_contract_info(instrument)
    if contract is not None:
        local_symbol = contract.get("localSymbol")
        if isinstance(local_symbol, str) and local_symbol:
            return local_symbol
    raw_symbol = getattr(instrument, "raw_symbol", None)
    raw_value = getattr(raw_symbol, "value", raw_symbol)
    return raw_value if isinstance(raw_value, str) and raw_value else None


def _instrument_contract_info(instrument: LoadedInstrument) -> Mapping | None:
    info = getattr(instrument, "info", None)
    if not isinstance(info, Mapping):
        return None
    contract = info.get("contract")
    return contract if isinstance(contract, Mapping) else None
