from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import NAMESPACE_URL, uuid5

from src.domain.errors import DomainError, idempotency_conflict, not_found, version_conflict
from src.domain.models import to_rfc3339, utc_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS sequences (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL CHECK (value >= 0)
);

CREATE TABLE IF NOT EXISTS equipment (
    equipment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    equipment_type TEXT NOT NULL,
    production_line_id TEXT NOT NULL,
    location TEXT NOT NULL,
    manufacturer TEXT,
    model TEXT,
    responsible_department TEXT,
    current_status TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    version INTEGER NOT NULL CHECK (version >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equipment_line_status
    ON equipment (production_line_id, current_status);
CREATE INDEX IF NOT EXISTS idx_equipment_name ON equipment (name);

CREATE TABLE IF NOT EXISTS telemetry_batches (
    batch_id TEXT PRIMARY KEY,
    equipment_id TEXT NOT NULL REFERENCES equipment(equipment_id),
    source TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    accepted_count INTEGER NOT NULL,
    rejected_count INTEGER NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry_samples (
    sample_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES telemetry_batches(batch_id),
    equipment_id TEXT NOT NULL REFERENCES equipment(equipment_id),
    measured_at TEXT NOT NULL,
    temperature_c REAL NOT NULL,
    vibration_mm_s REAL NOT NULL,
    current_a REAL NOT NULL,
    rotational_speed_rpm REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_equipment_time
    ON telemetry_samples (equipment_id, measured_at DESC);

CREATE TABLE IF NOT EXISTS health_evaluation_outbox (
    evaluation_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES telemetry_batches(batch_id),
    sample_id TEXT NOT NULL UNIQUE REFERENCES telemetry_samples(sample_id),
    equipment_id TEXT NOT NULL REFERENCES equipment(equipment_id),
    request_body TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'SENT')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_health_outbox_status_created
    ON health_evaluation_outbox (status, created_at);

CREATE TABLE IF NOT EXISTS equipment_status_events (
    event_id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    order_id TEXT NOT NULL,
    equipment_id TEXT NOT NULL REFERENCES equipment(equipment_id),
    previous_status TEXT NOT NULL,
    target_status TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    trace_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_status_event_equipment_time
    ON equipment_status_events (equipment_id, processed_at DESC);

CREATE TABLE IF NOT EXISTS idempotency_records (
    idempotency_key TEXT PRIMARY KEY,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class SQLiteEquipmentRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.database_path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO sequences(name, value) VALUES ('equipment', 0)"
            )
            connection.execute(
                """
                UPDATE sequences
                SET value = MAX(
                    value,
                    COALESCE(
                        (SELECT MAX(CAST(SUBSTR(equipment_id, 4) AS INTEGER)) FROM equipment),
                        0
                    )
                )
                WHERE name = 'equipment'
                """
            )
            connection.commit()

    @staticmethod
    def _equipment_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "equipmentId": row["equipment_id"],
            "name": row["name"],
            "equipmentType": row["equipment_type"],
            "productionLineId": row["production_line_id"],
            "location": row["location"],
            "manufacturer": row["manufacturer"],
            "model": row["model"],
            "responsibleDepartment": row["responsible_department"],
            "currentStatus": row["current_status"],
            "enabled": bool(row["enabled"]),
            "version": row["version"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _sample_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "sampleId": row["sample_id"],
            "measuredAt": row["measured_at"],
            "temperatureC": row["temperature_c"],
            "vibrationMmS": row["vibration_mm_s"],
            "currentA": row["current_a"],
            "rotationalSpeedRpm": row["rotational_speed_rpm"],
        }

    @staticmethod
    def _load_idempotent(
        connection: sqlite3.Connection,
        key: str,
        method: str,
        path: str,
        request_hash: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM idempotency_records WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        if (
            row["method"] != method
            or row["path"] != path
            or row["request_hash"] != request_hash
        ):
            raise idempotency_conflict()
        return json.loads(row["response_body"])

    @staticmethod
    def _store_idempotent(
        connection: sqlite3.Connection,
        key: str,
        method: str,
        path: str,
        request_hash: str,
        status_code: int,
        response: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO idempotency_records(
                idempotency_key, method, path, request_hash, status_code,
                response_body, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                method,
                path,
                request_hash,
                status_code,
                json.dumps(response, ensure_ascii=False, separators=(",", ":")),
                to_rfc3339(utc_now()),
            ),
        )

    def seed_if_empty(self) -> None:
        now = "2026-09-17T08:00:00Z"
        seeds = [
            (
                "EQ-000001", "一号数控机床", "CNC", "LINE-01", "一车间 A 区",
                "示例机床厂", "CNC-X1000", "机加车间", "RUNNING",
            ),
            (
                "EQ-000002", "二号工业机器人", "ROBOT", "LINE-01", "一车间 B 区",
                "示例自动化厂", "RB-200", "装配车间", "WARNING",
            ),
            (
                "EQ-000003", "循环水泵", "PUMP", "LINE-02", "二车间水泵房",
                "示例泵业", "P-80", "动力设备部", "STOPPED",
            ),
        ]
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]
            if count == 0:
                connection.executemany(
                    """
                    INSERT INTO equipment(
                        equipment_id, name, equipment_type, production_line_id,
                        location, manufacturer, model, responsible_department,
                        current_status, enabled, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
                    """,
                    [row + (now, now) for row in seeds],
                )
                connection.execute(
                    "UPDATE sequences SET value = MAX(value, 3) WHERE name = 'equipment'"
                )
            connection.commit()

    def get_equipment(self, equipment_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM equipment WHERE equipment_id = ?", (equipment_id,)
            ).fetchone()
        if row is None:
            raise not_found()
        return self._equipment_from_row(row)

    def list_equipment(
        self,
        keyword: str | None,
        production_line_id: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if keyword:
            clauses.append("(equipment_id LIKE ? OR name LIKE ?)")
            pattern = f"%{keyword}%"
            parameters.extend([pattern, pattern])
        if production_line_id:
            clauses.append("production_line_id = ?")
            parameters.append(production_line_id)
        if status:
            clauses.append("current_status = ?")
            parameters.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM equipment{where}", parameters
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM equipment{where} ORDER BY equipment_id LIMIT ? OFFSET ?",
                parameters + [page_size, (page - 1) * page_size],
            ).fetchall()
        return [self._equipment_from_row(row) for row in rows], total

    def create_equipment(
        self,
        values: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
    ) -> dict[str, Any]:
        path = "/api/v1/equipment"
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._load_idempotent(
                connection, idempotency_key, "POST", path, request_hash
            )
            if existing is not None:
                connection.commit()
                return existing
            current = connection.execute(
                "SELECT value FROM sequences WHERE name = 'equipment'"
            ).fetchone()[0]
            next_value = current + 1
            if next_value > 999999:
                raise DomainError(500, "INTERNAL_ERROR", "设备编号空间已用尽")
            equipment_id = f"EQ-{next_value:06d}"
            now = to_rfc3339(utc_now())
            connection.execute(
                "UPDATE sequences SET value = ? WHERE name = 'equipment'", (next_value,)
            )
            connection.execute(
                """
                INSERT INTO equipment(
                    equipment_id, name, equipment_type, production_line_id,
                    location, manufacturer, model, responsible_department,
                    current_status, enabled, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'STOPPED', 1, 0, ?, ?)
                """,
                (
                    equipment_id,
                    values["name"],
                    values["equipmentType"],
                    values["productionLineId"],
                    values["location"],
                    values.get("manufacturer"),
                    values.get("model"),
                    values.get("responsibleDepartment"),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM equipment WHERE equipment_id = ?", (equipment_id,)
            ).fetchone()
            response = self._equipment_from_row(row)
            self._store_idempotent(
                connection, idempotency_key, "POST", path, request_hash, 201, response
            )
            connection.commit()
        return response

    def update_equipment(
        self,
        equipment_id: str,
        expected_version: int,
        changes: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
    ) -> dict[str, Any]:
        path = f"/api/v1/equipment/{equipment_id}"
        field_map = {
            "name": "name",
            "productionLineId": "production_line_id",
            "location": "location",
            "responsibleDepartment": "responsible_department",
            "enabled": "enabled",
        }
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._load_idempotent(
                connection, idempotency_key, "PATCH", path, request_hash
            )
            if existing is not None:
                connection.commit()
                return existing
            row = connection.execute(
                "SELECT * FROM equipment WHERE equipment_id = ?", (equipment_id,)
            ).fetchone()
            if row is None:
                raise not_found()
            if row["version"] != expected_version:
                raise version_conflict(expected_version, row["version"])
            assignments: list[str] = []
            parameters: list[Any] = []
            for field_name, value in changes.items():
                assignments.append(f"{field_map[field_name]} = ?")
                parameters.append(int(value) if field_name == "enabled" else value)
            assignments.extend(["version = version + 1", "updated_at = ?"])
            parameters.extend([to_rfc3339(utc_now()), equipment_id])
            connection.execute(
                f"UPDATE equipment SET {', '.join(assignments)} WHERE equipment_id = ?",
                parameters,
            )
            updated = connection.execute(
                "SELECT * FROM equipment WHERE equipment_id = ?", (equipment_id,)
            ).fetchone()
            response = self._equipment_from_row(updated)
            self._store_idempotent(
                connection, idempotency_key, "PATCH", path, request_hash, 200, response
            )
            connection.commit()
        return response

    def ingest_telemetry(
        self,
        equipment_id: str,
        batch: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
        trace_id: str,
    ) -> dict[str, Any]:
        path = f"/api/v1/equipment/{equipment_id}/telemetry"
        batch_id = batch["batchId"]
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_idempotency = self._load_idempotent(
                connection, idempotency_key, "POST", path, request_hash
            )
            if existing_idempotency is not None:
                connection.commit()
                return existing_idempotency
            if connection.execute(
                "SELECT 1 FROM equipment WHERE equipment_id = ?", (equipment_id,)
            ).fetchone() is None:
                raise not_found()
            existing_batch = connection.execute(
                "SELECT * FROM telemetry_batches WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            if existing_batch is not None:
                if (
                    existing_batch["request_hash"] != request_hash
                    or existing_batch["equipment_id"] != equipment_id
                ):
                    raise idempotency_conflict()
                response = {
                    "batchId": batch_id,
                    "equipmentId": equipment_id,
                    "acceptedCount": existing_batch["accepted_count"],
                    "rejectedCount": existing_batch["rejected_count"],
                    "duplicate": True,
                    "receivedAt": existing_batch["received_at"],
                }
                self._store_idempotent(
                    connection, idempotency_key, "POST", path, request_hash, 202, response
                )
                connection.commit()
                return response

            sample_ids = [sample["sampleId"] for sample in batch["samples"]]
            placeholders = ",".join("?" for _ in sample_ids)
            existing_ids = {
                row[0]
                for row in connection.execute(
                    f"SELECT sample_id FROM telemetry_samples WHERE sample_id IN ({placeholders})",
                    sample_ids,
                ).fetchall()
            }
            accepted_samples = [
                sample for sample in batch["samples"] if sample["sampleId"] not in existing_ids
            ]
            received_at = to_rfc3339(utc_now())
            accepted_count = len(accepted_samples)
            rejected_count = len(batch["samples"]) - accepted_count
            connection.execute(
                """
                INSERT INTO telemetry_batches(
                    batch_id, equipment_id, source, request_hash,
                    accepted_count, rejected_count, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id, equipment_id, batch["source"], request_hash,
                    accepted_count, rejected_count, received_at,
                ),
            )
            connection.executemany(
                """
                INSERT INTO telemetry_samples(
                    sample_id, batch_id, equipment_id, measured_at,
                    temperature_c, vibration_mm_s, current_a, rotational_speed_rpm
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        sample["sampleId"], batch_id, equipment_id, sample["measuredAt"],
                        sample["temperatureC"], sample["vibrationMmS"], sample["currentA"],
                        sample["rotationalSpeedRpm"],
                    )
                    for sample in accepted_samples
                ],
            )
            for sample in accepted_samples:
                evaluation_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"equipment-health:{equipment_id}:{sample['sampleId']}",
                    )
                )
                evaluation_request = {
                    "evaluationId": evaluation_id,
                    "equipmentId": equipment_id,
                    "requestedAt": received_at,
                    "sample": sample,
                }
                connection.execute(
                    """
                    INSERT INTO health_evaluation_outbox(
                        evaluation_id, batch_id, sample_id, equipment_id,
                        request_body, trace_id, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    """,
                    (
                        evaluation_id,
                        batch_id,
                        sample["sampleId"],
                        equipment_id,
                        json.dumps(
                            evaluation_request,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        trace_id,
                        received_at,
                    ),
                )
            response = {
                "batchId": batch_id,
                "equipmentId": equipment_id,
                "acceptedCount": accepted_count,
                "rejectedCount": rejected_count,
                "duplicate": False,
                "receivedAt": received_at,
            }
            self._store_idempotent(
                connection, idempotency_key, "POST", path, request_hash, 202, response
            )
            connection.commit()
        return response

    def list_pending_health_evaluations(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT evaluation_id, request_body, trace_id
                FROM health_evaluation_outbox
                WHERE status = 'PENDING'
                ORDER BY created_at, evaluation_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "evaluationId": row["evaluation_id"],
                "request": json.loads(row["request_body"]),
                "traceId": row["trace_id"],
            }
            for row in rows
        ]

    def mark_health_evaluation_sent(self, evaluation_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE health_evaluation_outbox
                SET status = 'SENT', attempts = attempts + 1,
                    last_error = NULL, sent_at = ?
                WHERE evaluation_id = ? AND status = 'PENDING'
                """,
                (to_rfc3339(utc_now()), evaluation_id),
            )
            connection.commit()

    def mark_health_evaluation_failed(self, evaluation_id: str, error: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE health_evaluation_outbox
                SET attempts = attempts + 1, last_error = ?
                WHERE evaluation_id = ? AND status = 'PENDING'
                """,
                (error[:500], evaluation_id),
            )
            connection.commit()

    def count_pending_health_evaluations(self) -> int:
        with self._connection() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM health_evaluation_outbox WHERE status = 'PENDING'"
            ).fetchone()[0]

    def list_telemetry(
        self,
        equipment_id: str,
        from_time: str | None,
        to_time: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._connection() as connection:
            if connection.execute(
                "SELECT 1 FROM equipment WHERE equipment_id = ?", (equipment_id,)
            ).fetchone() is None:
                raise not_found()
            clauses = ["equipment_id = ?"]
            parameters: list[Any] = [equipment_id]
            if from_time:
                clauses.append("measured_at >= ?")
                parameters.append(from_time)
            if to_time:
                clauses.append("measured_at <= ?")
                parameters.append(to_time)
            where = " AND ".join(clauses)
            total = connection.execute(
                f"SELECT COUNT(*) FROM telemetry_samples WHERE {where}", parameters
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT * FROM telemetry_samples WHERE {where}
                ORDER BY measured_at DESC, sample_id DESC LIMIT ? OFFSET ?
                """,
                parameters + [page_size, (page - 1) * page_size],
            ).fetchall()
        return [self._sample_from_row(row) for row in rows], total

    def consume_status_event(
        self,
        event: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
    ) -> dict[str, Any]:
        path = "/api/v1/integration/equipment-status-events"
        event_id = event["eventId"]
        payload = event["payload"]
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous_event = connection.execute(
                "SELECT request_hash, trace_id FROM equipment_status_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if previous_event is not None:
                if previous_event["request_hash"] != request_hash:
                    raise idempotency_conflict()
                response = {
                    "accepted": True,
                    "duplicate": True,
                    "traceId": previous_event["trace_id"],
                }
                existing_key = connection.execute(
                    "SELECT 1 FROM idempotency_records WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing_key is None:
                    self._store_idempotent(
                        connection, idempotency_key, "POST", path, request_hash, 202, response
                    )
                connection.commit()
                return response

            existing_idempotency = self._load_idempotent(
                connection, idempotency_key, "POST", path, request_hash
            )
            if existing_idempotency is not None:
                connection.commit()
                return existing_idempotency
            equipment = connection.execute(
                "SELECT * FROM equipment WHERE equipment_id = ?", (payload["equipmentId"],)
            ).fetchone()
            if equipment is None:
                raise not_found()
            processed_at = to_rfc3339(utc_now())
            connection.execute(
                """
                INSERT INTO equipment_status_events(
                    event_id, request_hash, order_id, equipment_id, previous_status,
                    target_status, operator_id, reason, occurred_at, processed_at, trace_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, request_hash, payload["orderId"], payload["equipmentId"],
                    equipment["current_status"], payload["targetStatus"], payload["operatorId"],
                    payload["reason"], event["occurredAt"], processed_at, event["traceId"],
                ),
            )
            connection.execute(
                """
                UPDATE equipment
                SET current_status = ?, version = version + 1, updated_at = ?
                WHERE equipment_id = ?
                """,
                (payload["targetStatus"], processed_at, payload["equipmentId"]),
            )
            response = {"accepted": True, "duplicate": False, "traceId": event["traceId"]}
            self._store_idempotent(
                connection, idempotency_key, "POST", path, request_hash, 202, response
            )
            connection.commit()
        return response

    def count_status_events(self, event_id: str) -> int:
        with self._connection() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM equipment_status_events WHERE event_id = ?", (event_id,)
            ).fetchone()[0]
