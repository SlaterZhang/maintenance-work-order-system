from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "app_user"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(32), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    role_codes = Column(Text, nullable=False)
    permissions = Column(Text, nullable=False)
    organization = Column(String(100), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class NotificationTask(Base):
    __tablename__ = "notification_task"

    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=False)
    notification_id = Column(String(32), nullable=False)
    payload = Column(Text, nullable=False)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
