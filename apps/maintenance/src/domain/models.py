from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, ForeignKey, Text, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class WorkOrder(Base):
    __tablename__ = "work_order"

    id = Column(Integer, primary_key=True)
    order_id = Column(String(32), unique=True, index=True, nullable=False)
    source_type = Column(String(16), nullable=False)
    warning_id = Column(String(32), index=True, nullable=True)
    equipment_id = Column(String(16), index=True, nullable=False)
    equipment_name_snapshot = Column(String(100), nullable=False)
    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(4), nullable=False)
    status = Column(String(32), nullable=False, default="PENDING_CONFIRMATION")
    reporter_id = Column(String(64), nullable=False)
    assignee_id = Column(String(64), nullable=True)
    due_at = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=0)

    # 维修结论字段
    root_cause = Column(Text, nullable=True)
    measures = Column(Text, nullable=True)
    maintenance_result = Column(String(32), nullable=True)
    effective = Column(Boolean, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    downtime_minutes = Column(Integer, nullable=True)
    concluded_by = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    spare_requests = relationship("SpareRequest", back_populates="order",
                                  cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="order",
                              cascade="all, delete-orphan")
    assign_history = relationship("AssignmentHistory", back_populates="order",
                                  cascade="all, delete-orphan")


class AssignmentHistory(Base):
    __tablename__ = "assignment_history"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("work_order.id"))
    from_user = Column(String(64), nullable=True)
    to_user = Column(String(64), nullable=False)
    operator_id = Column(String(64), nullable=False)
    comment = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    order = relationship("WorkOrder", back_populates="assign_history")


class SparePart(Base):
    __tablename__ = "spare_part"
    id = Column(Integer, primary_key=True)
    spare_part_id = Column(String(16), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    specification = Column(String(200), nullable=False)
    unit = Column(String(20), nullable=False, default="个")
    on_hand_quantity = Column(Integer, nullable=False, default=0)
    reserved_quantity = Column(Integer, nullable=False, default=0)
    reorder_point = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=0)

    @property
    def available_quantity(self) -> int:
        return self.on_hand_quantity - self.reserved_quantity


class SpareRequest(Base):
    __tablename__ = "spare_request"
    id = Column(Integer, primary_key=True)
    request_id = Column(String(32), unique=True, index=True, nullable=False)
    order_id = Column(Integer, ForeignKey("work_order.id"), nullable=False)
    spare_part_id = Column(Integer, ForeignKey("spare_part.id"), nullable=False)
    requested_quantity = Column(Integer, nullable=False)
    approved_quantity = Column(Integer, nullable=False, default=0)
    issued_quantity = Column(Integer, nullable=False, default=0)
    returned_quantity = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="PENDING_APPROVAL")
    requester_id = Column(String(64), nullable=False)
    approver_id = Column(String(64), nullable=True)
    reason = Column(String(500), nullable=True)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    order = relationship("WorkOrder", back_populates="spare_requests")


class InventoryTransaction(Base):
    __tablename__ = "inventory_transaction"
    id = Column(Integer, primary_key=True)
    spare_part_id = Column(Integer, ForeignKey("spare_part.id"), nullable=False)
    request_id = Column(Integer, ForeignKey("spare_request.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("work_order.id"), nullable=True)
    tx_type = Column(String(16), nullable=False)  # RESERVE/RELEASE/ISSUE/RETURN/SCRAP
    quantity = Column(Integer, nullable=False)
    operator_id = Column(String(64), nullable=False)
    batch_no = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utcnow)


class ProcessedEvent(Base):
    """幂等：EventId 去重"""
    __tablename__ = "processed_event"
    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    event_type = Column(String(64), nullable=False)
    result_ref = Column(String(64), nullable=True)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utcnow)


class IdempotencyRecord(Base):
    """HTTP 层 Idempotency-Key 去重"""
    __tablename__ = "idempotency_record"
    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=False)
    request_fingerprint = Column(String(128), nullable=False)
    response_body = Column(Text, nullable=False)
    http_status = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("work_order.id"), nullable=True)
    action = Column(String(64), nullable=False)
    operator_id = Column(String(64), nullable=False)
    before_value = Column(String(255), nullable=True)
    after_value = Column(String(255), nullable=True)
    detail = Column(Text, nullable=True)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    order = relationship("WorkOrder", back_populates="audit_logs")


Index("ix_work_order_warning_active", WorkOrder.warning_id, WorkOrder.status)