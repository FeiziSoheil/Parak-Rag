"""SQLAlchemy engine and session management."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DATABASE_URL

_connect_args = {}
if "sqlite" in DATABASE_URL:
    _connect_args["check_same_thread"] = False
    # زمان انتظار (ثانیه) وقتی دیتابیس قفل است؛ جلوی خطای "database is locked" را می‌گیرد
    _connect_args["timeout"] = 30

engine = create_engine(DATABASE_URL, connect_args=_connect_args or {})


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """برای SQLite حالت WAL را فعال می‌کنیم تا هم‌زمانی خواندن/نوشتن بهتر شود."""
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 ثانیه (میلی‌ثانیه)
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
