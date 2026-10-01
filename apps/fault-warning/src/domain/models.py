"""B 模块的持久化模型（SQLAlchemy 2.0 声明式）。

数据所有权（``docs/06`` 第 3 节）
--------------------------------
* B 是 ``WarningId``、健康结果、预警状态的**唯一权威方**；
* 设备档案只保存 ``equipmentId``，不复制设备主档；
* 工单只保存 ``linkedOrderId`` 关联，不读写工单表；
* 用户只保存 ``UserId`` 字符串，不复制用户表。

时间字段一律保存 UTC。SQLite 会丢弃时区信息，因此写出时统一通过
:func:`src.domain.ids.to_rfc3339` 归一化，读取到 naive 值时按 UTC 处理。
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

from src.domain.enums import OutboxStatus, WarningStatus

from .ids import utc_now

Base = declarative_base()


class Warning(Base):
    """一条故障预警，对应契约 ``Warning`` schema。"""

    __tablename__ = "warning"

    id = Column(Integer, primary_key=True)
    warning_id = Column(String(32), unique=True, index=True, nullable=False)
    equipment_id = Column(String(16), index=True, nullable=False)
    risk_level = Column(String(16), nullable=False)
    health_score = Column(Float, nullable=False)
    suspected_fault = Column(String(200), nullable=False)
    recommended_action = Column(String(500), nullable=False)
    status = Column(
        String(32), nullable=False, default=WarningStatus.OPEN.value, index=True
    )
    warning_at = Column(DateTime, nullable=False, index=True)
    model_version = Column(String(32), nullable=False)
    linked_order_id = Column(String(32), nullable=True, index=True)
    acknowledged_by = Column(String(64), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    history = relationship(
        "WarningStatusHistory",
        back_populates="warning",
        cascade="all, delete-orphan",
    )


class WarningStatusHistory(Base):
    """预警状态变更审计，用于证明"预警如何被关闭/修正/标注"。"""

    __tablename__ = "warning_status_history"

    id = Column(Integer, primary_key=True)
    warning_pk = Column(Integer, ForeignKey("warning.id"), nullable=False, index=True)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=False)
    action = Column(String(32), nullable=False)
    operator_id = Column(String(64), nullable=True)
    detail = Column(String(500), nullable=True)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    warning = relationship("Warning", back_populates="history")


class HealthEvaluation(Base):
    """一次健康评估的完整留证。

    无论是否触发预警都会留档，便于回溯"为什么没有建单"。
    ``evaluation_id`` 来自请求，作为该次评估的天然幂等键：
    重复提交同一 ``evaluationId`` 直接返回首次结果，不重新评分、不重复建预警。
    """

    __tablename__ = "health_evaluation"

    id = Column(Integer, primary_key=True)
    evaluation_id = Column(String(64), unique=True, index=True, nullable=False)
    equipment_id = Column(String(16), index=True, nullable=False)
    health_score = Column(Float, nullable=False)
    risk_level = Column(String(16), nullable=False)
    suspected_fault = Column(String(200), nullable=False)
    recommended_action = Column(String(500), nullable=False)
    model_version = Column(String(32), nullable=False)
    evaluated_at = Column(DateTime, nullable=False)
    requested_at = Column(DateTime, nullable=True)
    warning_id = Column(String(32), nullable=True, index=True)
    sample_json = Column(Text, nullable=False)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class MaintenanceConclusion(Base):
    """C 回传的维修结论留档。

    "同一 orderId 的最终结论不可被旧版本覆盖"（``docs/06`` 第 9 节）
    由用例按 ``completedAt`` 单调比较实现，见
    :func:`src.application.warning_service.consume_maintenance_conclusion`。

    这里刻意**不加** ``(order_id, completed_at)`` 唯一约束：
    重复结论应当被"忽略并留档"，而不是让一次合法重放退化成 500。
    """

    __tablename__ = "maintenance_conclusion"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    order_id = Column(String(32), index=True, nullable=False)
    warning_id = Column(String(32), nullable=True, index=True)
    equipment_id = Column(String(16), nullable=False)
    root_cause = Column(Text, nullable=False)
    measures = Column(Text, nullable=False)
    result = Column(String(32), nullable=False)
    effective = Column(Boolean, nullable=False)
    completed_at = Column(DateTime, nullable=False)
    submitted_by = Column(String(64), nullable=False)
    downtime_minutes = Column(Integer, nullable=True)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class OutboxEvent(Base):
    """待发送事件/通知（outbox 模式）。

    业务写入与"待发送"记录在**同一事务**内提交，
    投递失败不会回滚已成立的预警，可以稍后重试
    （``docs/06`` 第 10 节第 7 条）。
    """

    __tablename__ = "outbox_event"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    target_url = Column(String(255), nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(
        String(16), nullable=False, default=OutboxStatus.PENDING.value, index=True
    )
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(500), nullable=True)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class IdempotencyRecord(Base):
    """HTTP 层 Idempotency-Key 去重记录。

    ``request_fingerprint`` 保存完整 64 位 sha256（十六进制），
    列宽与之一致。
    """

    __tablename__ = "idempotency_record"

    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    response_body = Column(Text, nullable=False)
    http_status = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


# 同设备 + 同疑似故障的"仍在跟踪"预警查询
Index(
    "ix_warning_active_lookup",
    Warning.equipment_id,
    Warning.suspected_fault,
    Warning.status,
)

# 预留当日 WarningId 序号时按日期前缀查最大值
Index("ix_warning_id_prefix", Warning.warning_id)
