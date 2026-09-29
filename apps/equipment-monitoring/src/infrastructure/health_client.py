from __future__ import annotations

from typing import Protocol

import httpx

from src.domain.models import HealthEvaluationRequest, HealthEvaluationResponse


class HealthEvaluationClient(Protocol):
    def evaluate(
        self,
        request: HealthEvaluationRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> HealthEvaluationResponse:
        ...


class HttpHealthEvaluationClient:
    def __init__(
        self,
        base_url: str,
        internal_api_token: str | None,
        timeout_seconds: float,
    ) -> None:
        self.url = f"{base_url.rstrip('/')}/api/v1/health-evaluations"
        self.internal_api_token = internal_api_token
        self.timeout_seconds = timeout_seconds

    def evaluate(
        self,
        request: HealthEvaluationRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> HealthEvaluationResponse:
        headers = {
            "X-Trace-Id": trace_id,
            "Idempotency-Key": idempotency_key,
        }
        if self.internal_api_token:
            headers["X-Internal-Token"] = self.internal_api_token
        response = httpx.post(
            self.url,
            json=request.model_dump(mode="json"),
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return HealthEvaluationResponse.model_validate(response.json())
