"""Dynamic, content-addressed CATB holdings with Artemis enrichment."""

from __future__ import annotations

import hashlib
import json
import math
import re
import warnings
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import requests

HANETF_HOLDINGS_URL = (
    "https://hanetf.com/wp-content/assets/upload/"
    "Holdings-CATB-IE000UWJUW87-all-all.xlsx"
)
_XML_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class CatbPortfolioError(ValueError):
    """CATB holdings could not produce a trustworthy portfolio observation."""


class CatbPortfolioSchemaError(CatbPortfolioError):
    """The workbook, cache schema, or fund identity is unsupported."""


class CatbPortfolioPositionError(CatbPortfolioError):
    """A holding contains an invalid or incomplete value."""


class CatbPortfolioWeightError(CatbPortfolioError):
    """Portfolio weights do not reconcile."""


@dataclass(frozen=True)
class CatbPortfolioMetrics:
    available_at: datetime
    insurance_spread: float
    expected_loss: float
    net_carry: float
    risk_multiple: float
    coverage: float


def _cell_value(cell: ElementTree.Element) -> str | None:
    if cell is None:
        raise CatbPortfolioSchemaError("HANetf workbook contains a missing cell")
    inline = cell.find(f"{_XML_NAMESPACE}is/{_XML_NAMESPACE}t")
    if inline is not None:
        return inline.text
    value = cell.find(f"{_XML_NAMESPACE}v")
    return None if value is None else value.text


def parse_hanetf_workbook(content: bytes) -> tuple[str, list[dict]]:
    """Normalize the CATB worksheet without requiring an Excel runtime."""
    try:
        with zipfile.ZipFile(BytesIO(content)) as workbook:
            root = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        raise CatbPortfolioSchemaError("invalid HANetf CATB workbook") from error

    rows = root.findall(f".//{_XML_NAMESPACE}row")
    if not rows:
        raise CatbPortfolioSchemaError("HANetf CATB workbook has no rows")
    title = _cell_value(rows[0].find(f"{_XML_NAMESPACE}c"))
    title_match = re.fullmatch(
        r"KRC Cat Bond UCITS ETF \(IE000UWJUW87\) As Of:(\d{2}-\d{2}-\d{4})",
        title or "",
    )
    if title_match is None:
        raise CatbPortfolioSchemaError("HANetf workbook is not the CATB fund")
    as_of = datetime.strptime(title_match.group(1), "%d-%m-%Y").date().isoformat()

    holdings = []
    try:
        for row in rows[5:]:
            values = {}
            for cell in row.findall(f"{_XML_NAMESPACE}c"):
                coordinate = re.fullmatch(r"([A-Z]+)\d+", cell.attrib["r"])
                if coordinate is None:
                    raise CatbPortfolioSchemaError("HANetf workbook has an invalid coordinate")
                values[coordinate.group(1)] = _cell_value(cell)
            if not values.get("A"):
                continue
            description = values["A"]
            rate = re.search(r"\s(\d+(?:\.\d+)?)%\s\d{2}/\d{2}/\d{4}$", description)
            maturity = re.search(r"(\d{2}/\d{2}/\d{4})$", description)
            holdings.append(
                {
                    "description": description,
                    "isin": None if values.get("H") == "NONE" else values.get("H"),
                    "weight": float(values["I"]) * 100.0,
                    "market_value": float(values["C"]),
                    "insurance_spread": float(rate.group(1)) if rate else None,
                    "maturity": maturity.group(1) if maturity else None,
                }
            )
    except (KeyError, TypeError, ValueError) as error:
        raise CatbPortfolioPositionError("HANetf workbook contains an invalid holding") from error
    return as_of, holdings


def _enrich(holdings: list[dict], enrichment_path: Path) -> list[dict]:
    matches = json.loads(enrichment_path.read_text())
    if matches.get("schema_version") != 1:
        raise CatbPortfolioSchemaError("unsupported CATB enrichment schema")
    by_isin = matches["matches"]
    allowed = {
        "expected_loss",
        "artemis_source",
        "match_basis",
        "available_at",
        "verified_at",
    }
    enriched = []
    for holding in holdings:
        match = by_isin.get(holding["isin"], {})
        unexpected = set(match) - allowed
        if unexpected:
            raise CatbPortfolioSchemaError(
                f"CATB enrichment contains forbidden fields: {sorted(unexpected)}"
            )
        enriched.append(holding | match)
    return enriched


