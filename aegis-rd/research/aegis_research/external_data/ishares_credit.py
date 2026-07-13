"""Point-in-time UCITS credit-bucket yield and duration observations from iShares."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

Fetch = Callable[[str], bytes]


class IsharesCreditDataError(ValueError):
    """An issuer response cannot satisfy the credit-bucket data contract."""


@dataclass(frozen=True)
class CreditBucket:
    instrument_id: str
    ucits_product_id: int
    ucits_slug: str
    analytics_product_id: int
    annual_fee_pct: float


BUCKETS = (
    CreditBucket(
        "SDIG.LSEETF",
        258126,
        "ishares-short-duration-corporate-bond-ucits-etf",
        258098,
        0.20,
    ),
    CreditBucket(
        "SDHY.LSEETF",
        258128,
        "ishares-short-duration-high-yield-corporate-bond-ucits-etf",
        258100,
        0.45,
    ),
    CreditBucket(
        "LQDE.LSEETF",
        251832,
        "ishares-corporate-bond-ucits-etf",
        239566,
        0.20,
    ),
    CreditBucket(
        "IHYU.LSEETF",
        251833,
        "ishares-high-yield-corporate-bond-ucits-etf",
        239565,
        0.50,
    ),
)

_USER_AGENT = "Mozilla/5.0 (compatible; aegis-rd credit research)"
_MAX_MONTH_END_LOOKBACK_DAYS = 7


def _http_fetch(url: str) -> bytes:
    response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.content


@dataclass(frozen=True)
class IsharesCreditSource:
    """Own retrieval, immutable caching, validation, and UCITS-weighted aggregation."""

    cache_dir: Path
    fetch: Fetch = _http_fetch

    def load_window(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Return one observation per bucket and completed calendar month in ``[start, end]``."""
        start = _calendar_timestamp(start)
        end = _calendar_timestamp(end)
        last_period = end.to_period("M")
        if end.normalize() < last_period.end_time.normalize():
            last_period -= 1
        periods = pd.period_range(start.to_period("M"), last_period, freq="M")
        observations = []
        for period in periods:
            observations.extend(self._load_month(period.end_time.normalize()))
        if not observations:
            return _empty_panel()
        frame = pd.DataFrame(observations)
        return frame.set_index(["as_of_date", "instrument_id"]).sort_index()

    def _load_month(self, calendar_month_end: pd.Timestamp) -> list[dict]:
        for days_back in range(_MAX_MONTH_END_LOOKBACK_DAYS + 1):
            as_of_date = calendar_month_end - pd.Timedelta(days=days_back)
            payloads = self._payloads_for_date(as_of_date)
            if all(_payload_has_holdings(payload) for payload in payloads.values()):
                return [
                    _aggregate_bucket(bucket, as_of_date, *payloads[bucket.instrument_id])
                    for bucket in BUCKETS
                ]
        raise IsharesCreditDataError(
            f"iShares has no common credit-bucket holdings date near {calendar_month_end.date()}"
        )

    def _payloads_for_date(self, as_of_date: pd.Timestamp) -> dict[str, tuple[dict, dict]]:
        requests_to_make = [
            (bucket, surface)
            for bucket in BUCKETS
            for surface in ("ucits", "analytics")
        ]
        with ThreadPoolExecutor(max_workers=len(requests_to_make)) as executor:
            futures = {
                (bucket.instrument_id, surface): executor.submit(
                    self._load_payload, bucket, surface, as_of_date
                )
                for bucket, surface in requests_to_make
            }
        return {
            bucket.instrument_id: (
                futures[(bucket.instrument_id, "ucits")].result(),
                futures[(bucket.instrument_id, "analytics")].result(),
            )
            for bucket in BUCKETS
        }

    def _load_payload(
        self, bucket: CreditBucket, surface: str, as_of_date: pd.Timestamp
    ) -> dict:
        request_key = _request_key(bucket, surface, as_of_date)
        cached = sorted(self.cache_dir.glob(f"{request_key}-*.json"))
        if cached:
            if len(cached) != 1:
                raise IsharesCreditDataError(f"conflicting cached responses for {request_key}")
            return _load_cached_payload(cached[0])

        url = _source_url(bucket, surface, as_of_date)
        contents = self.fetch(url)
        payload = _decode_payload(contents, request_key)
        _validate_response_identity(bucket, surface, as_of_date, payload)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(contents).hexdigest()
        destination = self.cache_dir / f"{request_key}-{digest[:16]}.json"
        _write_once(destination, contents)
        return payload


def _empty_panel() -> pd.DataFrame:
    frame = pd.DataFrame(
        columns=[
            "as_of_date",
            "instrument_id",
            "available_at",
            "net_ytw",
            "modified_duration",
            "coverage",
        ]
    )
    return frame.set_index(["as_of_date", "instrument_id"])


