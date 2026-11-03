"""Batch 103: 6-K earnings-release discovery for foreign filers.

SHOP's Q3-2024 quarter (period end 2024-09-30) had no 10-Q in the
submissions feed's recent window and no paginated buckets — but its earnings
release IS in the feed as a 6-K (``form6kq32024pressrelease.htm``, accession
``0001594805-24-000089``; the real EX-99.1 exhibit is the oddly-named
``a3pr.htm``). These tests pin the 6-K anchor + 6-K fallback machinery that
rescues it, and the guards that keep non-earnings 6-Ks out.
"""

from datetime import date
from unittest.mock import MagicMock

from tickerlens.services.ir_download import (
    _extract_6ks,
    _extract_er_8ks,
    _extract_sec_filings,
    _is_er_6k_anchor,
    _match_8k_non202_fallback,
    _quarter_tokens,
    _release_name_rank,
    discover_earnings_filings,
)


def test_quarter_tokens_shape():
    toks = _quarter_tokens(date(2024, 9, 30))
    assert "q32024" in toks and "q324" in toks
    assert "2024q3" in toks and "fy24q3" in toks
    assert "q42024" not in toks


def test_is_er_6k_anchor():
    # SHOP's earnings 6-Ks: quarter token + quarter-end reportDate.
    assert _is_er_6k_anchor("form6kq32024pressrelease.htm", date(2024, 9, 30))
    assert _is_er_6k_anchor("form6k-q32024results.htm", date(2024, 9, 30))
    # AGM results: no quarter token.
    assert not _is_er_6k_anchor("form6k-2024agmresults.htm", date(2024, 6, 4))
    # BFCM press release: no quarter token.
    assert not _is_er_6k_anchor("form6k-bfcmclosepressrelea.htm", date(2024, 12, 3))
    # Dividend 6-K: quarter token but event-dated (not month-end).
    assert not _is_er_6k_anchor("form6k-q42024dividend.htm", date(2024, 12, 5))
    # Annual-report 6-K: no quarter token for its report quarter.
    assert not _is_er_6k_anchor("form6k-2024annualreport.htm", date(2023, 12, 31))


def _shop_like_recent():
    return {
        "form": ["10-Q", "6-K", "6-K"],
        "accessionNumber": ["acc-10q", "acc-6k-pr", "acc-6k-agm"],
        "reportDate": ["2025-03-31", "2024-09-30", "2024-06-04"],
        "filingDate": ["2025-05-08", "2024-11-12", "2024-06-05"],
        "primaryDocument": [
            "shop-20250331.htm",
            "form6kq32024pressrelease.htm",
            "form6k-2024agmresults.htm",
        ],
        "items": ["", "", ""],
    }


def test_extract_sec_filings_includes_6k_anchors():
    sec = _extract_sec_filings(_shop_like_recent(), src_cik="0001594805")
    by_acc = {f["accession"]: f for f in sec}
    assert by_acc["acc-10q"]["form"] == "10-Q"
    anchor = by_acc["acc-6k-pr"]
    assert anchor["form"] == "6-K"
    assert anchor["report_date"] == date(2024, 9, 30)
    assert anchor["src_cik"] == "0001594805"
    # AGM 6-K: no quarter token — not an anchor.
    assert "acc-6k-agm" not in by_acc


def test_extract_6ks_collects_all_with_form_tag():
    six = _extract_6ks(_shop_like_recent(), src_cik="0001594805")
    assert [e["accession"] for e in six] == ["acc-6k-pr", "acc-6k-agm"]
    assert all(e["form"] == "6-K" and e["src_cik"] == "0001594805" for e in six)


def test_6k_never_enters_202_pool():
    ers = _extract_er_8ks(_shop_like_recent(), src_cik="0001594805")
    assert ers == []


