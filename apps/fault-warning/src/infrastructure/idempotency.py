"""HTTP 层 Idempotency-Key 去重。

契约（``docs/06`` 第 11.1 节）
-----------------------------
* 同一 ``Idempotency-Key`` + 相同方法/路径/请求体：返回**第一次的状态码与响应体**；
* 同一 ``Idempotency-Key`` 但请求体不同：409 ``IDEMPOTENCY_CONFLICT``。

与成员 C 实现的两点差异
-----------------------
1. :meth:`IdempotencyContext.remember` **只登记不提交**，
   由用例在同一事务内与业务写入一起 commit，
   消除"业务已提交、幂等记录因第二次 commit 失败而丢失"的窗口；
2. :class:`ReplayResult` 带回原始 HTTP 状态码，
   命中幂等的 201 请求不会错误地退化成 200。
"""

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.domain.errors import IdempotencyConflictError
from src.domain.models import IdempotencyRecord


def fingerprint(payload: object) -> str:
    """请求体的稳定指纹（sha256 十六进制，64 字符，与列宽一致）。"""
    raw = json.dumps(
        payload, sort_keys=True, default=str, ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ReplayResult:
    """命中幂等时应当原样返回的响应。"""

    http_status: int
    body: dict


@dataclass(frozen=True)
class IdempotencyContext:
    """一次写请求的幂等上下文。

    由 HTTP 层构造并传入用例，使用例能在**自己的事务**里登记响应，
    而不是等用例提交后再补一次 commit。
    """

    key: str
    raw_body: object

    def replay(self, db: Session) -> ReplayResult | None:
        """命中幂等则返回缓存响应；未命中返回 ``None``；同键不同体抛 409。"""
        record = (
            db.query(IdempotencyRecord)
            .filter(IdempotencyRecord.idempotency_key == self.key)
            .first()
        )
        if record is None:
            return None
        if record.request_fingerprint != fingerprint(self.raw_body):
            raise IdempotencyConflictError()
        return ReplayResult(
            http_status=record.http_status,
            body=json.loads(record.response_body),
        )

    def remember(
        self, db: Session, response_body: dict, http_status: int
    ) -> IdempotencyRecord:
        """登记幂等记录。**不提交**，由调用方与业务写入同事务提交。"""
        record = IdempotencyRecord(
            idempotency_key=self.key,
            request_fingerprint=fingerprint(self.raw_body),
            response_body=json.dumps(
                response_body, default=str, ensure_ascii=False
            ),
            http_status=http_status,
        )
        db.add(record)
        return record
