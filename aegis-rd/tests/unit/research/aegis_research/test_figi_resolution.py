from __future__ import annotations

import pytest

from research.aegis_research.configuration.schema import SymbolSpec
from research.aegis_research.market_data.figi import (
    FigiResolutionError,
    OpenFigiClient,
    resolve_figis,
)


class _FakeOpenFigiClient:
    """Records the jobs it is asked to map and replays canned responses."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = responses
        self.seen_jobs: list[dict] = []

    def map(self, jobs: list[dict]) -> list[dict]:
        self.seen_jobs = list(jobs)
        return self._responses


def _hit(figi: str) -> dict:
    return {"data": [{"figi": figi, "exchCode": "US"}]}


def test_resolves_each_ticker_to_its_unique_exchange_level_figi() -> None:
    symbols = [SymbolSpec(ticker="SPY", ccy="USD"), SymbolSpec(ticker="IWM", ccy="USD")]
    client = _FakeOpenFigiClient([_hit("BBG000BDTBL9"), _hit("BBG000B9XB24")])

    resolved = resolve_figis(symbols, client=client)

    assert resolved == {"SPY": "BBG000BDTBL9", "IWM": "BBG000B9XB24"}


def test_lse_suffix_stripped_and_mic_sent() -> None:
    # OpenFIGI's TICKER type rejects the yfinance venue suffix ('IHYU.L' -> no
    # match); the resolver must send the bare symbol + the venue's micCode.
    symbols = [SymbolSpec(ticker="IHYU.L", ccy="USD")]
    client = _FakeOpenFigiClient([_hit("BBG0022FR5K6")])

    resolve_figis(symbols, client=client)

    job = client.seen_jobs[0]
    assert job["idValue"] == "IHYU"
    assert job["micCode"] == "XLON"


def test_xetra_suffix_maps_to_xetr_mic() -> None:
    symbols = [SymbolSpec(ticker="VOOL.DE", ccy="EUR")]
    client = _FakeOpenFigiClient([_hit("BBG003Q292W1")])

    resolve_figis(symbols, client=client)

    job = client.seen_jobs[0]
    assert job["idValue"] == "VOOL"
    assert job["micCode"] == "XETR"


def test_unknown_exchange_suffix_fails_closed() -> None:
    # Fail closed rather than guess a venue for an unmapped suffix.
    symbols = [SymbolSpec(ticker="FOO.XX", ccy="USD")]
    client = _FakeOpenFigiClient([_hit("BBG000000001")])

    with pytest.raises(FigiResolutionError, match="XX"):
        resolve_figis(symbols, client=client)


def test_suffixless_ticker_sent_without_mic() -> None:
    # A bare (US-style) ticker carries no venue suffix: send it as-is.
    symbols = [SymbolSpec(ticker="SPY", ccy="USD")]
    client = _FakeOpenFigiClient([_hit("BBG000BDTBL9")])

    resolve_figis(symbols, client=client)

    job = client.seen_jobs[0]
    assert job["idValue"] == "SPY"
    assert "micCode" not in job


def test_quote_currency_is_sent_to_openfigi_verbatim() -> None:
    # GBp (pence) is the literal exchange quote token; OpenFIGI stores LSE
    # pence lines under 'GBp', so the filter must receive it verbatim (sending
    # the ISO major 'GBP' returns no match).
    symbols = [SymbolSpec(ticker="GILI.L", ccy="GBp")]
    client = _FakeOpenFigiClient([_hit("BBG000PLNQN7")])

    resolve_figis(symbols, client=client)

    assert client.seen_jobs[0]["currency"] == "GBp"


def test_unmapped_ticker_fails_closed() -> None:
    symbols = [SymbolSpec(ticker="SPY", ccy="USD"), SymbolSpec(ticker="NOPE", ccy="USD")]
    client = _FakeOpenFigiClient([_hit("BBG000BDTBL9"), {"warning": "No identifier found."}])

    with pytest.raises(FigiResolutionError, match="NOPE"):
        resolve_figis(symbols, client=client)


def test_ambiguous_ticker_fails_closed() -> None:
    ambiguous = {
        "data": [
            {"figi": "BBG000B9XRY4", "exchCode": "UN"},
            {"figi": "BBG000BPHFS9", "exchCode": "LN"},
        ]
    }
    symbols = [SymbolSpec(ticker="AAPL", ccy="USD")]
    client = _FakeOpenFigiClient([ambiguous])

    with pytest.raises(FigiResolutionError, match="AAPL"):
        resolve_figis(symbols, client=client)


def test_two_tickers_resolving_to_one_figi_fails_closed() -> None:
    symbols = [SymbolSpec(ticker="SPY", ccy="USD"), SymbolSpec(ticker="SPY2", ccy="USD")]
    client = _FakeOpenFigiClient([_hit("BBG000BDTBL9"), _hit("BBG000BDTBL9")])

    with pytest.raises(FigiResolutionError, match="BBG000BDTBL9"):
        resolve_figis(symbols, client=client)


class _RecordingTransport:
    """Stands in for the HTTP POST; echoes one data hit per job in the chunk."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict, list[dict]]] = []

    def __call__(self, *, headers: dict, jobs: list[dict]) -> list[dict]:
        self.calls.append((headers, jobs))
        return [_hit(f"FIGI-{job['idValue']}") for job in jobs]


def test_client_batches_into_chunks_of_ten_and_concatenates_in_order() -> None:
    transport = _RecordingTransport()
    client = OpenFigiClient(transport=transport)
    jobs = [{"idType": "TICKER", "idValue": f"T{i}", "currency": "USD"} for i in range(23)]

    responses = client.map(jobs)

    assert [len(jobs) for _, jobs in transport.calls] == [10, 10, 3]
    assert [r["data"][0]["figi"] for r in responses] == [f"FIGI-T{i}" for i in range(23)]


def test_client_sends_api_key_header_when_configured() -> None:
    transport = _RecordingTransport()
    client = OpenFigiClient(api_key="secret-key", transport=transport)

    client.map([{"idType": "TICKER", "idValue": "SPY", "currency": "USD"}])

    headers, _ = transport.calls[0]
    assert headers["X-OPENFIGI-APIKEY"] == "secret-key"


def test_client_omits_api_key_header_when_absent() -> None:
    transport = _RecordingTransport()
    client = OpenFigiClient(transport=transport)

    client.map([{"idType": "TICKER", "idValue": "SPY", "currency": "USD"}])

    headers, _ = transport.calls[0]
    assert "X-OPENFIGI-APIKEY" not in headers
