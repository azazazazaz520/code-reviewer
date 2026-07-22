from datetime import datetime, UTC

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator, DateTime

from app.config import settings


class UTCDateTime(TypeDecorator):
    """SQLite 兼容的 UTC 时间类型 — 读写时自动补上/保持 UTC 时区。

    SQLite 无法存储时区信息，naive datetime 存入后读回时丢失时区。
    此类型确保读出的 datetime 始终带有 UTC 时区标记，
    Pydantic 序列化时输出 ``Z`` 后缀，前端正确处理。
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)

# SQLite 默认不启用外键约束，需要手动开启
if "sqlite" in settings.database_url:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
