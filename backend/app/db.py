from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine_kwargs: dict[str, object] = {}
if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # A pooled connection to a real network database (Postgres) can go stale
    # while idle -- the server or an intermediate proxy closes it, and the
    # next checkout would otherwise fail with "server closed the connection
    # unexpectedly". pre_ping issues a cheap SELECT 1 before handing the
    # connection out and transparently reconnects if it's dead. SQLite is
    # in-process and never has this problem, so it's skipped there.
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
