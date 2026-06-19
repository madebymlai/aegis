"""IB InstrumentProvider wiring for live/paper listed-instrument identity.

ListedRef resolution is vendor-native: the mode layer asks IB's
InstrumentProvider to load each FIGI, then the strategy records the returned
Nautilus InstrumentId from the reconciled cache.  This module owns the small
IB-shaped config dictionaries and the cache metadata read needed to build that
boot bimap.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol

from aegis_runtime import InstrumentRef, ListedRef
from aegis_runtime.currency import major_currency
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.execution.figi_resolver import FigiResolutionError

IB_LISTED_EXCHANGE = "SMART"
IB_LISTED_SEC_TYPE = "STK"
IB_LISTED_SEC_ID_TYPE = "FIGI"

# Nautilus's IB provider accepts symbol-prefix -> MIC overrides.  IB sometimes
# reports London ETF listings on raw pseudo-venues (spike: IGLN.LSEETF); the
# override pins those known symbols to the listing MIC returned by IB.
IB_LISTED_MIC_OVERRIDES: dict[str, str] = {"IGLN": "XLON"}

IBContractConfig = dict[str, str]


class LoadedInstrument(Protocol):
    """Cache instrument fields needed to recover a FIGI-qualified IB contract."""

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


def _instrument_figi(instrument: LoadedInstrument) -> str | None:
    info = getattr(instrument, "info", None)
    if not isinstance(info, Mapping):
        return None
    contract = info.get("contract")
    if not isinstance(contract, Mapping):
        return None
    sec_id_type = contract.get("secIdType")
    if not isinstance(sec_id_type, str) or sec_id_type.upper() != IB_LISTED_SEC_ID_TYPE:
        return None
    sec_id = contract.get("secId")
    return sec_id if isinstance(sec_id, str) and sec_id else None
