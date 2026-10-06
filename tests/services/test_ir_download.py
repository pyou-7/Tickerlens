"""Unit tests for ir_download._pick_release_doc (pure filename matching)
and _assign_fy_and_quarter (pure FY/quarter labeling)."""

from datetime import date

from tickerlens.services.ir_download import _assign_fy_and_quarter, _pick_release_doc


def test_ex99_classic_wins():
    links = [
        "/Archives/edgar/data/320193/000032019325000073/aapl-20250628.htm",
        "/Archives/edgar/data/320193/000032019325000073/exhibit991-8k_20250628.htm",
        "/Archives/edgar/data/320193/000032019325000073/R1.htm",
    ]
    assert _pick_release_doc(links) == "exhibit991-8k_20250628.htm"


def test_ex99_dash_variant():
    links = ["ex-99.1_earnings.htm", "msft-20250630.htm"]
    assert _pick_release_doc(links) == "ex-99.1_earnings.htm"


def test_nvda_quarter_pr_suffix():
    # NVDA names exhibits qNfyYYpr.htm — no "ex99" anywhere.
    links = [
        "/Archives/edgar/data/1045810/000104581026000073/nvda-20260826.htm",
        "/Archives/edgar/data/1045810/000104581026000073/q2fy27cfocommentary.htm",
        "/Archives/edgar/data/1045810/000104581026000073/q2fy27pr.htm",
        "/Archives/edgar/data/1045810/000104581026000073/R1.htm",
    ]
    assert _pick_release_doc(links) == "q2fy27pr.htm"


def test_pressrelease_word():
    links = ["2026-q2-pressrelease.htm", "tsla-20260630.htm"]
    assert _pick_release_doc(links) == "2026-q2-pressrelease.htm"


def test_pr_separator_suffix():
    links = ["q2-2026_pr.htm", "amzn-20260630.htm"]
    assert _pick_release_doc(links) == "q2-2026_pr.htm"


def test_proper_htm_not_matched():
    # "pr" lookalikes without a digit must not be picked as press releases.
    links = ["proper.htm", "super.htm", "jnj-20260715.htm"]
    assert _pick_release_doc(links) is None


def test_no_release_returns_none():
    links = ["nvda-20260826.htm", "index.htm", "R1.htm"]
    assert _pick_release_doc(links) is None


def test_ex99_beats_pr_naming():
    # When both conventions appear, ex99 takes priority.
    links = ["q1fy27pr.htm", "ex991.htm"]
    assert _pick_release_doc(links) == "ex991.htm"


def _filing(form: str, report_date: date) -> dict:
    return {"form": form, "report_date": report_date}


def _labels(filings: list[dict]) -> list[tuple[str, int, str]]:
    _assign_fy_and_quarter(filings)
    return [
        (f["report_date"].isoformat(), f["fy"], f["fp"])
        for f in sorted(filings, key=lambda x: x["report_date"])
    ]


def test_assign_fy_quarter_calendar_full_year():
    filings = [
        _filing("10-Q", date(2024, 3, 31)),
        _filing("10-Q", date(2024, 6, 30)),
        _filing("10-Q", date(2024, 9, 30)),
        _filing("10-K", date(2024, 12, 31)),
    ]
    assert _labels(filings) == [
        ("2024-03-31", 2024, "Q1"),
        ("2024-06-30", 2024, "Q2"),
        ("2024-09-30", 2024, "Q3"),
        ("2024-12-31", 2024, "Q4"),
    ]


def test_assign_fy_quarter_noncalendar_partial_oldest_year():
    # NVDA-like: FY ends in January; the discovery window opens mid-cycle with
    # a Q3 10-Q whose fy group contains the 10-K. Quarters before the 10-K must
    # count back from Q4 — previously this mislabeled the oldest quarter Q1.
    filings = [
        _filing("10-Q", date(2024, 10, 27)),
        _filing("10-K", date(2025, 1, 26)),
        _filing("10-Q", date(2025, 4, 27)),
        _filing("10-Q", date(2025, 7, 27)),
    ]
    assert _labels(filings) == [
        ("2024-10-27", 2025, "Q3"),
        ("2025-01-26", 2025, "Q4"),
        ("2025-04-27", 2026, "Q1"),
        ("2025-07-27", 2026, "Q2"),
    ]


def test_assign_fy_quarter_trailing_partial_year_without_10k():
    # Most recent quarters of a new FY whose 10-K is not in the window yet:
    # quarters run forward from Q1 as before.
    filings = [
        _filing("10-K", date(2026, 1, 25)),
        _filing("10-Q", date(2026, 4, 26)),
        _filing("10-Q", date(2026, 7, 26)),
    ]
    assert _labels(filings) == [
        ("2026-01-25", 2026, "Q4"),
        ("2026-04-26", 2027, "Q1"),
        ("2026-07-26", 2027, "Q2"),
    ]


def _sec_filing(form: str, report: date, filed: date) -> dict:
    return {"form": form, "report_date": report, "filing_date": filed}


def _er(filed: date) -> dict:
    return {"filing_date": filed}


def test_match_8k_annual_period_with_long_lag():
    # 10-K filed 31 days after the earnings 8-K: the old 21-day window anchored
    # on the filing date missed this systematically for annual periods.
    from tickerlens.services.ir_download import _match_8k

    filing = _sec_filing("10-K", date(2025, 12, 31), date(2026, 2, 13))
    release = _er(date(2026, 1, 13))
    assert _match_8k(filing, [release]) == release


def test_match_8k_quarterly_normal_case():
    from tickerlens.services.ir_download import _match_8k

    filing = _sec_filing("10-Q", date(2025, 9, 30), date(2025, 11, 4))
    release = _er(date(2025, 10, 14))
    assert _match_8k(filing, [release]) == release


def test_match_8k_ignores_8k_before_period_end():
    from tickerlens.services.ir_download import _match_8k

    filing = _sec_filing("10-Q", date(2026, 6, 30), date(2026, 8, 6))
    early = _er(date(2026, 6, 15))  # before quarter end: not this quarter's release
    release = _er(date(2026, 7, 14))
    assert _match_8k(filing, [early, release]) == release


def test_match_8k_no_candidate_returns_none():
    from tickerlens.services.ir_download import _match_8k

    filing = _sec_filing("10-Q", date(2026, 6, 30), date(2026, 8, 6))
    assert _match_8k(filing, [_er(date(2026, 9, 15))]) is None
    assert _match_8k(filing, []) is None


def test_supplement_loses_to_narrative_release():
    links = [
        "a4q25erfex992supplement.htm",
        "a4q25erfexhibit991narrative.htm",
    ]
    assert _pick_release_doc(links) == "a4q25erfexhibit991narrative.htm"
    # Order-independent: the narrative wins even when listed second-to-last.
    assert _pick_release_doc(list(reversed(links))) == "a4q25erfexhibit991narrative.htm"


def test_supplement_picked_when_only_option():
    links = ["ex991supplement.htm", "R1.htm"]
    assert _pick_release_doc(links) == "ex991supplement.htm"
