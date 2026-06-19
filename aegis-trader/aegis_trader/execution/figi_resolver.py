"""FIGI → Nautilus InstrumentId Security Master (ADR-0002).

Resolves canonical FIGIs from the bundle's DataContract to venue-specific
Nautilus InstrumentIds at startup via OpenFIGI + a bounded
Bloomberg-exchange→MIC table.  Fail-closed on ambiguity or unmapped data.

Netting stays in FIGI space; the bimap produced here is queried only at the
execution edge (order submission, position diffing).

Architecture invariant (ADR-0003): this module imports Nautilus types
(InstrumentId) but NO broker-specific imports — the exchange table is
exchange-to-MIC, not exchange-to-IBKR.  The IBKR adapter is isolated to
the InstrumentProvider configuration in the runtime mode layer.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from aegis_runtime import FuturesRef, InstrumentRef, ListedRef
from nautilus_trader.model.identifiers import InstrumentId

OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
_MAX_JOBS_PER_REQUEST = 10
_API_KEY_ENV = "OPENFIGI_API_KEY"

# ── Bounded exchange-code table ───────────────────────────────────────────────
# Bloomberg exchange code → ISO 10383 MIC (Nautilus venue).
# Stable, human-auditable, one line per exchange.
# New instrument on known exchange → zero edits; new exchange → one line.

_bloomberg_exch_to_mic: dict[str, str] = {
    "LN": "XLON",      # London Stock Exchange
    "US": "XNYS",      # New York Stock Exchange (primary listing)
    "UW": "XUSP",      # US OTC / PINK
    "UN": "XNYS",      # NYSE (alternate code)
    "UQ": "XNAS",      # NASDAQ
    "GR": "XETR",      # Xetra / Deutsche Börse
    "GF": "XFRA",      # Frankfurt
    "GS": "XSTU",      # Stuttgart
    "NA": "XAMS",      # Euronext Amsterdam
    "FP": "XPAR",      # Euronext Paris
    "IM": "XMIL",      # Borsa Italiana / Milan
    "SM": "XMAD",      # Madrid
    "SW": "XSWX",      # SIX Swiss Exchange
    "JP": "XTKS",      # Tokyo Stock Exchange
    "HK": "XHKG",      # Hong Kong
    "AU": "XASX",      # Australian Securities Exchange
    "CN": "XCNQ",      # Canadian Securities Exchange / TSX-V
    "CT": "XTSE",      # Toronto Stock Exchange
    "EB": "XBRU",      # Euronext Brussels
    "DC": "XCSE",      # Copenhagen
    "SS": "XSTO",      # Stockholm
    "HE": "XHEL",      # Helsinki
    "NO": "XOSL",      # Oslo
    "PL": "XWAR",      # Warsaw
    "AV": "XWBO",      # Vienna
    "ID": "XIDX",      # Indonesia Stock Exchange
    "MK": "XKLS",      # Bursa Malaysia
    "SP": "XSES",      # Singapore
    "KS": "XKRX",      # Korea Exchange
    "TT": "XTAI",      # Taiwan Stock Exchange
    "TH": "XBKK",      # Thailand
    "PM": "XMEX",      # Mexican Stock Exchange
    "BZ": "XSAO",      # Brazil / B3
    "AR": "XBUE",      # Buenos Aires
    "SJ": "XJSE",      # Johannesburg
    "TA": "XTAE",      # Tel Aviv
    "IN": "XBOM",      # Bombay Stock Exchange / NSE
    "GLBX": "XCME",    # CME Globex
}


class FigiResolutionError(ValueError):
    """A FIGI could not be resolved to a Nautilus InstrumentId."""


@dataclass(frozen=True)
class _FigiMetadata:
    """Contract metadata extracted from an OpenFIGI exchange-level record."""

    figi: str
    ticker: str
    exch_code: str


@dataclass(frozen=True)
class FuturesContract:
    """Dated futures contract selected by the roll calendar."""

    symbol: str
    exchange: str


FuturesCalendar = Callable[[FuturesRef, date], FuturesContract]
FuturesContractResolver = Callable[[FuturesContract], InstrumentId]


# ── transport ─────────────────────────────────────────────────────────────────

OpenFigiTransport = Callable[..., list[dict]]


class _OpenFigiClient:
    """Thin OpenFIGI ``/v3/mapping`` adapter with auth and per-request job cap.

    A real HTTP transport is the default; tests inject a stubbed transport.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: OpenFigiTransport | None = None,
        max_jobs_per_request: int = _MAX_JOBS_PER_REQUEST,
    ) -> None:
        self._api_key = api_key
        self._transport = transport if transport is not None else _http_transport
        self._max_jobs_per_request = max_jobs_per_request

    @classmethod
    def from_env(cls) -> _OpenFigiClient:
        return cls(api_key=os.environ.get(_API_KEY_ENV))

    def map(self, jobs: list[dict]) -> list[dict]:
        headers = self._headers()
        responses: list[dict] = []
        for start in range(0, len(jobs), self._max_jobs_per_request):
            chunk = jobs[start : start + self._max_jobs_per_request]
            responses.extend(self._transport(headers=headers, jobs=chunk))
        return responses

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["X-OPENFIGI-APIKEY"] = self._api_key
        return h


