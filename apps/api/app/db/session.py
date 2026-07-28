from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    # Do not hold an OpenTelemetry context manager across the dependency
    # generator yield. FastAPI may resume cleanup in a different task/context.
    with SessionLocal() as session:
        yield session
