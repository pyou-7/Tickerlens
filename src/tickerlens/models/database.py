from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tickerlens.config import get_settings
from tickerlens.models.base import Base

# Import models so Base.metadata is populated before create_all / autogenerate
import tickerlens.models.company  # noqa: F401
import tickerlens.models.quarterly_financial  # noqa: F401


def get_engine(url: str | None = None) -> Engine:
    db_url = url or get_settings().database_url
    return create_engine(db_url, echo=False)


def get_session(engine: Engine | None = None) -> Session:
    eng = engine or get_engine()
    factory = sessionmaker(bind=eng)
    return factory()


def create_tables(engine: Engine | None = None) -> None:
    """Create all tables (idempotent). Used in tests and first-run setup."""
    Base.metadata.create_all(engine or get_engine())
