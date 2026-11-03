"""Batch 99: predecessor-CIK submissions merge in discover_earnings_filings.

SEC moves a ticker to a new CIK on a reorganization (XOM -> 0002115436) and
the new CIK's submissions feed starts at the succession, so pre-succession
earnings 8-Ks live only under the predecessor CIK. Discovery must merge the
predecessor feed, dedupe accession collisions to the current CIK's copy, and
build the exhibit/filing-index URLs under the 8-K's own source CIK.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from tickerlens.services.ir_download import (
    EarningsPeriod,
    _find_ex99_doc,
    discover_earnings_filings,
    er_doc_url,
    sec_doc_url,
)

CUR = "0002115436"   # XOM's current CIK
PRED = "0000034088"  # XOM's predecessor CIK


def _block(rows):
    """rows: (form, accession, report, filed, items, doc)."""
    return {
        "form": [r[0] for r in rows],
        "accessionNumber": [r[1] for r in rows],
        "reportDate": [r[2] for r in rows],
        "filingDate": [r[3] for r in rows],
        "items": [r[4] for r in rows],
        "primaryDocument": [r[5] for r in rows],
    }


def _payload(rows):
    return {"filings": {"recent": _block(rows), "files": []}}


def _xom_client():
    """Current feed: newest 10-Q (+ its 8-K). Predecessor feed: the newest
    10-Q again (dual-attributed, same accession) plus the older quarter."""
    cur_rows = [
        ("10-Q", "0002115436-26-000010", "2026-06-30", "2026-08-05", "", "xom-20260630.htm"),
        ("8-K", "0002115436-26-000011", "2026-08-04", "2026-08-04", "2.02", "xom-8k.htm"),
    ]
    pred_rows = [
        ("10-Q", "0002115436-26-000010", "2026-06-30", "2026-08-05", "", "xom-20260630.htm"),
        ("10-Q", "0000034088-26-000100", "2026-03-31", "2026-05-05", "", "xom-20260331.htm"),
        ("8-K", "0000034088-26-000101", "2026-05-04", "2026-05-04", "2.02", "xom-q1-8k.htm"),
    ]
    feeds = {CUR: _payload(cur_rows), PRED: _payload(pred_rows)}
    client = MagicMock()
    client.cik_for_ticker.return_value = CUR
    client.submissions.side_effect = lambda cik, **kw: feeds[cik]
    client.filing_index_url.side_effect = lambda cik, acc: f"https://x/{cik}/{acc}/"
    client.fetch_text.return_value = "<html></html>"
    return client


@pytest.fixture
def with_predecessor(monkeypatch):
    monkeypatch.setattr(
        "tickerlens.services.ir_download.predecessor_ciks",
        lambda cik: (PRED,) if cik == CUR else (),
    )


def test_discover_merges_predecessor_8k(with_predecessor):
    # The older quarter's earnings 8-K lives only under the predecessor CIK.
    periods = discover_earnings_filings("XOM", _xom_client(), n_quarters=2)
    assert [p.period_end for p in periods] == [date(2026, 3, 31), date(2026, 6, 30)]
    q1, q2 = periods
    assert q1.er_accession == "0000034088-26-000101"
    assert q1.er_cik == PRED
    assert q2.er_accession == "0002115436-26-000011"
    assert q2.er_cik == CUR


def test_discover_dedupes_dual_attributed_filing_to_current_cik(with_predecessor):
    # The newest 10-Q is attributed to BOTH CIKs (same accession) — the
    # current CIK's copy must win so sec_cik points at the live archives path.
    periods = discover_earnings_filings("XOM", _xom_client(), n_quarters=2)
    assert periods[1].sec_accession == "0002115436-26-000010"
    assert periods[1].sec_cik == CUR


def test_discover_fetches_both_feeds(with_predecessor):
    client = _xom_client()
    discover_earnings_filings("XOM", client, n_quarters=2)
    fetched = {c.args[0] for c in client.submissions.call_args_list}
    assert fetched == {CUR, PRED}


def test_discover_predecessor_fetch_failure_survives(with_predecessor):
    # A dead predecessor feed must not break discovery for the current CIK.
    client = _xom_client()
    feeds = {CUR: _payload([
        ("10-Q", "acc-q2", "2026-06-30", "2026-08-05", "", "d.htm"),
    ])}
    client.submissions.side_effect = lambda cik, **kw: feeds[cik]
    periods = discover_earnings_filings("XOM", client, n_quarters=1)
    assert [p.period_end for p in periods] == [date(2026, 6, 30)]


def test_discover_no_predecessor_single_submissions_call():
    # The real _CIK_SUCCESSIONS map has no entry for this CIK — one fetch.
    client = MagicMock()
    client.cik_for_ticker.return_value = "0000001"
    client.submissions.return_value = _payload([
        ("10-Q", "acc-0", "2026-06-30", "2026-07-30", "", "d0.htm"),
    ])
    periods = discover_earnings_filings("FAKE", client, n_quarters=1)
    assert client.submissions.call_count == 1
    assert len(periods) == 1
    assert periods[0].sec_cik == "0000001"
    assert periods[0].er_cik is None  # no 8-K matched


def test_find_ex99_doc_uses_8k_source_cik():
    client = MagicMock()
    client.filing_index_url.return_value = "https://x/"
    client.fetch_text.return_value = '<html><a href="ex991q1.htm">release</a></html>'
    matched = {
        "accession": "0000034088-26-000101",
        "src_cik": PRED,
        "primary_doc": "xom-q1-8k.htm",
        "items": "2.02",
    }
    assert _find_ex99_doc(CUR, matched, client) == "ex991q1.htm"
    # The filing index was fetched under the predecessor CIK, not CUR.
    assert client.filing_index_url.call_args[0] == (PRED, "0000034088-26-000101")


def test_find_ex99_doc_falls_back_to_passed_cik():
    client = MagicMock()
    client.filing_index_url.return_value = "https://x/"
    client.fetch_text.return_value = "<html></html>"
    matched = {"accession": "acc-9", "primary_doc": "d.htm", "items": "2.02"}
    assert _find_ex99_doc(CUR, matched, client) is None
    assert client.filing_index_url.call_args[0] == (CUR, "acc-9")


def _period(**kw):
    base = dict(
        quarter_label="Q1 FY2026",
        fiscal_year="FY2026",
        fp="Q1",
        fy=2026,
        period_end=date(2026, 3, 31),
        sec_form="10-Q",
        sec_accession="0000034088-26-000100",
        sec_doc="xom-20260331.htm",
        er_accession="0000034088-26-000101",
        er_doc="ex991q1.htm",
    )
    base.update(kw)
    return EarningsPeriod(**base)


def test_er_doc_url_prefers_er_cik():
    url = er_doc_url(CUR, _period(er_cik=PRED))
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/34088/"
        "000003408826000101/ex991q1.htm"
    )
    # Without a carried CIK, the passed CIK is used (unchanged behavior).
    url = er_doc_url(CUR, _period(er_cik=None))
    assert "/data/2115436/" in url
    assert er_doc_url(CUR, _period(er_accession=None)) is None


def test_sec_doc_url_prefers_sec_cik():
    url = sec_doc_url(CUR, _period(sec_cik=PRED))
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/34088/"
        "000003408826000100/xom-20260331.htm"
    )
    url = sec_doc_url(CUR, _period(sec_cik=None))
    assert "/data/2115436/" in url