def _fallback_client(index_docs):
    client = MagicMock()
    client.filing_index_url.side_effect = lambda cik, acc: f"https://x/{acc}/"
    fetched = []

    def _fetch(url):
        acc = url.rstrip("/").rsplit("/", 1)[-1]
        fetched.append(acc)
        docs = index_docs[acc]
        links = "".join(f'<a href="/Archives/x/{d}">{d}</a>' for d in docs)
        return f"<html><body>{links}</body></html>"

    client.fetch_text.side_effect = _fetch
    client.fetched = fetched
    return client


def _shop_anchor():
    return {
        "form": "6-K",
        "report_date": date(2024, 9, 30),
        "filing_date": date(2024, 11, 12),
    }


def _shop_6k_pr(accession="acc-6k-pr"):
    return {
        "form": "6-K",
        "accession": accession,
        "filing_date": date(2024, 11, 12),
        "primary_doc": "form6kq32024pressrelease.htm",
        "items": "",
        "src_cik": "0001594805",
    }


def test_fallback_6k_excludes_primary_doc_from_pick():
    # The 6-K cover form is press-release-named; without the exclusion it
    # would outrank the real EX-99.1 exhibit (a3pr.htm).
    assert _release_name_rank("form6kq32024pressrelease.htm")[0] == 1
    client = _fallback_client(
        {"acc-6k-pr": ["form6kq32024pressrelease.htm", "a3pr.htm"]}
    )
    m = _match_8k_non202_fallback(
        _shop_anchor(), [_shop_6k_pr()], "SHOP", "0001594805", client
    )
    assert m is not None
    assert m[0]["accession"] == "acc-6k-pr"
    assert m[1] == "a3pr.htm"


def test_fallback_6k_tiebreak_prefers_pressrelease_over_results():
    # SHOP furnishes two 6-Ks the same day: the press-release 6-K (real
    # release a3pr.htm) and the results 6-K (99.1 = financial statements).
    # Feed order lists the results 6-K first — the tiebreak must still try
    # the press-release 6-K first.
    results_6k = {
        "form": "6-K",
        "accession": "acc-6k-res",
        "filing_date": date(2024, 11, 12),
        "primary_doc": "form6k-q32024results.htm",
        "items": "",
        "src_cik": "0001594805",
    }
    client = _fallback_client(
        {
            "acc-6k-pr": ["form6kq32024pressrelease.htm", "a3pr.htm"],
            "acc-6k-res": [
                "form6k-q32024results.htm",
                "exhibit991financialstateme.htm",
                "exhibit992mdaq32024.htm",
            ],
        }
    )
    m = _match_8k_non202_fallback(
        _shop_anchor(), [results_6k, _shop_6k_pr()], "SHOP", "0001594805", client
    )
    assert m is not None and m[1] == "a3pr.htm"
    assert client.fetched == ["acc-6k-pr"]  # results 6-K index never read


def test_fallback_6k_unrelated_rejected():
    # BFCM press-release 6-K: no period reference on the primary doc or the
    # exhibit — must not become anyone's earnings release.
    bfcm = {
        "form": "6-K",
        "accession": "acc-6k-bfcm",
        "filing_date": date(2024, 12, 3),
        "primary_doc": "form6k-bfcmclosepressrelea.htm",
        "items": "",
        "src_cik": "0001594805",
    }
    filing = {
        "form": "6-K",
        "report_date": date(2024, 9, 30),
        "filing_date": date(2024, 12, 3),
    }
    client = _fallback_client(
        {"acc-6k-bfcm": ["form6k-bfcmclosepressrelea.htm", "bfcmex991.htm"]}
    )
    assert (
        _match_8k_non202_fallback(filing, [bfcm], "SHOP", "0001594805", client)
        is None
    )


