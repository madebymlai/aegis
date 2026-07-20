"""Curated same-session UCITS candidates for the ETF peer-reversal prototype."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UcitsCandidate:
    """One exact exchange line, not a provider-ambiguous ticker."""

    ticker: str
    instrument_id: str
    family: str
    ucits_evidence_url: str
    benchmark: bool = False


# All lines are London Stock Exchange USD listings of Ireland-domiciled UCITS ETFs.
# A family contains different funds/index constructions, never another currency line
# or share class of the same fund. CSPX is residualization input, not a trade candidate.
UCITS_UNIVERSE = (
    UcitsCandidate(
        "CSPX",
        "CSPX.LSEETF",
        "broad_us_equity",
        "https://www.ishares.com/uk/individual/en/products/253743/",
        benchmark=True,
    ),
    UcitsCandidate(
        "IUIT",
        "IUIT.LSEETF",
        "us_technology",
        "https://www.ishares.com/uk/individual/en/products/280510/",
    ),
    UcitsCandidate(
        "SXLK",
        "SXLK.LSEETF",
        "us_technology",
        "https://www.ssga.com/uk/en_gb/intermediary/etfs/state-street-spdr-sp-us-technology-select-sector-ucits-etf-acc-zpdt-gy",
    ),
    UcitsCandidate(
        "XUTC",
        "XUTC.LSEETF",
        "us_technology",
        "https://etf.dws.com/download/asset/b3cc4fb7-fcdb-4adc-87cf-f945a5f190aa",
    ),
    UcitsCandidate(
        "IUHC",
        "IUHC.LSEETF",
        "us_health_care",
        "https://www.ishares.com/uk/individual/en/products/280507/",
    ),
    UcitsCandidate(
        "SXLV",
        "SXLV.LSEETF",
        "us_health_care",
        "https://www.ssga.com/uk/en_gb/intermediary/etfs/state-street-spdr-sp-us-health-care-select-sector-ucits-etf-acc-zpdh-gy",
    ),
    UcitsCandidate(
        "XUHC",
        "XUHC.LSEETF",
        "us_health_care",
        "https://etf.dws.com/en-gb/AssetDownload/Index/6ddcc07e-5af6-4d6e-85bd-186c53ecc5e2/Factsheet.pdf",
    ),
    UcitsCandidate(
        "IUFS",
        "IUFS.LSEETF",
        "us_financials",
        "https://www.ishares.com/uk/individual/en/products/280523/",
    ),
    UcitsCandidate(
        "SXLF",
        "SXLF.LSEETF",
        "us_financials",
        "https://www.ssga.com/uk/en_gb/intermediary/etfs/state-street-spdr-sp-us-financials-select-sector-ucits-etf-acc-zpdf-gy",
    ),
    UcitsCandidate(
        "XUFN",
        "XUFN.LSEETF",
        "us_financials",
        "https://etf.dws.com/download/asset/a59cce0b-b560-48fa-b97d-037114e29350",
    ),
)

BENCHMARK = next(
    candidate.ticker for candidate in UCITS_UNIVERSE if candidate.benchmark
)
