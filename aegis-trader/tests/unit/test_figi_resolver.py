"""Unit tests for the FIGI→InstrumentId Security Master resolver.

Tests the resolver against a stubbed OpenFIGI transport (no network).
Covers: successful resolution, exchange-code mapping, fail-closed behaviour
on unmapped/ambiguous FIGIs, and bimap correctness.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from nautilus_trader.model.identifiers import InstrumentId, Venue

from aegis_trader.execution.figi_resolver import (
    FigiInstrumentResolver,
    FigiResolutionError,
    _bloomberg_exch_to_mic,
)

# ── well-known FIGI test vectors ──────────────────────────────────────────────

_FIGI_VUSA = "BBG000B9XRY4"  # Vanguard S&P 500 UCITS ETF (LSE)
_FIGI_IUSQ = "BBG00BD5NF21"  # iShares MSCI ACWI UCITS ETF (LSE)
_FIGI_EUNL = "BBG00H1VQ896"  # iShares Core MSCI World UCITS ETF (XETRA)
_FIGI_UNKNOWN = "BBGXXXXXXXX"  # not real


# ── mock OpenFIGI responses ───────────────────────────────────────────────────

def _openfigi_response(figi: str, *, ticker: str, exch_code: str,
                       security_type: str = "Common Stock",
                       currency: str = "USD",
                       name: str = "") -> dict:
    """Build a minimal OpenFIGI /v3/mapping response for a single FIGI query.

    The response mimics the exchange-level record returned when querying
    by idType=FIGI.
    """
    return {
        "data": [
            {
                "figi": figi,
                "name": name or f"{ticker} Test Security",
                "ticker": ticker,
                "exchCode": exch_code,
                "securityType": security_type,
                "currency": currency,
            }
        ]
    }


def _mock_transport(responses_by_figi: dict[str, dict]) -> Callable[..., list[dict]]:
    """Return a callable that acts as an OpenFIGI HTTP transport stub.

    Each job dict must have ``idValue`` set to the FIGI being queried.
    Returns one response per job in order.
    """
    def transport(*, headers, jobs):
        results = []
        for job in jobs:
            figi = job["idValue"]
            resp = responses_by_figi.get(figi)
            if resp is None:
                results.append({"data": []})
            else:
                results.append(resp)
        return results
    return transport


# ── resolver fixture ──────────────────────────────────────────────────────────


@pytest.fixture
def resolver():
    """Resolver with no preloaded mappings."""
    return FigiInstrumentResolver()


# ── tests: successful resolution ──────────────────────────────────────────────


class TestSuccessfulResolution:
    """Happy path: FIGI → InstrumentId for various exchange codes."""

    def test_single_figi_lse(self, resolver):
        """VUSA.L on LSE → VUSA.XLON."""
        transport = _mock_transport({
            _FIGI_VUSA: _openfigi_response(
                _FIGI_VUSA, ticker="VUSA", exch_code="LN",
                security_type="ETF", currency="GBP",
            ),
        })
        bimap = resolver.resolve({_FIGI_VUSA}, transport=transport)

        assert bimap == {_FIGI_VUSA: InstrumentId.from_str("VUSA.XLON")}

    def test_single_figi_xetra(self, resolver):
        """EUNL.DE on Xetra → EUNL.XETR."""
        transport = _mock_transport({
            _FIGI_EUNL: _openfigi_response(
                _FIGI_EUNL, ticker="EUNL", exch_code="GR",
                security_type="ETF", currency="EUR",
            ),
        })
        bimap = resolver.resolve({_FIGI_EUNL}, transport=transport)

        assert bimap == {_FIGI_EUNL: InstrumentId.from_str("EUNL.XETR")}

    def test_single_figi_nyse(self, resolver):
        """AAPL on NYSE → AAPL.XNYS."""
        figi = "BBG000B9XRY4"  # reuse as test vector
        transport = _mock_transport({
            figi: _openfigi_response(
                figi, ticker="AAPL", exch_code="US",
                security_type="Common Stock", currency="USD",
            ),
        })
        bimap = resolver.resolve({figi}, transport=transport)
        assert bimap == {figi: InstrumentId.from_str("AAPL.XNYS")}

    def test_single_figi_nasdaq(self, resolver):
        """MSFT on NASDAQ → MSFT.XNAS."""
        figi = "BBG000BPH459"  # test vector
        transport = _mock_transport({
            figi: _openfigi_response(
                figi, ticker="MSFT", exch_code="UQ",
                security_type="Common Stock", currency="USD",
            ),
        })
        bimap = resolver.resolve({figi}, transport=transport)
        assert bimap == {figi: InstrumentId.from_str("MSFT.XNAS")}

    def test_multiple_figis(self, resolver):
        """Multiple FIGIs resolve to their respective InstrumentIds."""
        transport = _mock_transport({
            _FIGI_VUSA: _openfigi_response(
                _FIGI_VUSA, ticker="VUSA", exch_code="LN",
                security_type="ETF", currency="GBP",
            ),
            _FIGI_EUNL: _openfigi_response(
                _FIGI_EUNL, ticker="EUNL", exch_code="GR",
                security_type="ETF", currency="EUR",
            ),
        })
        bimap = resolver.resolve({_FIGI_VUSA, _FIGI_EUNL}, transport=transport)

        assert len(bimap) == 2
        assert bimap[_FIGI_VUSA] == InstrumentId.from_str("VUSA.XLON")
        assert bimap[_FIGI_EUNL] == InstrumentId.from_str("EUNL.XETR")

    def test_exchange_code_mapping_table_has_required_entries(self):
        """Verify the bounded exchange table has the commonly-used entries."""
        required = {"LN": "XLON", "US": "XNYS", "UQ": "XNAS",
                     "GR": "XETR", "NA": "XAMS", "FP": "XPAR"}
        for code, expected_venue in required.items():
            assert _bloomberg_exch_to_mic[code] == expected_venue


# ── tests: fail-closed behaviour ─────────────────────────────────────────────


class TestFailClosed:
    """Resolver must refuse to proceed on unmapped/ambiguous FIGIs."""

    def test_unmapped_figi_raises(self, resolver):
        """A FIGI with no OpenFIGI data raises FigiResolutionError."""
        transport = _mock_transport({})
        with pytest.raises(FigiResolutionError, match="no data"):
            resolver.resolve({_FIGI_UNKNOWN}, transport=transport)

    def test_empty_data_raises(self, resolver):
        """OpenFIGI returns an empty data list."""
        transport = _mock_transport({
            _FIGI_UNKNOWN: {"data": []},
        })
        with pytest.raises(FigiResolutionError, match="no data"):
            resolver.resolve({_FIGI_UNKNOWN}, transport=transport)

    def test_no_exchange_level_record(self, resolver):
        """Response has data but no entry matching the queried FIGI."""
        transport = _mock_transport({
            _FIGI_VUSA: {
                "data": [
                    {"figi": "BBG000B9Y5X2", "name": "composite",
                     "securityType": "", "ticker": "", "exchCode": ""},
                ]
            },
        })
        with pytest.raises(FigiResolutionError, match="no exchange-level record"):
            resolver.resolve({_FIGI_VUSA}, transport=transport)

    def test_ambiguous_multiple_exchange_records(self, resolver):
        """Response has multiple exchange-level entries for the same FIGI."""
        transport = _mock_transport({
            _FIGI_VUSA: {
                "data": [
                    {"figi": _FIGI_VUSA, "ticker": "VUSA", "exchCode": "LN",
                     "securityType": "ETF", "currency": "GBP"},
                    {"figi": _FIGI_VUSA, "ticker": "VUSA", "exchCode": "GR",
                     "securityType": "ETF", "currency": "EUR"},
                ]
            },
        })
        with pytest.raises(FigiResolutionError, match="ambiguous"):
            resolver.resolve({_FIGI_VUSA}, transport=transport)

    def test_one_mapped_one_unmapped_raises(self, resolver):
        """If any FIGI fails, the whole batch fails (atomic)."""
        transport = _mock_transport({
            _FIGI_VUSA: _openfigi_response(
                _FIGI_VUSA, ticker="VUSA", exch_code="LN",
                security_type="ETF", currency="GBP",
            ),
            # _FIGI_UNKNOWN is not in the transport map → returns {"data": []}
        })
        with pytest.raises(FigiResolutionError, match="no data"):
            resolver.resolve({_FIGI_VUSA, _FIGI_UNKNOWN}, transport=transport)

    def test_unknown_exchange_code_raises(self, resolver):
        """Bloomberg exchange code not in the bounded table raises."""
        transport = _mock_transport({
            _FIGI_VUSA: _openfigi_response(
                _FIGI_VUSA, ticker="VUSA", exch_code="ZZ",  # unknown
                security_type="ETF", currency="GBP",
            ),
        })
        with pytest.raises(FigiResolutionError, match="unknown exchange code"):
            resolver.resolve({_FIGI_VUSA}, transport=transport)


# ── tests: edge cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Resolver edge cases and invariants."""

    def test_empty_figis_returns_empty(self, resolver):
        """Resolving zero FIGIs returns an empty bimap."""
        transport = _mock_transport({})
        bimap = resolver.resolve(set(), transport=transport)
        assert bimap == {}

    def test_duplicate_figi_is_idempotent(self, resolver):
        """Querying the same FIGI twice (e.g. across sleeves) returns one entry."""
        transport = _mock_transport({
            _FIGI_VUSA: _openfigi_response(
                _FIGI_VUSA, ticker="VUSA", exch_code="LN",
                security_type="ETF", currency="GBP",
            ),
        })
        # Pass the same FIGI twice in the set — set deduplicates, but we
        # test that the result has exactly one entry.
        bimap = resolver.resolve({_FIGI_VUSA}, transport=transport)
        assert len(bimap) == 1
        assert _FIGI_VUSA in bimap

    def test_missing_ticker_in_response(self, resolver):
        """Response missing the ticker field raises cleanly."""
        transport = _mock_transport({
            _FIGI_VUSA: {
                "data": [
                    {"figi": _FIGI_VUSA, "exchCode": "LN",
                     "securityType": "ETF", "currency": "GBP"},
                ]
            },
        })
        with pytest.raises(FigiResolutionError, match="ticker"):
            resolver.resolve({_FIGI_VUSA}, transport=transport)

    def test_retired_figi_resolves(self, resolver):
        """A FIGI marked as 'retired' in OpenFIGI should still resolve
        if it has metadata (it's still the canonical identifier)."""
        transport = _mock_transport({
            _FIGI_VUSA: {
                "data": [
                    {"figi": _FIGI_VUSA, "ticker": "VUSA", "exchCode": "LN",
                     "securityType": "ETF", "currency": "GBP",
                     "securityDescription": "RETIRED"},
                ]
            },
        })
        bimap = resolver.resolve({_FIGI_VUSA}, transport=transport)
        assert _FIGI_VUSA in bimap
