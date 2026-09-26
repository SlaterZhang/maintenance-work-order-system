import httpx

from src.config import settings


def send_warning_raised(event: dict, trace_id: str) -> dict:
    url = f"{settings.member_c_base}/api/v1/integration/warning-events"
    headers = {
        "X-Trace-Id": trace_id,
        "Idempotency-Key": event["eventId"],
        "X-Internal-Token": settings.internal_api_token,
    }
    with httpx.Client(timeout=3.0) as client:
        response = client.post(url, json=event, headers=headers)
    body = None
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    return {"status": response.status_code, "body": body, "url": url}
