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
    """补齐种子设备（逐台幂等）并为其生成 72 小时遥测历史。

    逐台判断而非"表为空才播种"：设备是主数据，后续版本扩充种子清单时
    （2026-10-10 由 3 台扩到 8 台）应当**只补新增的**，不覆盖演示库中
    已被重置/演示改过的存量设备，也不重复补遥测。
    """
    existing = {
        row[0] for row in db.query(Equipment.equipment_id).all()
    }
    added = False
    for item in SEED_EQUIPMENT:
        if item["equipment_id"] in existing:
            continue
        db.add(Equipment(**item))
        added = True
    if added:
        db.commit()
    # 阶段3：为尚无遥测样本的种子设备补 72 小时历史（趋势预测演示数据）
    seed_telemetry(db)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
