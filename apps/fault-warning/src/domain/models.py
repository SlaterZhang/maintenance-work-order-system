from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class Warning(Base):
    __tablename__ = "warning"

    id = Column(Integer, primary_key=True)
    warning_id = Column(String(32), unique=True, index=True, nullable=False)
    equipment_id = Column(String(16), index=True, nullable=False)
    risk_level = Column(String(16), nullable=False)
    health_score = Column(Float, nullable=False)
    suspected_fault = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="OPEN")
    warning_at = Column(DateTime, nullable=False)
    model_version = Column(String(32), nullable=False)
    linked_order_id = Column(String(32), nullable=True)
    event_sent = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class HealthEvaluation(Base):
    __tablename__ = "health_evaluation"

    id = Column(Integer, primary_key=True)
    evaluation_id = Column(String(64), unique=True, index=True, nullable=False)
    equipment_id = Column(String(16), index=True, nullable=False)
    response_body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class MaintenanceConclusionEvent(Base):
    __tablename__ = "maintenance_conclusion_event"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    warning_id = Column(String(32), nullable=True)
    order_id = Column(String(32), nullable=False)
    result = Column(String(32), nullable=False)
    effective = Column(Boolean, nullable=False)
    payload = Column(Text, nullable=False)
    trace_id = Column(String(64), nullable=True)
    received_at = Column(DateTime, default=utcnow, nullable=False)
