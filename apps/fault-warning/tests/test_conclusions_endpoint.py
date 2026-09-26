import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"
EXAMPLE_PATH = CONTRACTS_DIR / "examples" / "maintenance-conclusion.json"
CONCLUSION_PATH = "/api/v1/integration/maintenance-conclusions"
INTERNAL_TOKEN = "dev-internal-token-change-me"


def load_contract_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def post_conclusion(client: TestClient, event: dict, idem_key: str | None = None,
                    token: str | None = INTERNAL_TOKEN):
    headers = {"X-Trace-Id": "trace-20260917-001"}
    if token is not None:
        headers["X-Internal-Token"] = token
    headers["Idempotency-Key"] = idem_key or event["eventId"]
    return client.post(CONCLUSION_PATH, json=event, headers=headers)


def seed_warning(db: Session, warning_id: str = "WARN-20260917-0001") -> None:
    from src.domain.models import Warning

    db.add(
        Warning(
            warning_id=warning_id,
            equipment_id="EQ-000001",
            risk_level="HIGH",
            health_score=42.5,
            suspected_fault="主轴轴承振动异常",
            recommended_action="建议停机检查主轴轴承及润滑状态",
            status="OPEN",
            warning_at=datetime(2026, 9, 17, 8, 29, 55, tzinfo=timezone.utc),
            model_version="rule-engine-1.0.0",
        )
    )
    db.commit()


def test_contract_example_accepted_and_resolves_warning(client: TestClient, db: Session):
    seed_warning(db)
    event = load_contract_example()
    response = post_conclusion(client, event)
    assert response.status_code == 202
    assert response.json() == {"accepted": True, "duplicate": False, "traceId": "trace-20260917-001"}

    from src.domain.models import Warning

    warning = db.query(Warning).filter_by(warning_id="WARN-20260917-0001").first()
    assert warning.status == "RESOLVED"


def test_duplicate_event_id_is_idempotent(client: TestClient, db: Session):
    seed_warning(db)
    event = load_contract_example()
    first = post_conclusion(client, event)
    assert first.status_code == 202
    second = post_conclusion(client, event)
    assert second.status_code == 202
    assert second.json()["duplicate"] is True


def test_unknown_warning_returns_404(client: TestClient):
    event = load_contract_example()
    response = post_conclusion(client, event)
    assert response.status_code == 404
    assert response.json()["code"] == "WARNING_NOT_FOUND"


def test_null_warning_id_accepted(client: TestClient):
    event = load_contract_example()
    event["payload"]["warningId"] = None
    response = post_conclusion(client, event)
    assert response.status_code == 202
    assert response.json()["accepted"] is True


def test_missing_submitted_by_rejected(client: TestClient, db: Session):
    seed_warning(db)
    event = load_contract_example()
    del event["payload"]["submittedBy"]
    response = post_conclusion(client, event)
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_invalid_token_rejected(client: TestClient):
    event = load_contract_example()
    response = post_conclusion(client, event, token="wrong-token")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
