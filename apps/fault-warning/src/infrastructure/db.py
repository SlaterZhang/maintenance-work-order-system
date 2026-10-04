"""数据库引擎与会话。"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import settings
from src.domain.models import Base

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    # SQLite 默认禁止跨线程复用连接，而 FastAPI 的依赖注入会在不同线程
    # 执行同步端点，因此必须放开；同时关闭同线程检查不会引入并发写问题，
    # 因为写操作统一在请求级 Session 内完成。
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """建表（幂等）。"""
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个 Session，结束时关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
