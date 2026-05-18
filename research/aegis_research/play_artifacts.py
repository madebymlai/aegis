from __future__ import annotations

import fcntl
import json
import math
import os
import shutil
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.aegis_research.cli_support.output import safe_message
from research.aegis_research.market_data.loading import assert_public_metadata_safe

PLAY_ARTIFACT_SCHEMA_VERSION = "play_artifacts.v1"
MAX_LEADERBOARD_ROWS = 10
MAX_FAILURE_SAMPLES = 10


class PlayArtifactError(ValueError):
    pass


class PlayArtifactStore:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.play_dir = self.output_dir / "play"
        self.last_run_dir = self.play_dir / "last-run"
        self.staging_dir = self.play_dir / ".staging"
        self.backup_dir = self.play_dir / "backups"
        self.failed_dir = self.play_dir / "failed"
        self.lock_path = self.play_dir / ".lock"

    def write_success(
        self,
        *,
        play_name: str,
        ranking: Mapping[str, Any],
        variant_records: Sequence[Mapping[str, Any]],
        backup: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        metric = str(ranking["metric"])
        direction = str(ranking["direction"])
        rank_by = str(ranking.get("rank_by", "primary_metric"))
        leaderboard = build_play_leaderboard(
            variant_records,
            metric=metric,
            direction=direction,
            rank_by=rank_by,
        )
        if not leaderboard["rows"]:
            raise PlayArtifactError("all variants failed or ranking metrics are unavailable")

        attempt_id = _attempt_id()
        staging = self.staging_dir / attempt_id
        summary = {
            "schema_version": PLAY_ARTIFACT_SCHEMA_VERSION,
            "attempt_id": attempt_id,
            "play_name": play_name,
            "evidence_type": "exploratory",
            "created_at": _now_iso(),
            "ranking": {"metric": metric, "direction": direction, "rank_by": rank_by},
            "leaderboard_summary": leaderboard["summary"],
            "metadata": dict(metadata or {}),
        }
        _assert_public_payload_safe(summary)
        _assert_public_payload_safe(leaderboard)

        with self._locked():
            staging.mkdir(parents=True, exist_ok=False)
            _write_json(staging / "summary.json", summary)
            _write_json(staging / "leaderboard.json", leaderboard)
            _assert_required_files(staging, ("summary.json", "leaderboard.json"))
            backup_path = self._backup_existing(attempt_id) if backup and self.last_run_dir.exists() else None
            self._publish_last_run(staging, attempt_id)

        return {
            "attempt_id": attempt_id,
            "last_run_dir": str(self.last_run_dir),
            "summary_path": str(self.last_run_dir / "summary.json"),
            "leaderboard_path": str(self.last_run_dir / "leaderboard.json"),
            "backup_dir": _relative_or_none(backup_path),
            "leaderboard_summary": leaderboard["summary"],
            "top_rows": leaderboard["rows"],
        }

    def write_failed_attempt(self, play_name: str, error: Exception) -> dict[str, Any]:
        attempt_id = _attempt_id()
        failure_dir = self.failed_dir / attempt_id
        failure_dir.mkdir(parents=True, exist_ok=False)
        payload = {
            "schema_version": PLAY_ARTIFACT_SCHEMA_VERSION,
            "attempt_id": attempt_id,
            "play_name": play_name,
            "evidence_type": "exploratory_failure",
            "created_at": _now_iso(),
            "error_type": type(error).__name__,
            "message": safe_message(str(error)),
        }
        path = failure_dir / "failure.json"
        _write_json(path, payload)
        return {
            "attempt_id": attempt_id,
            "failure_dir": _relative_or_none(failure_dir),
            "failure_path": _relative_or_none(path),
        }

    @contextmanager
    def _locked(self):
        self.play_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_WRONLY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(descriptor)
            raise PlayArtifactError("another play run is already writing last-run artifacts") from error
        try:
            os.ftruncate(descriptor, 0)
            os.write(descriptor, _now_iso().encode())
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
            self.lock_path.unlink(missing_ok=True)

    def _backup_existing(self, attempt_id: str) -> Path:
        backup_path = self.backup_dir / attempt_id
        if backup_path.exists():
            raise PlayArtifactError("play backup target already exists")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.last_run_dir, backup_path)
        return backup_path

    def _publish_last_run(self, staging: Path, attempt_id: str) -> None:
        previous = self.play_dir / f".previous-{attempt_id}"
        if previous.exists():
            raise PlayArtifactError("play previous-last-run staging target already exists")
        if self.last_run_dir.exists():
            self.last_run_dir.replace(previous)
        try:
            staging.replace(self.last_run_dir)
        except BaseException:
            if previous.exists():
                if self.last_run_dir.exists():
                    shutil.rmtree(self.last_run_dir)
                previous.replace(self.last_run_dir)
            raise
        if previous.exists():
            shutil.rmtree(previous)


