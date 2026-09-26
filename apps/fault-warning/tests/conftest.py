import os
import tempfile
from pathlib import Path

_TEST_DB = (Path(tempfile.gettempdir()) / "member_b_test.db").as_posix()
os.environ.setdefault("MEMBER_B_DATABASE_URL", f"sqlite:///{_TEST_DB}")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from src.config import settings
    from src.domain.models import Base
    from src.infrastructure.db import SessionLocal, engine

    settings.member_c_base = "http://127.0.0.1:1"
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

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
