import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.domain.models import Base, User
from src.infrastructure.seed import SEED_USERS

engine = create_engine(
    settings.member_d_database_url,
    connect_args={"check_same_thread": False}
    if settings.member_d_database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def seed_users(db) -> None:
    if db.query(User).count() > 0:
        return
    for item in SEED_USERS:
        db.add(
            User(
                user_id=item["user_id"],
                display_name=item["display_name"],
                role_codes=json.dumps(item["role_codes"]),
                permissions=json.dumps(item["permissions"]),
                organization=item["organization"],
                enabled=item["enabled"],
            )
        )
    db.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