def _http_transport(*, headers: dict[str, str], jobs: list[dict]) -> list[dict]:
    import requests

    response = requests.post(OPENFIGI_MAPPING_URL, headers=headers, json=jobs, timeout=30)
    response.raise_for_status()
    return response.json()


# ── resolver ──────────────────────────────────────────────────────────────────


class FigiInstrumentResolver:
    """Resolves ListedRefs to Nautilus InstrumentIds via OpenFIGI + exchange table.

    A ListedRef resolution ignores ``as_of``: permanently listed instruments are
    date-invariant. Resolution is atomic when preloading a set of refs.
    """

    def __init__(
        self,
        *,
        futures_calendar: FuturesCalendar | None = None,
        futures_contract_resolver: FuturesContractResolver | None = None,
    ) -> None:
        self._bimap: dict[ListedRef, InstrumentId] = {}
        self._futures_calendar = futures_calendar
        self._futures_contract_resolver = futures_contract_resolver
        self._contract_to_ref: dict[InstrumentId, InstrumentRef] = {}

    def resolve(
        self,
        ref: InstrumentRef | str | set[InstrumentRef | str],
        as_of: date | None = None,
        *,
        transport: OpenFigiTransport | None = None,
    ) -> InstrumentId | dict[InstrumentRef | str, InstrumentId]:
        """Resolve one InstrumentRef as-of a date, or preload a set of refs.

        ``as_of`` is accepted for the asset-agnostic Security Master interface;
        ListedRef ignores it and resolves date-invariantly.
        """
        if isinstance(ref, set):
            return self.resolve_many(ref, transport=transport)
        if isinstance(ref, FuturesRef):
            if as_of is None:
                raise FigiResolutionError("as_of is required to resolve a FuturesRef")
            return self._resolve_future(ref, as_of)
        listed = _listed_ref(ref)
        if listed not in self._bimap:
            self._bimap.update(self._resolve_listed({listed}, transport=transport))
        instrument_id = self._bimap[listed]
        self._contract_to_ref[instrument_id] = listed
        return instrument_id

    def resolve_many(
        self,
        refs: set[InstrumentRef | str],
        *,
        transport: OpenFigiTransport | None = None,
    ) -> dict[InstrumentRef | str, InstrumentId]:
        """Resolve refs to an InstrumentRef→InstrumentId bimap atomically."""
        if not refs:
            return {}
        if any(isinstance(ref, FuturesRef) for ref in refs):
            raise FigiResolutionError("resolve_many cannot resolve FuturesRef without as_of")
        originals = {_listed_ref(ref): ref for ref in refs}
        missing = set(originals) - set(self._bimap)
        if missing:
            self._bimap.update(self._resolve_listed(missing, transport=transport))
        resolved = {original: self._bimap[listed] for listed, original in originals.items()}
        for original, instrument_id in resolved.items():
            self._contract_to_ref[instrument_id] = _listed_ref(original)
        return resolved

    def ref_for(self, instrument_id: InstrumentId) -> InstrumentRef:
        """Fold a resolved dated/listed contract back to its canonical InstrumentRef."""
        try:
            return self._contract_to_ref[instrument_id]
        except KeyError:
            raise FigiResolutionError(
                f"InstrumentId {instrument_id!r} has no resolved InstrumentRef inverse"
            ) from None

    def _resolve_future(self, ref: FuturesRef, as_of: date) -> InstrumentId:
        if self._futures_calendar is None or self._futures_contract_resolver is None:
            raise FigiResolutionError("FuturesRef resolution requires injected futures adapters")
        contract = self._futures_calendar(ref, as_of)
        if contract.exchange not in _bloomberg_exch_to_mic:
            raise FigiResolutionError(
                f"Futures contract {contract.symbol!r}: unknown exchange code {contract.exchange!r}"
            )
        instrument_id = self._futures_contract_resolver(contract)
        self._contract_to_ref[instrument_id] = ref
        return instrument_id

    def _resolve_listed(
        self,
        refs: set[ListedRef],
        *,
        transport: OpenFigiTransport | None,
    ) -> dict[ListedRef, InstrumentId]:
        client = _OpenFigiClient(transport=transport) if transport else _OpenFigiClient.from_env()

        ordered = sorted(refs)
        jobs = [{"idType": "FIGI", "idValue": ref.figi} for ref in ordered]
        responses = client.map(jobs)

        bimap: dict[ListedRef, InstrumentId] = {}
        errors: list[str] = []
        for ref, response in zip(ordered, responses, strict=True):
            try:
                metadata = _extract_metadata(ref.figi, response)
                instrument_id = _to_instrument_id(metadata)
                bimap[ref] = instrument_id
            except FigiResolutionError as e:
                errors.append(str(e))

        if errors:
            raise FigiResolutionError(
                "FIGI resolution failed closed — "
                + "; ".join(errors)
                + ". Refusing to start the book with unidentified instruments."
            )

        return bimap


