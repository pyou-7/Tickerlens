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


def test_ensure_schema_adds_skipped_quarters_column(tmp_path) -> None:
    # Batch 48: pre-existing DBs lack Company.xbrl_skipped_quarters; the
    # startup migration must add it so the middle-gap acknowledgment has
    # somewhere to persist.
    db = tmp_path / "old.db"
    engine = get_engine(f"sqlite:///{db}")
    create_tables(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE companies DROP COLUMN xbrl_skipped_quarters"))
    cols_before = {c["name"] for c in inspect(engine).get_columns("companies")}
    assert "xbrl_skipped_quarters" not in cols_before

    ensure_schema(engine)

    cols_after = {c["name"] for c in inspect(engine).get_columns("companies")}
    assert "xbrl_skipped_quarters" in cols_after


def test_ensure_schema_adds_redeemable_nci_column(tmp_path) -> None:
    # Batch 59: pre-existing DBs lack quarterly_financials.redeemable_nci;
    # the startup migration must add it so the mezzanine line persists.
    db = tmp_path / "old.db"
    engine = get_engine(f"sqlite:///{db}")
    create_tables(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE quarterly_financials DROP COLUMN redeemable_nci"))
    cols_before = {c["name"] for c in inspect(engine).get_columns("quarterly_financials")}
    assert "redeemable_nci" not in cols_before

    ensure_schema(engine)

    cols_after = {c["name"] for c in inspect(engine).get_columns("quarterly_financials")}
    assert "redeemable_nci" in cols_after


def test_ensure_schema_adds_temporary_equity_column(tmp_path) -> None:
    # Batch 83: pre-existing DBs lack quarterly_financials.temporary_equity;
    # the startup migration must add it so the mezzanine line persists.
    db = tmp_path / "old.db"
    engine = get_engine(f"sqlite:///{db}")
    create_tables(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE quarterly_financials DROP COLUMN temporary_equity"))
    cols_before = {c["name"] for c in inspect(engine).get_columns("quarterly_financials")}
    assert "temporary_equity" not in cols_before

    ensure_schema(engine)

    cols_after = {c["name"] for c in inspect(engine).get_columns("quarterly_financials")}
    assert "temporary_equity" in cols_after