def _calendar_timestamp(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is not None:
        timestamp = timestamp.tz_localize(None)
    return timestamp.normalize()


def _source_url(bucket: CreditBucket, surface: str, as_of_date: pd.Timestamp) -> str:
    date = as_of_date.strftime("%Y%m%d")
    if surface == "ucits":
        return (
            "https://www.ishares.com/uk/individual/en/products/"
            f"{bucket.ucits_product_id}/{bucket.ucits_slug}/1506575576011.ajax"
            "?tab=all&fileType=json&switchLocale=y&siteEntryPassthrough=true"
            f"&asOfDate={date}"
        )
    if surface == "analytics":
        return (
            "https://www.ishares.com/varnish-api/blk-one01-product-data/product-data/api/v2/"
            "get-product-data?appSubType=ISHARES&appType=PRODUCT_PAGE&component=holdings.all"
            f"&locale=en_US&portfolioId={bucket.analytics_product_id}&targetSite=us-ishares"
            f"&userType=individual&excludeContent=true&asOfDate={date}"
        )
    raise IsharesCreditDataError(f"unknown iShares credit surface: {surface}")


def _request_key(bucket: CreditBucket, surface: str, as_of_date: pd.Timestamp) -> str:
    product_id = (
        bucket.ucits_product_id if surface == "ucits" else bucket.analytics_product_id
    )
    return f"credit-{surface}-{product_id}-{as_of_date:%Y%m%d}"


def _decode_payload(contents: bytes, request_key: str) -> dict:
    try:
        payload = json.loads(contents.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IsharesCreditDataError(f"invalid JSON response for {request_key}") from error
    if not isinstance(payload, dict):
        raise IsharesCreditDataError(f"non-object JSON response for {request_key}")
    return payload


def _load_cached_payload(path: Path) -> dict:
    contents = path.read_bytes()
    expected_hash = path.stem.rsplit("-", maxsplit=1)[-1]
    actual_hash = hashlib.sha256(contents).hexdigest()
    if not actual_hash.startswith(expected_hash):
        raise IsharesCreditDataError(f"cached response does not match its identity: {path}")
    return _decode_payload(contents, path.name)


def _write_once(destination: Path, contents: bytes) -> None:
    if destination.exists():
        return
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        with suppress(FileExistsError):
            os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _payload_has_holdings(payloads: tuple[dict, dict]) -> bool:
    ucits, analytics = payloads
    ucits_rows = ucits.get("aaData")
    try:
        points = _analytics_points(analytics)
    except IsharesCreditDataError:
        return False
    return bool(ucits_rows) and bool(points.get("isin", {}).get("value"))


def _validate_response_identity(
    bucket: CreditBucket,
    surface: str,
    as_of_date: pd.Timestamp,
    payload: dict,
) -> None:
    if surface == "ucits":
        if not isinstance(payload.get("aaData"), list):
            raise IsharesCreditDataError("iShares UCITS response has an unknown schema")
        return
    points = _analytics_points(payload)
    if not points.get("isin", {}).get("value"):
        return
    reported_date = points.get("asOfDate", {}).get("value")
    if str(reported_date) != as_of_date.strftime("%Y%m%d"):
        raise IsharesCreditDataError(
            f"{bucket.instrument_id} analytics returned a different as-of date: {reported_date}"
        )


def _analytics_points(payload: dict) -> dict:
    try:
        return payload["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"][
            "dataPointsByNameMap"
        ]
    except (KeyError, TypeError) as error:
        raise IsharesCreditDataError("iShares analytics response has an unknown schema") from error


def _aggregate_bucket(
    bucket: CreditBucket,
    as_of_date: pd.Timestamp,
    ucits_payload: dict,
    analytics_payload: dict,
) -> dict:
    points = _analytics_points(analytics_payload)
    analytics = _security_analytics(points)
    holdings = _ucits_fixed_income_weights(ucits_payload)
    total_weight = sum(weight for _, weight in holdings)
    matched = [(weight, analytics[isin]) for isin, weight in holdings if isin in analytics]
    matched_weight = sum(weight for weight, _ in matched)
    if total_weight <= 0.0 or matched_weight <= 0.0:
        raise IsharesCreditDataError(
            f"{bucket.instrument_id} has no matchable fixed-income weight on {as_of_date.date()}"
        )
    gross_ytw = sum(weight * values[0] for weight, values in matched) / matched_weight
    duration = sum(weight * values[1] for weight, values in matched) / matched_weight
    return {
        "as_of_date": as_of_date,
        "instrument_id": bucket.instrument_id,
        "available_at": as_of_date + pd.Timedelta(days=1),
        "net_ytw": gross_ytw - bucket.annual_fee_pct,
        "modified_duration": duration,
        "coverage": matched_weight / total_weight,
    }


def _security_analytics(points: dict) -> dict[str, tuple[float, float]]:
    isins = points.get("isin", {}).get("value", [])
    yields = points.get("yieldToWorst", {}).get("value", [])
    durations = points.get("modifiedDuration", {}).get("value", [])
    if not (len(isins) == len(yields) == len(durations)):
        raise IsharesCreditDataError("iShares security analytics columns are not aligned")
    result: dict[str, tuple[float, float]] = {}
    for isin, ytw, duration in zip(isins, yields, durations, strict=True):
        if not isin or ytw is None or duration is None:
            continue
        values = (float(ytw), float(duration))
        if isin in result and result[isin] != values:
            raise IsharesCreditDataError(f"conflicting analytics for ISIN {isin}")
        result[isin] = values
    return result


def _ucits_fixed_income_weights(payload: dict) -> list[tuple[str, float]]:
    rows = payload.get("aaData")
    if not isinstance(rows, list):
        raise IsharesCreditDataError("iShares UCITS response has an unknown schema")
    holdings = []
    for row in rows:
        if not isinstance(row, list) or len(row) <= 9 or row[3] != "Fixed Income":
            continue
        weight = row[5].get("raw") if isinstance(row[5], dict) else None
        if row[9] and weight is not None and float(weight) > 0.0:
            holdings.append((str(row[9]), float(weight)))
    return holdings
