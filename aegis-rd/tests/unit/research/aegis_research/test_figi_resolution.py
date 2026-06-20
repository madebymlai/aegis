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


def test_mic_drives_miccode_with_bare_symbol() -> None:
    # The provider-agnostic ISO MIC supplies the venue filter; the provider
    # ticker's suffix is stripped to the bare OpenFIGI symbol (OpenFIGI's
    # TICKER type rejects 'IHYU.L').
    symbols = [SymbolSpec(ticker="IHYU.L", ccy="USD", mic="XLON")]
    client = _FakeOpenFigiClient([_hit("BBG0022FR5K6")])

    resolve_figis(symbols, client=client)

    job = client.seen_jobs[0]
    assert job["idType"] == "TICKER"
    assert job["idValue"] == "IHYU"
    assert job["micCode"] == "XLON"
    assert job["currency"] == "USD"


def test_isin_resolves_via_id_isin() -> None:
    # An ISIN is the authoritative, provider-agnostic security id: resolve it
    # through OpenFIGI's ID_ISIN type, ignoring the provider ticker entirely.
    symbols = [SymbolSpec(ticker="IHYU.L", ccy="USD", isin="IE00BF3N7094")]
    client = _FakeOpenFigiClient([_hit("BBG0022FR5K6")])

    resolve_figis(symbols, client=client)

    job = client.seen_jobs[0]
    assert job["idType"] == "ID_ISIN"
    assert job["idValue"] == "IE00BF3N7094"
    # Currency narrows a multi-currency-listed ISIN to the right trading line.
    assert job["currency"] == "USD"


def test_isin_with_mic_narrows_to_venue() -> None:
    symbols = [SymbolSpec(ticker="IHYU.L", ccy="USD", isin="IE00BF3N7094", mic="XLON")]
    client = _FakeOpenFigiClient([_hit("BBG0022FR5K6")])

    resolve_figis(symbols, client=client)

    job = client.seen_jobs[0]
    assert job["idType"] == "ID_ISIN"
    assert job["micCode"] == "XLON"


def test_ticker_without_hints_sends_bare_symbol_and_currency() -> None:
    # No mic/isin: best-effort TICKER + currency, no venue filter (resolves
    # only when the bare symbol + currency is globally unique).
    symbols = [SymbolSpec(ticker="SPY", ccy="USD")]
    client = _FakeOpenFigiClient([_hit("BBG000BDTBL9")])

    resolve_figis(symbols, client=client)

    job = client.seen_jobs[0]
    assert job["idValue"] == "SPY"
    assert job["currency"] == "USD"
    assert "micCode" not in job


def test_quote_currency_is_sent_to_openfigi_verbatim() -> None:
    # GBp (pence) is the literal exchange quote token; OpenFIGI stores LSE
    # pence lines under 'GBp', so the filter must receive it verbatim (sending
    # the ISO major 'GBP' returns no match).
    symbols = [SymbolSpec(ticker="GILI.L", ccy="GBp", mic="XLON")]
    client = _FakeOpenFigiClient([_hit("BBG000PLNQN7")])

    resolve_figis(symbols, client=client)

    assert client.seen_jobs[0]["currency"] == "GBp"


def test_explicit_figi_bypasses_openfigi() -> None:
    # An authoritative figi on the symbol is used verbatim; the ambiguous/
    # unmappable OpenFIGI lookup is skipped entirely (no job is sent).
    symbols = [SymbolSpec(ticker="AIGC.L", ccy="USD", figi="BBG000BLDWV1")]
    client = _FakeOpenFigiClient([])

    resolved = resolve_figis(symbols, client=client)

    assert resolved == {"AIGC.L": "BBG000BLDWV1"}
    assert client.seen_jobs == []


def test_explicit_figi_mixes_with_resolved() -> None:
    # Only the symbols without an explicit figi are sent to OpenFIGI.
    symbols = [
        SymbolSpec(ticker="AIGC.L", ccy="USD", figi="BBG000BLDWV1"),
        SymbolSpec(ticker="IHYU.L", ccy="USD"),
    ]
    client = _FakeOpenFigiClient([_hit("BBG0022FR5K6")])

    resolved = resolve_figis(symbols, client=client)

    assert resolved == {"AIGC.L": "BBG000BLDWV1", "IHYU.L": "BBG0022FR5K6"}
    assert [job["idValue"] for job in client.seen_jobs] == ["IHYU"]


def test_explicit_figi_colliding_with_resolved_fails_closed() -> None:
    symbols = [
        SymbolSpec(ticker="AIGC.L", ccy="USD", figi="BBG0022FR5K6"),
        SymbolSpec(ticker="IHYU.L", ccy="USD"),
    ]
    client = _FakeOpenFigiClient([_hit("BBG0022FR5K6")])

    with pytest.raises(FigiResolutionError, match="BBG0022FR5K6"):
        resolve_figis(symbols, client=client)


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
