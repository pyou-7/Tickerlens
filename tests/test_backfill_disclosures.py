"""Tests for scripts/backfill_disclosures.py cohort selectors (batch 96)."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "backfill_disclosures.py"
    spec = importlib.util.spec_from_file_location("backfill_disclosures", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Col:
    """Stub column: ``_Col('cik') == value`` yields a row predicate."""

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):  # noqa: D105
        return lambda row: getattr(row, self.name) == other

    def __hash__(self):
        return hash(self.name)


class _Row:
    def __init__(self, cik, highlights):
        self.cik = cik
        self.press_release_highlights = highlights


class _Company:
    def __init__(self, ticker, cik):
        self.ticker = ticker
        self.cik = cik


class _Query:
    def __init__(self, items):
        self._items = list(items)

    def order_by(self, *_):
        return self

    def filter(self, predicate):
        return _Query([i for i in self._items if predicate(i)])

    def all(self):
        return list(self._items)


def _run_selector(mod, companies_rows, selector):
    """Run a selector over in-memory fakes.

    companies_rows: list of (ticker, cik, [highlights per quarter]).
    """
    companies = [_Company(t, c) for t, c, _ in companies_rows]
    rows = [_Row(c, h) for _, c, hs in companies_rows for h in hs]

    class FakeCompany:
        ticker = _Col("ticker")
        cik = _Col("cik")

    class FakeQF:
        cik = _Col("cik")

    class FakeSession:
        def query(self, model):
            if model is FakeCompany:
                return _Query(companies)
            if model is FakeQF:
                return _Query(rows)
            raise AssertionError(model)

    orig_company, orig_qf = mod.Company, mod.QuarterlyFinancial
    mod.Company, mod.QuarterlyFinancial = FakeCompany, FakeQF
    try:
        return selector(FakeSession())
    finally:
        mod.Company, mod.QuarterlyFinancial = orig_company, orig_qf


def test_partial_selector_includes_only_partials():
    mod = _load_script()
    rows = [
        ("AAA", "1", ["h", None, None]),   # partial -> included
        ("BBB", "2", [None, None, None]),  # zero -> excluded
        ("CCC", "3", ["h", "h", "h"]),      # full -> excluded
        ("DDD", "4", ["[]", "h", None]),    # partial ("[]" counts as empty) -> included
        ("EEE", "5", ["[]", "[]", "[]"]),   # all "[]" -> zero cohort -> excluded
        ("FFF", "6", []),                   # no rows -> excluded
    ]
    got = _run_selector(mod, rows, mod._partial_highlight_tickers)
    assert sorted(t for t, _ in got) == ["AAA", "DDD"]
    assert all(isinstance(cik, str) for _, cik in got)


def test_zero_selector_still_excludes_partials():
    mod = _load_script()
    rows = [
        ("AAA", "1", ["h", None, None]),  # partial -> excluded from zero
        ("BBB", "2", [None, None, None]),  # zero -> included
        # Note: the pre-existing zero selector treats a literal "[]" row as
        # content (only "" / whitespace count as empty); the partial selector
        # follows _filled_count and treats "[]" as empty. "[]" rows are
        # produced by the extractor, so EEE sits in neither cohort — that
        # pre-existing inconsistency is out of scope for this batch.
        ("EEE", "5", ["[]", "[]"]),  # -> excluded from zero (pre-existing semantics)
    ]
    got = _run_selector(mod, rows, mod._zero_highlight_tickers)
    assert sorted(t for t, _ in got) == ["BBB"]


def test_cli_cohort_flag_choices():
    mod = _load_script()
    import argparse
    import inspect

    src = inspect.getsource(mod.main)
    assert '"partial"' in src and '"zero"' in src
