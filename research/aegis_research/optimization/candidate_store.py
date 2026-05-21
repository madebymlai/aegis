from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class CandidateStoreError(RuntimeError):
    pass


class CandidateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        _ensure_private_location(self.path)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if os.name == "posix":
            self.path.chmod(0o600)
        self._ensure_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> CandidateStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def insert_completed_run(
        self,
        *,
        run_id: str,
        candidate_rows: Sequence[Mapping[str, Any]],
        leaderboard: Mapping[str, Any],
        provenance: Mapping[str, Any],
    ) -> None:
        if not candidate_rows:
            raise CandidateStoreError("completed optimization run has no candidate rows to persist")
        rank_scope = _rank_scope(leaderboard)
        ranking_metric = str(leaderboard["ranking_metric"])
        ranking_direction = str(leaderboard["ranking_direction"])
        with self._connection:
            for row in candidate_rows:
                self._insert_candidate(run_id=run_id, row=row, provenance=provenance)
            self._connection.execute(
                "DELETE FROM candidate_rankings WHERE run_id = ? AND rank_scope = ?",
                (run_id, rank_scope),
            )
            for rank, row in enumerate(leaderboard.get("rows", ()), start=1):
                candidate_key = str(row["candidate_key"])
                self._connection.execute(
                    """
                    INSERT INTO candidate_rankings (
                        run_id,
                        rank_scope,
                        candidate_key,
                        rank,
                        ranking_metric,
                        ranking_direction,
                        ranking_metric_value,
                        metric_sort_value,
                        metrics_json,
                        leaderboard_row_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        rank_scope,
                        candidate_key,
                        rank,
                        ranking_metric,
                        ranking_direction,
                        _float_or_none(row.get("ranking_metric_value")),
                        _metric_sort_value(row.get("ranking_metric_value"), ranking_direction),
                        _json_dumps(row.get("metrics", {})),
                        _json_dumps(row),
                    ),
                )

    def insert_promotion(
        self,
        *,
        token: str,
        run_id: str,
        component_family: str,
        component_id: str,
        component_slot: str,
        candidate_key: str,
        params: Mapping[str, Any],
        provenance: Mapping[str, Any],
    ) -> None:
        row_payload = {
            "run_id": run_id,
            "component_family": component_family,
            "component_id": component_id,
            "component_slot": component_slot,
            "candidate_key": candidate_key,
            "params_json": _json_dumps(params),
            "provenance_json": _json_dumps(provenance),
        }
        with self._connection:
            existing = self._connection.execute(
                "SELECT * FROM candidate_promotions WHERE token = ?",
                (token,),
            ).fetchone()
            if existing is not None:
                for field, value in row_payload.items():
                    if existing[field] != value:
                        raise CandidateStoreError(
                            f"promotion token {token} already exists with different payload"
                        )
                return
            self._connection.execute(
                """
                INSERT INTO candidate_promotions (
                    token,
                    run_id,
                    component_family,
                    component_id,
                    component_slot,
                    candidate_key,
                    params_json,
                    provenance_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token,
                    row_payload["run_id"],
                    row_payload["component_family"],
                    row_payload["component_id"],
                    row_payload["component_slot"],
                    row_payload["candidate_key"],
                    row_payload["params_json"],
                    row_payload["provenance_json"],
                ),
            )

    def top_candidates_by_run(self, run_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT r.rank, r.leaderboard_row_json, c.candidate_row_json, c.provenance_json
            FROM candidate_rankings r
            JOIN candidates c ON c.run_id = r.run_id AND c.candidate_key = r.candidate_key
            WHERE r.run_id = ?
            ORDER BY r.rank ASC
            LIMIT ?
            """,
            (run_id, limit),
        ).fetchall()
        return [_ranked_result(row) for row in rows]

    def top_candidates_by_metric(
        self,
        metric: str,
        *,
        direction: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT r.rank, r.leaderboard_row_json, c.candidate_row_json, c.provenance_json
            FROM candidate_rankings r
            JOIN candidates c ON c.run_id = r.run_id AND c.candidate_key = r.candidate_key
            WHERE r.ranking_metric = ? AND r.ranking_direction = ?
            ORDER BY r.metric_sort_value ASC, r.run_id ASC, r.candidate_key ASC
            LIMIT ?
            """,
            (metric, direction, limit),
        ).fetchall()
        return [_ranked_result(row) for row in rows]

    def params_by_candidate_key(
        self,
        candidate_key: str,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._candidate_lookup(candidate_key, run_id=run_id)
        return _json_loads(row["params_json"])

    def candidate_by_key(
        self,
        candidate_key: str,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._candidate_lookup(candidate_key, run_id=run_id)
        return {
            "run_id": row["run_id"],
            "candidate_key": row["candidate_key"],
            "candidate": _json_loads(row["candidate_row_json"]),
            "params": _json_loads(row["params_json"]),
            "provenance": _json_loads(row["provenance_json"]),
        }

    def provenance_by_candidate(
        self,
        candidate_key: str,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._candidate_lookup(candidate_key, run_id=run_id)
        return _json_loads(row["provenance_json"])

    def params_by_promotion_token(self, token: str) -> dict[str, Any]:
        return self.promotion_by_token(token)["params"]

    def promotion_by_token(self, token: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM candidate_promotions WHERE token = ?",
            (token,),
        ).fetchone()
        if row is None:
            raise CandidateStoreError(f"unknown promotion token: {token}")
        return {
            "token": row["token"],
            "run_id": row["run_id"],
            "component_family": row["component_family"],
            "component_id": row["component_id"],
            "component_slot": row["component_slot"],
            "candidate_key": row["candidate_key"],
            "params": _json_loads(row["params_json"]),
            "provenance": _json_loads(row["provenance_json"]),
        }

    def _ensure_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidate_store_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        row = self._connection.execute(
            "SELECT value FROM candidate_store_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO candidate_store_meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
        elif row["value"] != str(SCHEMA_VERSION):
            raise CandidateStoreError(
                f"candidate store schema version {row['value']} is not supported; "
                f"expected {SCHEMA_VERSION}"
            )
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                run_id TEXT NOT NULL,
                candidate_key TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                params_json TEXT NOT NULL,
                identity_json TEXT NOT NULL,
                store_namespace_json TEXT NOT NULL,
                candidate_row_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                PRIMARY KEY (run_id, candidate_key)
            );
            CREATE INDEX IF NOT EXISTS idx_candidates_key ON candidates(candidate_key);

            CREATE TABLE IF NOT EXISTS candidate_rankings (
                run_id TEXT NOT NULL,
                rank_scope TEXT NOT NULL,
                candidate_key TEXT NOT NULL,
                rank INTEGER NOT NULL,
                ranking_metric TEXT NOT NULL,
                ranking_direction TEXT NOT NULL,
                ranking_metric_value REAL,
                metric_sort_value REAL NOT NULL,
                metrics_json TEXT NOT NULL,
                leaderboard_row_json TEXT NOT NULL,
                PRIMARY KEY (run_id, rank_scope, candidate_key),
                UNIQUE (run_id, rank_scope, rank),
                FOREIGN KEY (run_id, candidate_key) REFERENCES candidates(run_id, candidate_key)
            );
            CREATE INDEX IF NOT EXISTS idx_candidate_rankings_run
                ON candidate_rankings(run_id, rank);
            CREATE INDEX IF NOT EXISTS idx_candidate_rankings_metric
                ON candidate_rankings(ranking_metric, ranking_direction, metric_sort_value);

            CREATE TABLE IF NOT EXISTS candidate_promotions (
                token TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                component_family TEXT NOT NULL,
                component_id TEXT NOT NULL,
                component_slot TEXT NOT NULL,
                candidate_key TEXT NOT NULL,
                params_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                FOREIGN KEY (run_id, candidate_key) REFERENCES candidates(run_id, candidate_key)
            );
            CREATE INDEX IF NOT EXISTS idx_candidate_promotions_candidate
                ON candidate_promotions(run_id, candidate_key);
            """
        )

    def _insert_candidate(
        self,
        *,
        run_id: str,
        row: Mapping[str, Any],
        provenance: Mapping[str, Any],
    ) -> None:
        candidate_key = str(row["candidate_key"])
        candidate_row_json = _json_dumps(row)
        existing = self._connection.execute(
            "SELECT candidate_row_json FROM candidates WHERE run_id = ? AND candidate_key = ?",
            (run_id, candidate_key),
        ).fetchone()
        if existing is not None:
            if existing["candidate_row_json"] != candidate_row_json:
                raise CandidateStoreError(
                    f"candidate {candidate_key} already exists for run {run_id} with different payload"
                )
            return
        self._connection.execute(
            """
            INSERT INTO candidates (
                run_id,
                candidate_key,
                row_index,
                params_json,
                identity_json,
                store_namespace_json,
                candidate_row_json,
                provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                candidate_key,
                int(row["row_index"]),
                _json_dumps(row["params"]),
                _json_dumps(row["identity"]),
                _json_dumps(row.get("store_namespace", {})),
                candidate_row_json,
                _json_dumps(provenance),
            ),
        )

    def _candidate_lookup(self, candidate_key: str, *, run_id: str | None) -> sqlite3.Row:
        if run_id is None:
            rows = self._connection.execute(
                "SELECT * FROM candidates WHERE candidate_key = ? ORDER BY run_id ASC",
                (candidate_key,),
            ).fetchall()
            if len(rows) > 1:
                raise CandidateStoreError(
                    f"candidate key {candidate_key} exists in multiple runs; pass run_id"
                )
            row = rows[0] if rows else None
        else:
            row = self._connection.execute(
                "SELECT * FROM candidates WHERE run_id = ? AND candidate_key = ?",
                (run_id, candidate_key),
            ).fetchone()
        if row is None:
            raise CandidateStoreError(f"unknown candidate key: {candidate_key}")
        return row


def _ensure_private_location(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "posix":
        return
    parent_mode = path.parent.stat().st_mode & 0o777
    if parent_mode & 0o077:
        raise CandidateStoreError(
            f"candidate store directory {path.parent} must not be accessible by group/other"
        )
    if path.exists():
        file_mode = path.stat().st_mode & 0o777
        if file_mode & 0o077:
            raise CandidateStoreError(
                f"candidate store {path} must not be accessible by group/other"
            )


def _rank_scope(leaderboard: Mapping[str, Any]) -> str:
    return _json_dumps(
        {
            "schema_version": leaderboard.get("schema_version"),
            "ranking_metric": leaderboard.get("ranking_metric"),
            "ranking_direction": leaderboard.get("ranking_direction"),
            "metric_registry_fingerprint": leaderboard.get("metric_registry_fingerprint"),
            "weight_basis": leaderboard.get("weight_basis"),
        }
    )


def _ranked_result(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "rank": row["rank"],
        "leaderboard_row": _json_loads(row["leaderboard_row_json"]),
        "candidate": _json_loads(row["candidate_row_json"]),
        "provenance": _json_loads(row["provenance_json"]),
    }


def _metric_sort_value(value: Any, direction: str) -> float:
    parsed = _float_or_none(value)
    if parsed is None:
        return float("inf")
    return -parsed if direction == "desc" else parsed


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return None if parsed != parsed else parsed


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_loads(value: str) -> Any:
    return json.loads(value)
