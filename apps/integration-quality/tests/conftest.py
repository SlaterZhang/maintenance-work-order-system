import os
import tempfile
from pathlib import Path

_TEST_DB = (Path(tempfile.gettempdir()) / "member_d_test.db").as_posix()
os.environ.setdefault("MEMBER_D_DATABASE_URL", f"sqlite:///{_TEST_DB}")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from src.domain.models import Base
    from src.infrastructure.db import SessionLocal, engine, seed_users

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_users(db)

    from src.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    from src.infrastructure.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
