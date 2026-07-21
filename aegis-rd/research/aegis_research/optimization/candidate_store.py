from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.optimization.candidate_evidence import (
    CANDIDATE_EVAL_ROW_SCHEMA_VERSION,
    CANDIDATE_IDENTITY_SCHEMA_VERSION,
    candidate_key_for_identity,
)
from research.aegis_research.optimization.candidate_store_identity import (
    CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
)
from research.aegis_research.optimization.continuous_evidence import (
    validate_selection_identity,
)

SCHEMA_VERSION = 7
PUBLICATION_PENDING = "pending"
PUBLICATION_ACTIVE = "active"
PUBLICATION_STATES = frozenset({PUBLICATION_PENDING, PUBLICATION_ACTIVE})


class CandidateStoreError(RuntimeError):
    pass


class CandidateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        _ensure_private_location(self.path)
        self._connection = sqlite3.connect(self.path)
        try:
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            if os.name == "posix":
                self.path.chmod(0o600)
            self._ensure_schema()
        except BaseException:
            # The connection is open before validation runs; a failed schema check
            # (or any init error) must not leak it, since __enter__ never fires when
            # __init__ raises inside a `with`.
            self._connection.close()
            raise

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
        provenance: Mapping[str, Any],
        publication_state: str = PUBLICATION_ACTIVE,
    ) -> None:
        _validate_publication_state(publication_state)
        if not candidate_rows:
            raise CandidateStoreError("completed optimization run has no candidate rows to persist")
        _validate_continuous_protocol(candidate_rows, provenance)
        candidate_values = [
            _candidate_insert_values(
                run_id=run_id,
                row=row,
                provenance=provenance,
                publication_state=publication_state,
            )
            for row in candidate_rows
        ]
        candidate_payloads = [(value[1], value[4]) for value in candidate_values]
        ranking_values = [
            (run_id, str(row["role"]), str(row["candidate_key"]), publication_state)
            for row in candidate_rows
        ]
        with self._connection:
            self._connection.executemany(
                """
                INSERT OR IGNORE INTO candidates (
                    run_id,
                    candidate_key,
                    params_json,
                    identity_json,
                    candidate_row_json,
                    provenance_json,
                    publication_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                candidate_values,
            )
            self._assert_candidate_payloads_match(
                run_id=run_id,
                candidate_payloads=candidate_payloads,
            )
            self._connection.executemany(
                """
                UPDATE candidates
                SET publication_state = ?
                WHERE run_id = ? AND candidate_key = ?
                """,
                ((publication_state, run_id, str(row["candidate_key"])) for row in candidate_rows),
            )
            self._connection.execute(
                "DELETE FROM candidate_rankings WHERE run_id = ?",
                (run_id,),
            )
            self._connection.executemany(
                """
                INSERT INTO candidate_rankings (
                    run_id,
                    role,
                    candidate_key,
                    publication_state
                ) VALUES (?, ?, ?, ?)
                """,
                ranking_values,
            )

    def activate_run(self, run_id: str) -> None:
        with self._connection:
            candidate_count = self._connection.execute(
                "SELECT COUNT(*) FROM candidates WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            if candidate_count == 0:
                raise CandidateStoreError(f"cannot activate unknown candidate-store run: {run_id}")
            self._connection.execute(
                "UPDATE candidates SET publication_state = ? WHERE run_id = ?",
                (PUBLICATION_ACTIVE, run_id),
            )
            self._connection.execute(
                "UPDATE candidate_rankings SET publication_state = ? WHERE run_id = ?",
                (PUBLICATION_ACTIVE, run_id),
            )

    def candidate_key_for_role(self, run_id: str, role: str) -> str:
        """Resolve a representative role (best/median/worst) to its candidate_key.

        A role is the storage-free handle into a Run's ranked candidates — the
        ``candidate_rankings`` primary key is ``(run_id, role)``. Raises when the run
        has no active candidate filling that role.
        """
        row = self._connection.execute(
            """
            SELECT candidate_key FROM candidate_rankings
            WHERE run_id = ? AND role = ? AND publication_state = ?
            """,
            (run_id, role, PUBLICATION_ACTIVE),
        ).fetchone()
        if row is None:
            raise CandidateStoreError(f"unknown role {role!r} for run {run_id!r}")
        return row["candidate_key"]

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
                params_json TEXT NOT NULL,
                identity_json TEXT NOT NULL,
                candidate_row_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                publication_state TEXT NOT NULL,
                PRIMARY KEY (run_id, candidate_key)
            );
            CREATE INDEX IF NOT EXISTS idx_candidates_key ON candidates(candidate_key);

            CREATE TABLE IF NOT EXISTS candidate_rankings (
                run_id TEXT NOT NULL,
                role TEXT NOT NULL,
                candidate_key TEXT NOT NULL,
                publication_state TEXT NOT NULL,
                PRIMARY KEY (run_id, role),
                FOREIGN KEY (run_id, candidate_key) REFERENCES candidates(run_id, candidate_key)
            );
            """
        )

    def _assert_candidate_payloads_match(
        self,
        *,
        run_id: str,
        candidate_payloads: Sequence[tuple[Any, Any]],
    ) -> None:
        expected_payloads: dict[str, str] = {}
        for candidate_key_value, payload_value in candidate_payloads:
            candidate_key = str(candidate_key_value)
            payload = str(payload_value)
            existing_payload = expected_payloads.setdefault(candidate_key, payload)
            if existing_payload != payload:
                raise CandidateStoreError(
                    f"candidate {candidate_key} already exists for run {run_id} with different payload"
                )

        for candidate_keys in _chunks(tuple(expected_payloads), 500):
            placeholders = ",".join("?" for _ in candidate_keys)
            rows = self._connection.execute(
                f"""
                SELECT candidate_key, candidate_row_json
                FROM candidates
                WHERE run_id = ? AND candidate_key IN ({placeholders})
                """,
                (run_id, *candidate_keys),
            ).fetchall()
            stored_payloads = {row["candidate_key"]: row["candidate_row_json"] for row in rows}
            missing = sorted(set(candidate_keys) - set(stored_payloads))
            if missing:
                raise CandidateStoreError(
                    f"candidate rows were not persisted for run {run_id}: {missing[:5]}"
                )
            for candidate_key in candidate_keys:
                if stored_payloads[candidate_key] != expected_payloads[candidate_key]:
                    raise CandidateStoreError(
                        f"candidate {candidate_key} already exists for run {run_id} with different payload"
                    )

    def _candidate_lookup(self, candidate_key: str, *, run_id: str | None) -> sqlite3.Row:
        if run_id is None:
            rows = self._connection.execute(
                """
                SELECT * FROM candidates
                WHERE candidate_key = ? AND publication_state = ?
                ORDER BY run_id ASC
                """,
                (candidate_key, PUBLICATION_ACTIVE),
            ).fetchall()
            if len(rows) > 1:
                raise CandidateStoreError(
                    f"candidate key {candidate_key} exists in multiple runs; pass run_id"
                )
            row = rows[0] if rows else None
        else:
            row = self._connection.execute(
                """
                SELECT * FROM candidates
                WHERE run_id = ? AND candidate_key = ? AND publication_state = ?
                """,
                (run_id, candidate_key, PUBLICATION_ACTIVE),
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


def _candidate_insert_values(
    *,
    run_id: str,
    row: Mapping[str, Any],
    provenance: Mapping[str, Any],
    publication_state: str,
) -> tuple[Any, ...]:
    return (
        run_id,
        str(row["candidate_key"]),
        _json_dumps(row["params"]),
        _json_dumps(row["identity"]),
        _json_dumps(_stable_candidate_payload(row)),
        _json_dumps(provenance),
        publication_state,
    )


def _stable_candidate_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    """Candidate evidence stripped of run-specific ranking attributes.

    ``role`` and ``rank`` vary by slot while ``candidate_key`` is identity-stable,
    so a candidate that fills several roles must persist an identical payload to
    pass the duplicate-payload guard.
    """
    return {
        key: value for key, value in row.items() if key not in ("role", "ordinal_rank")
    }


def _validate_continuous_protocol(
    candidate_rows: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
) -> None:
    if provenance.get("schema_version") != CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION:
        raise CandidateStoreError("unsupported candidate store provenance schema_version")
    provenance_identity = provenance.get("selection_identity")
    if not isinstance(provenance_identity, Mapping):
        raise CandidateStoreError("candidate store provenance requires a selection identity")
    try:
        validate_selection_identity(provenance_identity)
    except (TypeError, ValueError) as error:
        raise CandidateStoreError(str(error)) from error
    provenance_identity_bytes = canonical_json_bytes(provenance_identity)
    for row in candidate_rows:
        if row.get("schema_version") != CANDIDATE_EVAL_ROW_SCHEMA_VERSION:
            raise CandidateStoreError("unsupported candidate row schema_version")
        identity = row.get("identity")
        if not isinstance(identity, Mapping):
            raise CandidateStoreError("candidate row requires a versioned identity")
        if identity.get("schema_version") != CANDIDATE_IDENTITY_SCHEMA_VERSION:
            raise CandidateStoreError("unsupported Candidate identity schema_version")
        candidate_key = row.get("candidate_key")
        if candidate_key != candidate_key_for_identity(identity):
            raise CandidateStoreError("candidate_key does not match Candidate identity")
        row_selection_identity = identity.get("selection_identity")
        if (
            not isinstance(row_selection_identity, Mapping)
            or canonical_json_bytes(row_selection_identity) != provenance_identity_bytes
        ):
            raise CandidateStoreError(
                "candidate and store provenance selection identity do not match"
            )
        retired = {
            "selection_metrics",
            "held_out_metrics",
            "held_out_metrics_mean",
        } & set(row)
        if retired:
            raise CandidateStoreError(
                f"candidate row contains retired Split evidence fields: {sorted(retired)}"
            )


def _validate_publication_state(value: str) -> None:
    if value not in PUBLICATION_STATES:
        raise CandidateStoreError(
            f"candidate publication_state must be one of {sorted(PUBLICATION_STATES)}; got {value!r}"
        )


def _chunks(values: Sequence[str], size: int) -> Iterator[tuple[str, ...]]:
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])


def _json_dumps(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _json_loads(value: str) -> Any:
    return json.loads(value)
