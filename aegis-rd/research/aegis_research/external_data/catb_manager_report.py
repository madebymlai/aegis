"""Causal, content-addressed portfolio statistics from CATB manager reports."""

from __future__ import annotations

import hashlib
import html
import json
import re
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests

HANETF_REPORT_SITEMAP = "https://hanetf.com/monthly_reports-sitemap.xml"
_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class CatbManagerReportError(ValueError):
    """A manager report could not produce a trustworthy portfolio observation."""


@dataclass(frozen=True)
class CatbManagerMetrics:
    """Whole-portfolio CATB statistics usable from the report publication time."""

    available_at: datetime
    as_of: str
    average_coupon: float
    average_yield: float
    insurance_spread: float
    expected_loss: float
    weighted_maturity_years: float

    @property
    def loss_adjusted_yield(self) -> float:
        return self.average_yield - self.expected_loss

    @property
    def risk_multiple(self) -> float:
        return self.insurance_spread / self.expected_loss


def _plain_text(content: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", content, flags=re.I | re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", without_scripts)).split())


def _percent(text: str, label: str) -> float:
    match = re.search(rf"{label}\s*(\d+(?:\.\d+)?)%", text, flags=re.I)
    if match is None:
        raise CatbManagerReportError(f"CATB manager report has no {label}")
    return float(match.group(1))


def parse_manager_report(content: str) -> CatbManagerMetrics:
    """Parse the stable manager-statistics labels, not presentation markup."""
    text = _plain_text(content)
    published = re.search(r"Published Date:\s*([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    as_of = re.search(r"Portfolio Statistics\s*As of\s*(\d{2}/\d{2}/\d{4})", text, flags=re.I)
    maturity = re.search(
        r"weighted average maturity was\s*(\d+(?:\.\d+)?)\s*years", text, flags=re.I
    )
    if published is None or as_of is None or maturity is None:
        raise CatbManagerReportError("CATB manager report is missing its dates or maturity")
    metrics = CatbManagerMetrics(
        available_at=datetime.strptime(published.group(1), "%B %d, %Y").replace(tzinfo=UTC),
        as_of=datetime.strptime(as_of.group(1), "%d/%m/%Y").date().isoformat(),
        average_coupon=_percent(text, "Average Coupon"),
        average_yield=_percent(text, "Average Yield"),
        insurance_spread=_percent(text, "Spread"),
        expected_loss=_percent(text, r"Expected Loss \(EL\) %"),
        weighted_maturity_years=float(maturity.group(1)),
    )
    values = (
        metrics.average_coupon,
        metrics.average_yield,
        metrics.insurance_spread,
        metrics.expected_loss,
        metrics.weighted_maturity_years,
    )
    if any(value <= 0.0 for value in values) or metrics.expected_loss >= metrics.average_yield:
        raise CatbManagerReportError("CATB manager report contains implausible statistics")
    return metrics


def discover_report_urls() -> list[str]:
    response = requests.get(HANETF_REPORT_SITEMAP, headers=_REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return sorted(
        set(
            re.findall(
                r"https://hanetf\.com/monthly-reports/cat-bond-quarterly-report-[^<\"]+/?",
                response.text,
            )
        )
    )


def refresh_report_cache(cache_dir: Path) -> list[Path]:
    """Discover reports and retain each distinct source document by content hash."""
    paths = []
    for url in discover_report_urls():
        response = requests.get(url, headers=_REQUEST_HEADERS, timeout=30)
        response.raise_for_status()
        metrics = parse_manager_report(response.text)
        digest = hashlib.sha256(response.content).hexdigest()
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"catb-manager-report-{digest[:16]}.json"
        if not path.exists():
            payload = {
                "schema_version": 1,
                "source_url": url,
                "source_sha256": digest,
                "available_at": metrics.available_at.isoformat(),
                "as_of": metrics.as_of,
                "average_coupon": metrics.average_coupon,
                "average_yield": metrics.average_yield,
                "insurance_spread": metrics.insurance_spread,
                "expected_loss": metrics.expected_loss,
                "weighted_maturity_years": metrics.weighted_maturity_years,
            }
            path.write_text(json.dumps(payload, indent=2) + "\n")
        paths.append(path)
    return paths


def load_cached_report(path: Path) -> CatbManagerMetrics:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise CatbManagerReportError("unsupported CATB manager-report cache")
    try:
        return CatbManagerMetrics(
            available_at=datetime.fromisoformat(payload["available_at"]),
            as_of=str(payload["as_of"]),
            average_coupon=float(payload["average_coupon"]),
            average_yield=float(payload["average_yield"]),
            insurance_spread=float(payload["insurance_spread"]),
            expected_loss=float(payload["expected_loss"]),
            weighted_maturity_years=float(payload["weighted_maturity_years"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CatbManagerReportError("invalid CATB manager-report cache") from error


def current_and_cached_reports(
    cache_dir: Path, *, history_dir: Path | None = None
) -> list[CatbManagerMetrics]:
    """Refresh when online, then return all observations in publication order."""
    try:
        refresh_report_cache(cache_dir)
    except requests.RequestException as error:
        warnings.warn(f"CATB manager-report refresh failed; using cache: {error}", stacklevel=2)
    paths = sorted(cache_dir.glob("catb-manager-report-*.json"))
    if history_dir is not None:
        paths.extend(sorted(history_dir.glob("catb-manager-report-*.json")))
    if not paths:
        raise CatbManagerReportError("CATB manager-report cache is empty")
    reports = [load_cached_report(path) for path in paths]
    return sorted(reports, key=lambda report: report.available_at)
