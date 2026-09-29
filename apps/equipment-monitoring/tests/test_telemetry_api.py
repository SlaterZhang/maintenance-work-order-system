from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.config import Settings
from src.domain.models import HealthEvaluationResponse
from src.interfaces.http import create_app


class RecordingHealthClient:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls = []

    def evaluate(self, request, trace_id, idempotency_key):
        self.calls.append((request, trace_id, idempotency_key))
        if self.should_fail:
            raise ConnectionError("warning service unavailable")
        return HealthEvaluationResponse(
            evaluationId=request.evaluationId,
            equipmentId=request.equipmentId,
            healthScore=92,
            riskLevel="LOW",
            suspectedFault="",
            recommendedAction="",
            modelVersion="test-rule-1",
            evaluatedAt="2026-09-17T08:32:00Z",
            warningId=None,
        )


def sample(sample_id: str, measured_at: str, temperature: float = 78.5) -> dict:
    return {
        "sampleId": sample_id,
        "measuredAt": measured_at,
        "temperatureC": temperature,
        "vibrationMmS": 6.2,
        "currentA": 13.8,
        "rotationalSpeedRpm": 1450,
    }


def test_ingest_query_and_duplicate_batch(client) -> None:
    body = {
        "batchId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "source": "SIMULATOR",
        "samples": [
            sample("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "2026-09-17T08:30:00Z"),
            sample("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "2026-09-17T08:31:00Z", 79.0),
        ],
    }
    first_headers = {
        "Idempotency-Key": "66666666-6666-4666-8666-666666666666",
        "X-Internal-Token": "test-internal-token",
    }
    first = client.post(
        "/api/v1/equipment/EQ-000001/telemetry", json=body, headers=first_headers
    )

    assert first.status_code == 202
    assert first.json()["acceptedCount"] == 2
    assert first.json()["rejectedCount"] == 0
    assert first.json()["duplicate"] is False

    duplicate_headers = {
        "Idempotency-Key": "77777777-7777-4777-8777-777777777777",
        "X-Internal-Token": "test-internal-token",
    }
    duplicate = client.post(
        "/api/v1/equipment/EQ-000001/telemetry", json=body, headers=duplicate_headers
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["duplicate"] is True

    page = client.get(
        "/api/v1/equipment/EQ-000001/telemetry",
        params={"from": "2026-09-17T08:30:30Z", "to": "2026-09-17T09:00:00Z"},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["sampleId"] == "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def test_telemetry_rejects_bad_range_and_non_utc_time(client) -> None:
    bad_range = client.get(
        "/api/v1/equipment/EQ-000001/telemetry",
        params={"from": "2026-09-18T00:00:00Z", "to": "2026-09-17T00:00:00Z"},
    )
    assert bad_range.status_code == 400
    assert bad_range.json()["code"] == "VALIDATION_ERROR"

    body = {
        "batchId": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        "source": "DEVICE_GATEWAY",
        "samples": [
            sample("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "2026-09-17T16:30:00+08:00")
        ],
    }
    response = client.post(
        "/api/v1/equipment/EQ-000001/telemetry",
        json=body,
        headers={
            "Idempotency-Key": "88888888-8888-4888-8888-888888888888",
            "X-Internal-Token": "test-internal-token",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_telemetry_write_requires_configured_credential(client) -> None:
    response = client.post(
        "/api/v1/equipment/EQ-000001/telemetry",
        json={
            "batchId": "ffffffff-ffff-4fff-8fff-ffffffffffff",
            "source": "MANUAL_TEST",
            "samples": [
                sample("99999999-9999-4999-8999-999999999999", "2026-09-17T08:30:00Z")
            ],
        },
        headers={"Idempotency-Key": "99999999-1111-4111-8111-999999999999"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_TOKEN_INVALID"


def test_ingestion_calls_member_b_with_c_int_02_contract(tmp_path: Path) -> None:
    health_client = RecordingHealthClient()
    app = create_app(
        Settings(database_path=tmp_path / "outbound.db", seed_on_start=True),
        health_evaluation_client=health_client,
    )
    body = {
        "batchId": "abababab-abab-4bab-8bab-abababababab",
        "source": "SIMULATOR",
        "samples": [
            sample("cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd", "2026-09-17T08:30:00Z")
        ],
    }
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/equipment/EQ-000001/telemetry",
            json=body,
            headers={
                "Idempotency-Key": "34343434-3434-4434-8434-343434343434",
                "X-Trace-Id": "trace-health-001",
            },
        )

    assert response.status_code == 202
    assert len(health_client.calls) == 1
    request, trace_id, evaluation_key = health_client.calls[0]
    assert request.equipmentId == "EQ-000001"
    assert str(request.sample.sampleId) == "cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd"
    assert trace_id == "trace-health-001"
    assert evaluation_key == str(request.evaluationId)
    assert app.state.repository.count_pending_health_evaluations() == 0


def test_member_b_failure_keeps_health_evaluation_for_retry(tmp_path: Path) -> None:
    health_client = RecordingHealthClient(should_fail=True)
    app = create_app(
        Settings(database_path=tmp_path / "outbox-retry.db", seed_on_start=True),
        health_evaluation_client=health_client,
    )
    body = {
        "batchId": "efefefef-efef-4fef-8fef-efefefefefef",
        "source": "DEVICE_GATEWAY",
        "samples": [
            sample("10101010-1010-4010-8010-101010101010", "2026-09-17T08:30:00Z")
        ],
    }
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/equipment/EQ-000001/telemetry",
            json=body,
            headers={
                "Idempotency-Key": "56565656-5656-4656-8656-565656565656",
                "X-Trace-Id": "trace-health-002",
            },
        )

    assert response.status_code == 202
    assert response.json()["acceptedCount"] == 1
    assert app.state.repository.count_pending_health_evaluations() == 1

    original_evaluation_id = health_client.calls[0][2]
    health_client.should_fail = False
    assert app.state.service.dispatch_pending_health_evaluations() == 1
    assert health_client.calls[-1][2] == original_evaluation_id
    assert app.state.repository.count_pending_health_evaluations() == 0