def refresh_holdings_cache(
    cache_dir: Path,
    *,
    retrieved_at: datetime | None = None,
) -> Path:
    """Fetch current holdings and retain the first observed copy of each distinct workbook."""
    response = requests.get(
        HANETF_HOLDINGS_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            "Referer": "https://hanetf.com/fund/catb-krc-cat-bond-ucits-etf/",
            "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
        },
        timeout=30,
    )
    response.raise_for_status()
    content_hash = hashlib.sha256(response.content).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"catb-holdings-{content_hash[:16]}.json"
    as_of, holdings = parse_hanetf_workbook(response.content)
    holdings_hash = hashlib.sha256(
        json.dumps(holdings, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    observed_at = (retrieved_at or datetime.now(UTC)).isoformat()
    if path.exists():
        cached = json.loads(path.read_text())
        if cached.get("schema_version") == 2:
            return path
        observed_at = cached.get("retrieved_at", observed_at)
    payload = {
        "schema_version": 2,
        "as_of": as_of,
        "retrieved_at": observed_at,
        "fund_isin": "IE000UWJUW87",
        "source_url": HANETF_HOLDINGS_URL,
        "source_sha256": content_hash,
        "holdings_sha256": holdings_hash,
        "holdings": holdings,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def load_portfolio_metrics(
    path: Path,
    enrichment_path: Path,
    *,
    collateral_yield: float,
    fund_fee: float,
) -> CatbPortfolioMetrics:
    """Aggregate only explicitly matched CATB tranches; never impute unmatched risk."""
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 2 or payload.get("fund_isin") != "IE000UWJUW87":
        raise CatbPortfolioSchemaError("unsupported CATB holdings cache")
    try:
        available_at = datetime.fromisoformat(payload["retrieved_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise CatbPortfolioSchemaError("invalid CATB retrieval timestamp") from error

    holdings = payload.get("holdings")
    if not isinstance(holdings, list) or not holdings:
        raise CatbPortfolioSchemaError("CATB cache has no holdings")
    holdings_hash = hashlib.sha256(
        json.dumps(holdings, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if holdings_hash != payload.get("holdings_sha256"):
        raise CatbPortfolioSchemaError("CATB cached holdings failed integrity verification")
    holdings = _enrich(holdings, enrichment_path)
    enrichment_times = [
        datetime.fromisoformat(holding["available_at"])
        for holding in holdings
        if holding.get("expected_loss") is not None
    ]
    if enrichment_times:
        available_at = max(available_at, max(enrichment_times))
    identifiers = [holding["isin"] for holding in holdings if holding["isin"] is not None]
    if len(identifiers) != len(set(identifiers)):
        raise CatbPortfolioPositionError("CATB cache contains duplicate ISINs")
    for holding in holdings:
        values = [holding["weight"], holding["market_value"]]
        values.extend(
            value
            for value in (holding["insurance_spread"], holding.get("expected_loss"))
            if value is not None
        )
        if any(not math.isfinite(float(value)) or float(value) < 0.0 for value in values):
            raise CatbPortfolioPositionError("CATB holding values must be finite and non-negative")
        if holding.get("expected_loss") is not None and holding.get("artemis_source") is None:
            raise CatbPortfolioPositionError("matched CATB holding has no Artemis source")

    total_weight = sum(float(holding["weight"]) for holding in holdings)
    if not math.isclose(total_weight, 100.0, abs_tol=0.1):
        raise CatbPortfolioWeightError("CATB holding weights do not reconcile to 100%")
    positions = [holding for holding in holdings if holding.get("expected_loss") is not None]
    eligible_weight = sum(
        float(holding["weight"])
        for holding in holdings
        if holding.get("eligible_cat_bond", holding["insurance_spread"] is not None)
    )
    matched_weight = sum(float(position["weight"]) for position in positions)
    if eligible_weight <= 0.0 or matched_weight <= 0.0:
        raise CatbPortfolioWeightError("CATB matched weights must be positive")

    insurance_spread = sum(
        float(position["weight"]) * float(position["insurance_spread"])
        for position in positions
    ) / matched_weight
    expected_loss = sum(
        float(position["weight"]) * float(position["expected_loss"])
        for position in positions
    ) / matched_weight
    if expected_loss <= 0.0:
        raise CatbPortfolioPositionError("CATB matched expected loss must be positive")
    return CatbPortfolioMetrics(
        available_at=available_at,
        insurance_spread=insurance_spread,
        expected_loss=expected_loss,
        net_carry=collateral_yield + insurance_spread - expected_loss - fund_fee,
        risk_multiple=insurance_spread / expected_loss,
        coverage=matched_weight / eligible_weight,
    )


def current_and_cached_metrics(
    cache_dir: Path,
    enrichment_path: Path,
    *,
    history_dir: Path | None = None,
    collateral_yield: float,
    fund_fee: float,
) -> list[CatbPortfolioMetrics]:
    """Refresh when online, then return the full causal cache history."""
    try:
        refresh_holdings_cache(cache_dir)
    except requests.RequestException as error:
        warnings.warn(f"CATB holdings refresh failed; using cache: {error}", stacklevel=2)
    paths = sorted(cache_dir.glob("catb-holdings-*.json"))
    if history_dir is not None:
        paths.extend(sorted(history_dir.glob("catb-holdings-*.json")))
    if not paths:
        raise CatbPortfolioSchemaError("CATB holdings cache is empty")
    metrics = [
        load_portfolio_metrics(
            path,
            enrichment_path,
            collateral_yield=collateral_yield,
            fund_fee=fund_fee,
        )
        for path in paths
    ]
    return sorted(metrics, key=lambda observation: observation.available_at)