def build_play_leaderboard(
    variant_records: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    direction: str,
    rank_by: str = "primary_metric",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    excluded = 0
    for index, record in enumerate(variant_records):
        variant_id = _variant_id(record, index)
        if "error" in record:
            failures.append(_failure_sample(variant_id, record["error"]))
            continue
        value = _metric_value(record, metric)
        if value is None:
            excluded += 1
            failures.append(_failure_sample(variant_id, f"metric {metric!r} unavailable"))
            continue
        row = _leaderboard_row(record, variant_id, metric, value, direction)
        row["_sort_value"] = _sort_value(row, direction=direction, rank_by=rank_by)
        rows.append(row)

    reverse = rank_by == "baseline_delta" or direction == "desc"
    rows = sorted(rows, key=lambda row: (row["_sort_value"], row["variant_id"]), reverse=reverse)
    rows = [{key: value for key, value in row.items() if key != "_sort_value"} for row in rows]
    attempted = len(variant_records)
    failed = len(failures) - excluded
    succeeded = len(rows)
    return {
        "schema_version": PLAY_ARTIFACT_SCHEMA_VERSION,
        "metric": metric,
        "direction": direction,
        "rank_by": rank_by,
        "rows": rows[:MAX_LEADERBOARD_ROWS],
        "failure_samples": failures[:MAX_FAILURE_SAMPLES],
        "summary": {
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": failed,
            "excluded": excluded,
            "success_ratio": succeeded / attempted if attempted else 0.0,
            "partial_leaderboard": bool(failed or excluded),
            "failure_gating_status": "pass" if not failed and not excluded else "partial",
        },
    }


def _leaderboard_row(
    record: Mapping[str, Any],
    variant_id: str,
    metric: str,
    value: float,
    direction: str,
) -> dict[str, Any]:
    row = {
        "variant_id": variant_id,
        "primary_metric": metric,
        "primary_metric_value": value,
        "indicator_source": record.get("indicator_source"),
        "indicator_id": record.get("indicator_id"),
        "indicators": record.get("indicators", []),
        "params": record.get("params", {}),
        "portfolio": record.get("portfolio", {}),
    }
    baseline_value = _baseline_metric_value(record, metric)
    if baseline_value is not None:
        raw_delta = value - baseline_value
        row |= {
            "baseline_component_indicator_id": record.get("baseline_component_indicator_id"),
            "baseline_metric_value": baseline_value,
            "baseline_delta": raw_delta,
            "direction_adjusted_delta": raw_delta if direction == "desc" else -raw_delta,
        }
    return row


def _metric_value(record: Mapping[str, Any], metric: str) -> float | None:
    metrics = record.get("metrics", {})
    value = metrics.get(metric) if isinstance(metrics, Mapping) else record.get(metric)
    return _finite_float(value)


def _baseline_metric_value(record: Mapping[str, Any], metric: str) -> float | None:
    metrics = record.get("baseline_metrics", {})
    value = metrics.get(metric) if isinstance(metrics, Mapping) else record.get("baseline_metric_value")
    return _finite_float(value)


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _sort_value(row: Mapping[str, Any], *, direction: str, rank_by: str) -> float:
    if rank_by == "baseline_delta" and row.get("direction_adjusted_delta") is not None:
        return float(row["direction_adjusted_delta"])
    if rank_by == "baseline_delta" and direction == "asc":
        return -float(row["primary_metric_value"])
    return float(row["primary_metric_value"])


def _assert_public_payload_safe(payload: Mapping[str, Any]) -> None:
    try:
        assert_public_metadata_safe(payload)
    except ValueError as error:
        raise PlayArtifactError("play artifact payload contains unsafe public metadata") from error


def _variant_id(record: Mapping[str, Any], index: int) -> str:
    value = record.get("variant_id") or record.get("id")
    if isinstance(value, str) and value:
        return value
    params = record.get("params", {})
    token = json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
    return f"variant-{index}-{uuid.uuid5(uuid.NAMESPACE_URL, token)}"


def _failure_sample(variant_id: str, error: Any) -> dict[str, str]:
    if isinstance(error, Mapping):
        code = safe_message(str(error.get("code", "variant_failed")))
        message = safe_message(str(error.get("message", code)))
    else:
        code = "variant_failed"
        message = safe_message(str(error))
    return {"variant_id": variant_id, "code": code, "message": message}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n")


def _assert_required_files(path: Path, names: Sequence[str]) -> None:
    missing = [name for name in names if not (path / name).is_file()]
    if missing:
        raise PlayArtifactError(f"play staging is incomplete: {missing}")


def _attempt_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _relative_or_none(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path)
