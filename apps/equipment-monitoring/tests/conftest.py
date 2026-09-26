import os
import tempfile
from pathlib import Path

_TEST_DB = (Path(tempfile.gettempdir()) / "member_a_test.db").as_posix()
os.environ.setdefault("MEMBER_A_DATABASE_URL", f"sqlite:///{_TEST_DB}")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from src.infrastructure.db import SessionLocal, engine, seed_equipment
    from src.domain.models import Base

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_equipment(db)

    from src.main import app

    with TestClient(app) as test_client:
        yield test_client
