"""Federal Reserve GSW fitted nominal Treasury curve snapshots."""

from __future__ import annotations

import hashlib
import io
import math
import os
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

GSW_NOMINAL_CURVE_URL = "https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv"

Fetch = Callable[[], bytes]


class GswCurveDataError(ValueError):
    """A GSW response or cached snapshot cannot satisfy the curve contract."""


@dataclass(frozen=True)
class GswCurveProvenance:
    sha256: str
    first_date: pd.Timestamp
    last_date: pd.Timestamp
    cache_path: Path


@dataclass(frozen=True)
class GswZeroYield:
    curve_date: pd.Timestamp
    zero_yield_pct: float


@dataclass(frozen=True)
class GswNominalCurveSnapshot:
    curve: pd.DataFrame
    provenance: GswCurveProvenance

    def zero_yield(self, as_of_date: str | pd.Timestamp, modified_duration: float) -> GswZeroYield:
        """Return the fitted continuously compounded yield without using a future curve."""
        date = _calendar_timestamp(as_of_date)
        eligible = self.curve.loc[self.curve.index <= date]
        if eligible.empty:
            raise GswCurveDataError(f"GSW curve has no observation on or before {date.date()}")
        if not math.isfinite(modified_duration) or modified_duration <= 0.0:
            raise GswCurveDataError("modified duration must be finite and positive")
        curve_date = pd.Timestamp(eligible.index[-1])
        parameters = eligible.iloc[-1]
        return GswZeroYield(
            curve_date=curve_date,
            zero_yield_pct=_svensson_zero_yield(parameters, modified_duration),
        )


def _http_fetch() -> bytes:
    response = requests.get(GSW_NOMINAL_CURVE_URL, timeout=30)
    response.raise_for_status()
    return response.content


@dataclass(frozen=True)
class GswNominalCurveSource:
    """Own live retrieval, validation, immutable caching, fallback, and provenance."""

    cache_dir: Path
    fetch: Fetch = _http_fetch

    def load(self) -> GswNominalCurveSnapshot:
        try:
            contents = self.fetch()
        except (OSError, requests.RequestException):
            return self._load_cached()
        snapshot = _snapshot(contents, self.cache_dir)
        _write_snapshot(snapshot.provenance.cache_path, contents)
        return snapshot

    def _load_cached(self) -> GswNominalCurveSnapshot:
        cached = [
            _snapshot(path.read_bytes(), self.cache_dir, expected_path=path)
            for path in self.cache_dir.glob("gsw-nominal-*.csv")
        ]
        if not cached:
            raise GswCurveDataError("GSW curve is unavailable and no cached snapshot exists")
        return max(
            cached,
            key=lambda snapshot: (
                snapshot.provenance.last_date,
                snapshot.provenance.sha256,
            ),
        )


def _snapshot(
    contents: bytes,
    cache_dir: Path,
    *,
    expected_path: Path | None = None,
) -> GswNominalCurveSnapshot:
    digest = hashlib.sha256(contents).hexdigest()
    path = cache_dir / f"gsw-nominal-{digest[:16]}.csv"
    if expected_path is not None and expected_path != path:
        raise GswCurveDataError(f"cached GSW snapshot does not match its identity: {expected_path}")
    curve = _parse_curve(contents)
    provenance = GswCurveProvenance(
        sha256=digest,
        first_date=pd.Timestamp(curve.index[0]),
        last_date=pd.Timestamp(curve.index[-1]),
        cache_path=path,
    )
    return GswNominalCurveSnapshot(curve=curve, provenance=provenance)


def _parse_curve(contents: bytes) -> pd.DataFrame:
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise GswCurveDataError("GSW curve is not UTF-8 CSV") from error
    lines = text.splitlines()
    header = next((index for index, line in enumerate(lines) if line.startswith("Date,")), None)
    if header is None:
        raise GswCurveDataError("GSW curve is missing the Date header")
    frame = pd.read_csv(io.StringIO("\n".join(lines[header:])), na_values=["NA", -999.99])
    required = ["Date", "BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2"]
    missing = [column for column in required if column not in frame]
    if missing:
        raise GswCurveDataError(f"GSW curve is missing columns: {missing}")
    frame["Date"] = pd.to_datetime(frame["Date"], errors="raise")
    curve = frame.set_index("Date")[required[1:]].apply(pd.to_numeric, errors="coerce")
    curve = curve[~curve.index.duplicated(keep=False)].sort_index()
    curve = curve.dropna(subset=["BETA0", "BETA1", "BETA2", "TAU1"])
    if curve.empty:
        raise GswCurveDataError("GSW curve has invalid required parameter values")
    return curve


def _svensson_zero_yield(parameters: pd.Series, maturity_years: float) -> float:
    beta0 = float(parameters["BETA0"])
    beta1 = float(parameters["BETA1"])
    beta2 = float(parameters["BETA2"])
    beta3 = float(parameters["BETA3"])
    tau1 = float(parameters["TAU1"])
    tau2 = float(parameters["TAU2"])
    if not math.isfinite(tau1) or tau1 <= 0.0:
        raise GswCurveDataError("GSW curve has invalid TAU1")
    first = _svensson_loading(maturity_years, tau1)
    second = first - math.exp(-maturity_years / tau1)
    third = 0.0
    if beta3 != 0.0:
        if not math.isfinite(tau2) or tau2 <= 0.0:
            raise GswCurveDataError("GSW curve has invalid TAU2")
        third = _svensson_loading(maturity_years, tau2) - math.exp(-maturity_years / tau2)
    yield_pct = beta0 + beta1 * first + beta2 * second + beta3 * third
    if not math.isfinite(yield_pct):
        raise GswCurveDataError("GSW curve produced a non-finite zero yield")
    return yield_pct


def _svensson_loading(maturity_years: float, tau: float) -> float:
    scaled = maturity_years / tau
    return -math.expm1(-scaled) / scaled


def _calendar_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is not None:
        timestamp = timestamp.tz_localize(None)
    return timestamp.normalize()


def _write_snapshot(destination: Path, contents: bytes) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
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
