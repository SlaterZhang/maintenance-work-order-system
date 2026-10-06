from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.domain.models import Base, Equipment
from src.infrastructure.seed import SEED_EQUIPMENT, seed_telemetry

engine = create_engine(
    settings.member_a_database_url,
    connect_args={"check_same_thread": False}
    if settings.member_a_database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def seed_equipment(db) -> None:
    if db.query(Equipment).count() > 0:
        return
    for item in SEED_EQUIPMENT:
        db.add(Equipment(**item))
    db.commit()
    # 阶段3：设备档案首次落库时同步补 72 小时遥测历史（趋势预测演示数据）
    seed_telemetry(db)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
