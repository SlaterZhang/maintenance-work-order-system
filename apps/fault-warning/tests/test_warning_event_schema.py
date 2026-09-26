import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"
SAMPLE = {
    "sampleId": "e51d94ca-5258-4e5a-bccc-99c55cfda001",
    "measuredAt": "2026-09-17T08:29:50Z",
    "temperatureC": 78.5,
    "vibrationMmS": 6.2,
    "currentA": 13.8,
    "rotationalSpeedRpm": 1450,
}


def _load(name: str) -> dict:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def _validate(event: dict) -> list:
    envelope = Draft202012Validator(
        _load("schemas/event-envelope.schema.json"), format_checker=FormatChecker()
    )
    payload = Draft202012Validator(
        _load("schemas/warning-raised.payload.schema.json"), format_checker=FormatChecker()
    )
    errors = list(envelope.iter_errors(event))
    errors += list(payload.iter_errors(event["payload"]))
    return errors


def test_built_event_passes_contract_schemas(client: TestClient, db):
    request = {
        "evaluationId": str(uuid.uuid4()),
        "equipmentId": "EQ-000001",
        "requestedAt": "2026-09-17T08:29:55Z",
        "sample": dict(SAMPLE),
    }
    response = client.post(
        "/api/v1/health-evaluations",
        json=request,
        headers={
            "X-Internal-Token": "dev-internal-token-change-me",
            "Idempotency-Key": request["evaluationId"],
            "X-Trace-Id": "trace-20260917-001",
        },
    )
    warning_id = response.json()["warningId"]

    from src.application import warning_service

    event = warning_service.build_warning_raised_event(
        db, warning_id, SAMPLE, "trace-20260917-001"
    )
    errors = _validate(event)
    assert errors == []


def test_contract_example_passes_contract_schemas():
    event = _load("examples/warning-raised.json")
    assert _validate(event) == []
