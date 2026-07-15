"""Validated, content-addressed ECB USD-to-EUR daily conversion history."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import warnings
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
import requests

_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"


class EcbFxError(RuntimeError):
    pass


class FxClient(Protocol):
    def usd_per_eur(self, start: date, end: date) -> pd.Series: ...


@dataclass(frozen=True)
class EcbClient:
    timeout_seconds: int = 30

    def usd_per_eur(self, start: date, end: date) -> pd.Series:
        response = requests.get(
            _URL,
            params={
                "startPeriod": start.isoformat(),
                "endPeriod": end.isoformat(),
                "format": "csvdata",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        frame = pd.read_csv(io.StringIO(response.text))
        if not {"TIME_PERIOD", "OBS_VALUE"}.issubset(frame.columns):
            raise EcbFxError("ECB FX response is missing TIME_PERIOD or OBS_VALUE")
        series = pd.Series(
            frame["OBS_VALUE"].to_numpy(dtype=float),
            index=pd.to_datetime(frame["TIME_PERIOD"]),
            name="usd_per_eur",
        ).sort_index()
        return series[~series.index.duplicated(keep="last")]


@dataclass(frozen=True)
class EcbFxSnapshot:
    eur_per_usd: pd.Series
    retrieved_at: str
    covered_start: str
    covered_end: str


@dataclass(frozen=True)
class EcbUsdEurSource:
    cache_dir: Path
    client: FxClient | None = None

    def refresh(self, start: date, end: date) -> EcbFxSnapshot:
        usd_per_eur = (self.client or EcbClient()).usd_per_eur(start, end)
        if usd_per_eur.empty or (usd_per_eur <= 0.0).any():
            raise EcbFxError("ECB USD/EUR history is empty or non-positive")
        snapshot = EcbFxSnapshot(
            eur_per_usd=(1.0 / usd_per_eur).rename("eur_per_usd"),
            retrieved_at=datetime.now(UTC).isoformat(),
            covered_start=start.isoformat(),
            covered_end=end.isoformat(),
        )
        payload = _payload(snapshot)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        identity = str(payload["snapshot_sha256"])
        destination = self.cache_dir / f"eur-per-usd-{identity[:16]}.json"
        _write_once(destination, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return snapshot

    def latest(self) -> EcbFxSnapshot:
        paths = tuple(self.cache_dir.glob("eur-per-usd-*.json"))
        if not paths:
            raise EcbFxError("ECB FX cache is empty and no live snapshot is available")
        snapshots = tuple(load_snapshot(path) for path in paths)
        return max(snapshots, key=lambda item: (item.covered_end, item.retrieved_at))

    def load(self, start: date, end: date, *, refresh: bool = True) -> EcbFxSnapshot:
        if refresh:
            try:
                return self.refresh(start, end)
            except (requests.RequestException, EcbFxError, ValueError) as error:
                warnings.warn(f"ECB FX refresh failed; using cache: {error}", stacklevel=2)
        snapshot = self.latest()
        if snapshot.covered_start > start.isoformat() or snapshot.covered_end < end.isoformat():
            raise EcbFxError("newest ECB FX cache does not cover the requested range")
        return snapshot


def _payload(snapshot: EcbFxSnapshot) -> dict[str, object]:
    observations = [
        {"date": timestamp.date().isoformat(), "eur_per_usd": float(value)}
        for timestamp, value in snapshot.eur_per_usd.items()
    ]
    identity_payload = {
        "covered_start": snapshot.covered_start,
        "covered_end": snapshot.covered_end,
        "observations": observations,
    }
    identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "snapshot_sha256": identity,
        "retrieved_at": snapshot.retrieved_at,
        "covered_start": snapshot.covered_start,
        "covered_end": snapshot.covered_end,
        "observations": observations,
    }


def load_snapshot(path: Path) -> EcbFxSnapshot:
    payload = json.loads(path.read_text())
    observations = payload.get("observations")
    if payload.get("schema_version") != 1 or not isinstance(observations, list):
        raise EcbFxError("unsupported ECB FX snapshot schema")
    identity_payload = {
        "covered_start": payload.get("covered_start"),
        "covered_end": payload.get("covered_end"),
        "observations": observations,
    }
    identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if identity != payload.get("snapshot_sha256") or identity[:16] not in path.name:
        raise EcbFxError("ECB FX snapshot content does not match its identity")
    series = pd.Series(
        [float(item["eur_per_usd"]) for item in observations],
        index=pd.to_datetime([item["date"] for item in observations]),
        name="eur_per_usd",
    )
    if series.empty or not series.index.is_monotonic_increasing or (series <= 0.0).any():
        raise EcbFxError("invalid ECB FX observations")
    return EcbFxSnapshot(
        eur_per_usd=series,
        retrieved_at=str(payload["retrieved_at"]),
        covered_start=str(payload["covered_start"]),
        covered_end=str(payload["covered_end"]),
    )


def _write_once(destination: Path, contents: str) -> None:
    if destination.exists():
        return
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        with suppress(FileExistsError):
            os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
