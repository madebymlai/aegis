"""Dynamic, content-addressed CATB holdings with Artemis enrichment."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import requests

HANETF_HOLDINGS_URL = (
    "https://hanetf.com/wp-content/assets/upload/Holdings-CATB-IE000UWJUW87-all-all.xlsx"
)
_XML_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class CatbPortfolioError(ValueError):
    """CATB holdings could not produce a trustworthy portfolio observation."""


class CatbPortfolioSchemaError(CatbPortfolioError):
    """The workbook, cache schema, or fund identity is unsupported."""


class CatbPortfolioPositionError(CatbPortfolioError):
    """A holding contains an invalid or incomplete value."""


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
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36"
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
