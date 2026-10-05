from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tickerlens.config import get_settings
from tickerlens.models.base import Base

# Import models so Base.metadata is populated before create_all / autogenerate
import tickerlens.models.company  # noqa: F401
import tickerlens.models.quarterly_financial  # noqa: F401
import tickerlens.models.valuation_history  # noqa: F401


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


def ensure_schema(engine: Engine | None = None) -> None:
    """Add any model columns missing from existing tables (light migration).

    ``create_all`` only creates missing *tables*; when a feature commit adds
    columns to an existing table (e.g. disclosures on quarterly_financials),
    older databases would crash with "no such column". This inspects each
    known table and ALTERs in whatever is missing. All app columns are
    nullable, which SQLite's ADD COLUMN supports. Never raises.
    """
    eng = engine or get_engine()
    try:
        inspector = inspect(eng)
        with eng.begin() as conn:
            for table in Base.metadata.sorted_tables:
                existing = {c["name"] for c in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name not in existing:
                        ddl = (
                            f"ALTER TABLE {table.name} "
                            f"ADD COLUMN {column.name} "
                            f"{column.type.compile(dialect=eng.dialect)}"
                        )
                        conn.execute(text(ddl))
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Schema migration check failed", exc_info=True
        )
