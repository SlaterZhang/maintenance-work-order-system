import hashlib
import json
from sqlalchemy.orm import Session
from src.domain.models import IdempotencyRecord
from src.domain.errors import IdempotencyConflictError


def fingerprint(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:128]


def check_and_store(db: Session, key: str, payload: dict) -> dict | None:
    """
    返回 None 表示首次请求，继续执行；
    返回 dict 表示命中幂等，直接返回缓存响应。
    抛 IdempotencyConflictError 表示同 key 不同体。
    """
    fp = fingerprint(payload)
    record = db.query(IdempotencyRecord).filter(
        IdempotencyRecord.idempotency_key == key
    ).first()
    if record is None:
        return None
    if record.request_fingerprint != fp:
        raise IdempotencyConflictError()
    return json.loads(record.response_body)


def store_response(db: Session, key: str, payload: dict,
                   response_body: dict, status: int):
    db.add(IdempotencyRecord(
        idempotency_key=key,
        request_fingerprint=fingerprint(payload),
        response_body=json.dumps(response_body, default=str),
        http_status=status,
    ))