def _shop_discovery_recent():
    # SHOP-shaped: 5× 10-Q + 2× 10-K in the recent window, the Q3-2024
    # quarterly filing beyond it, two Q3-2024 6-Ks + one BFCM 6-K in-window,
    # no 8-Ks at all.
    forms, accs, reports, filings, docs, items = [], [], [], [], [], []
    quarters = [
        ("10-K", "2024-12-31", "2025-02-11", "shop-20241231.htm"),
        ("10-Q", "2025-03-31", "2025-05-08", "shop-20250331.htm"),
        ("10-Q", "2025-06-30", "2025-08-06", "shop-20250630.htm"),
        ("10-Q", "2025-09-30", "2025-11-04", "shop-20250930.htm"),
        ("10-K", "2025-12-31", "2026-02-11", "shop-20251231.htm"),
        ("10-Q", "2026-03-31", "2026-05-05", "shop-20260331.htm"),
        ("10-Q", "2026-06-30", "2026-08-05", "shop-20260630.htm"),
        ("6-K", "2024-09-30", "2024-11-12", "form6kq32024pressrelease.htm"),
        ("6-K", "2024-09-30", "2024-11-12", "form6k-q32024results.htm"),
        ("6-K", "2024-12-03", "2024-12-03", "form6k-bfcmclosepressrelea.htm"),
    ]
    for i, (form, rep, fil, doc) in enumerate(quarters):
        forms.append(form)
        accs.append(f"acc-{i}")
        reports.append(rep)
        filings.append(fil)
        docs.append(doc)
        items.append("")
    return {
        "form": forms,
        "accessionNumber": accs,
        "reportDate": reports,
        "filingDate": filings,
        "primaryDocument": docs,
        "items": items,
    }


def test_discover_6k_anchor_end_to_end():
    recent = _shop_discovery_recent()
    client = MagicMock()
    client.cik_for_ticker.return_value = "0001594805"
    client.submissions.return_value = {"filings": {"recent": recent, "files": []}}
    client.filing_index_url.side_effect = lambda cik, acc: f"https://x/{acc}/"
    index_docs = {
        "acc-7": ["form6kq32024pressrelease.htm", "a3pr.htm"],
        "acc-8": ["form6k-q32024results.htm", "exhibit991financialstateme.htm"],
    }

    def _fetch(url):
        acc = url.rstrip("/").rsplit("/", 1)[-1]
        docs = index_docs[acc]
        links = "".join(f'<a href="/Archives/x/{d}">{d}</a>' for d in docs)
        return f"<html><body>{links}</body></html>"

    client.fetch_text.side_effect = _fetch

    periods = discover_earnings_filings(
        "SHOP", client, n_quarters=8, oldest_period_end=date(2024, 9, 30)
    )
    assert len(periods) == 8
    oldest = periods[0]
    assert oldest.period_end == date(2024, 9, 30)
    assert oldest.sec_form == "6-K"
    assert oldest.quarter_label == "Q3 FY2024"
    assert oldest.fy == 2024 and oldest.fp == "Q3"
    assert oldest.er_accession == "acc-7"
    assert oldest.er_doc == "a3pr.htm"
    assert oldest.er_cik == "0001594805"
    # The formal filings still anchor their own quarters — no 6-K shadow.
    assert [p.sec_form for p in periods[1:]] == [
        "10-K", "10-Q", "10-Q", "10-Q", "10-K", "10-Q", "10-Q",
    ]
    forms_by_end = {p.period_end: p.sec_form for p in periods}
    assert forms_by_end[date(2025, 3, 31)] == "10-Q"
    assert sum(1 for p in periods if p.sec_form == "6-K") == 1


def test_anchor_shadowed_by_10q_on_same_date():
    # A 10-Q on the same report date always wins over the 6-K anchor.
    recent = {
        "form": ["10-Q", "6-K"],
        "accessionNumber": ["acc-10q", "acc-6k"],
        "reportDate": ["2024-09-30", "2024-09-30"],
        "filingDate": ["2024-11-12", "2024-11-12"],
        "primaryDocument": ["shop-20240930.htm", "form6kq32024pressrelease.htm"],
        "items": ["", ""],
    }
    client = MagicMock()
    client.cik_for_ticker.return_value = "0001594805"
    client.submissions.return_value = {"filings": {"recent": recent, "files": []}}
    periods = discover_earnings_filings("SHOP", client, n_quarters=2)
    assert len(periods) == 1
    assert periods[0].sec_form == "10-Q"
    assert periods[0].sec_accession == "acc-10q"
