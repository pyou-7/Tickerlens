"""Tests for the lightweight schema migration (ensure_schema)."""

from __future__ import annotations

from sqlalchemy import inspect, text

from tickerlens.models.database import create_tables, ensure_schema, get_engine


def test_ensure_schema_adds_missing_columns(tmp_path) -> None:
    # Simulate a pre-disclosures database: create tables, then drop the
    # four disclosure columns Gemini's commit added without a migration.
    db = tmp_path / "old.db"
    engine = get_engine(f"sqlite:///{db}")
    create_tables(engine)
    with engine.begin() as conn:
        for col in (
            "management_guidance",
            "management_guidance_source",
            "transcript_excerpts",
            "transcript_source",
        ):
            conn.execute(text(f"ALTER TABLE quarterly_financials DROP COLUMN {col}"))
    cols_before = {c["name"] for c in inspect(engine).get_columns("quarterly_financials")}
    assert "management_guidance" not in cols_before

    ensure_schema(engine)

    cols_after = {c["name"] for c in inspect(engine).get_columns("quarterly_financials")}
    assert "management_guidance" in cols_after
    assert "transcript_source" in cols_after


def test_ensure_schema_is_idempotent(tmp_path) -> None:
    db = tmp_path / "fresh.db"
    engine = get_engine(f"sqlite:///{db}")
    create_tables(engine)
    ensure_schema(engine)  # no missing columns — must be a harmless no-op
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("quarterly_financials")}
    assert "management_guidance" in cols
