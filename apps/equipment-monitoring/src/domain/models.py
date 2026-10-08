from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True)
    equipment_id = Column(String(16), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    equipment_type = Column(String(50), nullable=False)
    production_line_id = Column(String(32), nullable=False)
    location = Column(String(100), nullable=False)
    manufacturer = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    responsible_department = Column(String(100), nullable=True)
    current_status = Column(String(32), nullable=False, default="RUNNING")
    enabled = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class EquipmentStatusEvent(Base):
    __tablename__ = "equipment_status_event"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    order_id = Column(String(32), index=True, nullable=False)
    equipment_id = Column(String(16), index=True, nullable=False)
    target_status = Column(String(32), nullable=False)
    operator_id = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    occurred_at = Column(DateTime, nullable=False)
    trace_id = Column(String(64), nullable=True)
    received_at = Column(DateTime, default=utcnow, nullable=False)


class TelemetryBatch(Base):
    __tablename__ = "telemetry_batch"

    id = Column(Integer, primary_key=True)
    batch_id = Column(String(64), unique=True, index=True, nullable=False)
    equipment_id = Column(String(16), index=True, nullable=False)
    source = Column(String(32), nullable=False)
    accepted_count = Column(Integer, nullable=False, default=0)
    received_at = Column(DateTime, default=utcnow, nullable=False)


class TelemetrySampleRecord(Base):
    __tablename__ = "telemetry_sample"

    id = Column(Integer, primary_key=True)
    sample_id = Column(String(64), unique=True, index=True, nullable=False)
    equipment_id = Column(String(16), index=True, nullable=False)
    measured_at = Column(DateTime, index=True, nullable=False)
    temperature_c = Column(Float, nullable=False)
    vibration_mm_s = Column(Float, nullable=False)
    current_a = Column(Float, nullable=False)
    rotational_speed_rpm = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