def _listed_ref(ref: InstrumentRef | str) -> ListedRef:
    if isinstance(ref, ListedRef):
        return ref
    if isinstance(ref, str):
        return ListedRef(ref)
    raise FigiResolutionError(f"unsupported InstrumentRef variant {type(ref).__name__}")


def _extract_metadata(figi: str, response: dict) -> _FigiMetadata:
    """Extract the exchange-level metadata for *figi* from an OpenFIGI response."""
    data = response.get("data", [])
    if not data:
        raise FigiResolutionError(f"FIGI {figi!r}: no data returned from OpenFIGI")

    exchange_rows = [
        row for row in data
        if row.get("figi") == figi and row.get("securityType")
    ]
    if not exchange_rows:
        raise FigiResolutionError(
            f"FIGI {figi!r}: no exchange-level record found "
            f"(got {len(data)} row(s) but none matched the FIGI with a securityType)"
        )
    if len(exchange_rows) > 1:
        raise FigiResolutionError(
            f"FIGI {figi!r}: ambiguous — {len(exchange_rows)} exchange-level records"
        )

    row = exchange_rows[0]
    ticker = row.get("ticker", "") or ""
    if not ticker:
        raise FigiResolutionError(
            f"FIGI {figi!r}: missing ticker in OpenFIGI response"
        )

    return _FigiMetadata(
        figi=figi,
        ticker=ticker,
        exch_code=row.get("exchCode", "") or "",
    )


def _to_instrument_id(metadata: _FigiMetadata) -> InstrumentId:
    """Convert FIGI metadata to a Nautilus InstrumentId via the exchange table."""
    exch_code = metadata.exch_code
    venue = _bloomberg_exch_to_mic.get(exch_code)
    if venue is None:
        raise FigiResolutionError(
            f"FIGI {metadata.figi!r}: unknown exchange code {exch_code!r} "
            f"for ticker {metadata.ticker!r}; "
            f"add a mapping to the bounded exchange-code table"
        )
    return InstrumentId.from_str(f"{metadata.ticker}.{venue}")
