"""Resolve a data-provider ticker to its canonical FIGI via OpenFIGI.

The FIGI (OpenFIGI / Bloomberg Global Identifier) is the cross-boundary
instrument identity an Execution Bundle carries (root ADR-0002): the provider
ticker stays RD-internal for data fetch only, and `aerd export` resolves it to a
FIGI once, at export, and bakes it into the bundle's ``DataContract``.

Resolution is **fail-closed** (Aegis 'no tolerance'): an unmapped or ambiguous
ticker refuses the export rather than guessing an instrument identity.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence

from aegis_runtime.currency import major_currency

from research.aegis_research.configuration.schema import SymbolSpec

OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
# OpenFIGI caps an unauthenticated mapping request at 10 jobs (100 with a key);
# the conservative bound works in either mode.
_MAX_JOBS_PER_REQUEST = 10
_API_KEY_ENV = "OPENFIGI_API_KEY"

# A transport turns one chunk of mapping jobs into OpenFIGI's aligned response list.
Transport = Callable[..., list[dict]]


class FigiResolutionError(ValueError):
    """A ticker could not be resolved to exactly one FIGI."""


class OpenFigiClient:
    """Thin OpenFIGI ``/v3/mapping`` adapter: batches jobs and sets auth headers.

    Hides the HTTP transport, the per-request job cap, and the API-key header
    behind a single ``map`` call returning OpenFIGI's response list aligned 1:1
    with the jobs supplied (across however many requests the cap forces).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: Transport | None = None,
        max_jobs_per_request: int = _MAX_JOBS_PER_REQUEST,
    ) -> None:
        self._api_key = api_key
        self._transport = transport if transport is not None else _post_json
        self._max_jobs_per_request = max_jobs_per_request

    @classmethod
    def from_env(cls) -> OpenFigiClient:
        return cls(api_key=os.environ.get(_API_KEY_ENV))

    def map(self, jobs: list[dict]) -> list[dict]:
        headers = self._headers()
        responses: list[dict] = []
        for start in range(0, len(jobs), self._max_jobs_per_request):
            chunk = jobs[start : start + self._max_jobs_per_request]
            responses.extend(self._transport(headers=headers, jobs=chunk))
        return responses

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-OPENFIGI-APIKEY"] = self._api_key
        return headers


def resolve_symbol_figis(symbols: Sequence[SymbolSpec]) -> dict[str, str]:
    """Resolve ticker -> FIGI against the live OpenFIGI service (env API key)."""
    return resolve_figis(symbols, client=OpenFigiClient.from_env())


def resolve_figis(
    symbols: Sequence[SymbolSpec],
    *,
    client: OpenFigiClient,
) -> dict[str, str]:
    """Map each symbol's provider ticker to its unique exchange-level FIGI.

    Returns a ticker -> FIGI map in declared order. Fail-closed: an unmapped or
    ambiguous ticker raises :class:`FigiResolutionError`.
    """
    jobs = [_mapping_job(spec) for spec in symbols]
    responses = client.map(jobs)
    resolved: dict[str, str] = {}
    unmapped: list[str] = []
    ambiguous: list[str] = []
    for spec, response in zip(symbols, responses, strict=True):
        figis = _figis_of(response)
        if not figis:
            unmapped.append(spec.ticker)
        elif len(figis) > 1:
            ambiguous.append(spec.ticker)
        else:
            resolved[spec.ticker] = next(iter(figis))
    _fail_closed(unmapped=unmapped, ambiguous=ambiguous, collisions=_collisions(resolved))
    return resolved


def _collisions(resolved: dict[str, str]) -> list[str]:
    by_figi: dict[str, list[str]] = {}
    for ticker, figi in resolved.items():
        by_figi.setdefault(figi, []).append(ticker)
    return sorted(figi for figi, tickers in by_figi.items() if len(tickers) > 1)


def _fail_closed(*, unmapped: list[str], ambiguous: list[str], collisions: list[str]) -> None:
    problems: list[str] = []
    if unmapped:
        problems.append(f"no FIGI for {', '.join(sorted(unmapped))}")
    if ambiguous:
        problems.append(
            f"multiple exchange-level FIGIs for {', '.join(sorted(ambiguous))} "
            "(disambiguate the listing)"
        )
    if collisions:
        problems.append(
            f"distinct tickers share FIGI {', '.join(collisions)} "
            "(would collapse two instruments)"
        )
    if problems:
        raise FigiResolutionError(
            "OpenFIGI resolution failed closed — "
            + "; ".join(problems)
            + ". Refusing to export with an unidentified instrument."
        )


def _mapping_job(spec: SymbolSpec) -> dict[str, str]:
    return {
        "idType": "TICKER",
        "idValue": spec.ticker,
        "currency": major_currency(spec.ccy),
    }


def _figis_of(response: dict) -> set[str]:
    return {row["figi"] for row in response.get("data", []) if row.get("figi")}


def _post_json(*, headers: dict[str, str], jobs: list[dict]) -> list[dict]:
    import requests

    response = requests.post(OPENFIGI_MAPPING_URL, headers=headers, json=jobs, timeout=30)
    response.raise_for_status()
    return response.json()
