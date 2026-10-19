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


def test_mastercard_doubled_x_ex99():
    # Mastercard names exhibits ma06302026-exx991xearnings.htm (doubled x).
    links = [
        "/Archives/edgar/data/1141391/000114139126000081/ma-20260730.htm",
        "/Archives/edgar/data/1141391/000114139126000081/ma06302026-exx991xearnings.htm",
        "/Archives/edgar/data/1141391/000114139126000081/R1.htm",
    ]
    assert _pick_release_doc(links) == "ma06302026-exx991xearnings.htm"


def test_starbucks_truncated_earningsrele():
    # Starbucks truncates "release": sbux-06282026xearningsrele.htm.
    links = [
        "/Archives/edgar/data/829224/000082922426000129/sbux-20260729.htm",
        "/Archives/edgar/data/829224/000082922426000129/sbux-06282026xearningsrele.htm",
        "/Archives/edgar/data/829224/000082922426000129/R1.htm",
    ]
    assert _pick_release_doc(links) == "sbux-06282026xearningsrele.htm"


def test_amd_bare_991_suffix():
    # AMD names the exhibit q22026991.htm (quarter + 99.1, no "ex").
    links = [
        "/Archives/edgar/data/2488/000000248826000121/amd-20260804.htm",
        "/Archives/edgar/data/2488/000000248826000121/amdq22026earningsslidesf.htm",
        "/Archives/edgar/data/2488/000000248826000121/q22026991.htm",
        "/Archives/edgar/data/2488/000000248826000121/R1.htm",
    ]
    assert _pick_release_doc(links) == "q22026991.htm"


def test_realty_income_991_infix_before_quarter():
    # Realty Income names the exhibit o-991q22026.htm (99.1 before the quarter
    # marker); the supplement realtyincomeq22026supple.htm must still lose.
    links = [
        "/Archives/edgar/data/726728/000072672826000044/o-20260805.htm",
        "/Archives/edgar/data/726728/000072672826000044/o-991q22026.htm",
        "/Archives/edgar/data/726728/000072672826000044/realtyincomeq22026supple.htm",
        "/Archives/edgar/data/726728/000072672826000044/R1.htm",
    ]
    assert _pick_release_doc(links) == "o-991q22026.htm"


def test_991_infix_with_separator():
    # A 99.1 exhibit followed by a separator (e.g. o-991-q2) also ranks tier 0.
    links = ["o-20260805.htm", "o-991-q22026.htm", "R1.htm"]
    assert _pick_release_doc(links) == "o-991-q22026.htm"


def test_991_inside_longer_number_not_matched():
    # 991 embedded in a longer digit run (e.g. a doc id ...9912...) is not a
    # 99.1 exhibit marker — falls through to None here.
    links = ["doc9912final.htm", "R1.htm"]
    assert _pick_release_doc(links) is None


def test_amgen_truncated_earningsrelea():
    # Amgen truncates differently: amgn-20260630earningsrelea.htm.
    links = [
        "/Archives/edgar/data/318154/000031815426000000/amgn-20260804.htm",
        "/Archives/edgar/data/318154/000031815426000000/amgn-20260630earningsrelea.htm",
        "/Archives/edgar/data/318154/000031815426000000/R1.htm",
    ]
    assert _pick_release_doc(links) == "amgn-20260630earningsrelea.htm"


def test_accenture_earnings_8k_exhibit():
    # Accenture names the exhibit q4fy26earnings8-kexhibit.htm — "earnings"
    # directly joined to "8-k", no "release" word.
    links = [
        "/Archives/edgar/data/1467373/000146737326000037/acn-20261001.htm",
        "/Archives/edgar/data/1467373/000146737326000037/q4fy26earnings8-kexhibit.htm",
        "/Archives/edgar/data/1467373/000146737326000037/R1.htm",
    ]
    assert _pick_release_doc(links) == "q4fy26earnings8-kexhibit.htm"


def test_eog_exh99_prefix():
    # EOG abbreviates "exhibit" as "exh": exh99-1080426.htm (exhibit 99.1).
    links = ["eog-20260804.htm", "exh99-1080426.htm", "R1.htm"]
    assert _pick_release_doc(links) == "exh99-1080426.htm"


def test_carnival_earningsrelease_8k_suffix():
    # Carnival: a20263qearningsrelease8-k.htm — "earningsrelease" followed by
    # a digit (no word boundary) must still match.
    links = ["ccl-20260929.htm", "a20263qearningsrelease8-k.htm", "R1.htm"]
    assert _pick_release_doc(links) == "a20263qearningsrelease8-k.htm"


def test_travelers_pressrelease_date_suffix():
    # Travelers: a991pressrelease93026.htm — "pressrelease" followed by a
    # date; the a992finsupp93026.htm supplement must lose.
    links = ["trv-20261016.htm", "a991pressrelease93026.htm", "a992finsupp93026.htm"]
    assert _pick_release_doc(links) == "a991pressrelease93026.htm"


def test_affirm_truncated_shareholderle():
    # Affirm's earnings release IS the shareholder letter, truncated to
    # affirmfq426shareholderle.htm.
    links = [
        "/Archives/edgar/data/1820953/000162828026059271/afrm-20260825.htm",
        "/Archives/edgar/data/1820953/000162828026059271/affirmfq426shareholderle.htm",
        "/Archives/edgar/data/1820953/000162828026059271/R1.htm",
    ]
    assert _pick_release_doc(links) == "affirmfq426shareholderle.htm"


def test_coinbase_shareholderletter():
    links = ["coin-20260212.htm", "q425shareholderletter.htm", "R1.htm"]
    assert _pick_release_doc(links) == "q425shareholderletter.htm"


def test_duolingo_truncated_share_beats_presentation():
    # Duolingo: the ...share.htm doc is the shareholder-letter release; the
    # ...xpres.htm doc is the earnings deck and must lose.
    links = [
        "duol-20260805.htm",
        "q2fy26duolingo6-30x26share.htm",
        "q2fy26duolingo6-30x26xpres.htm",
    ]
    assert _pick_release_doc(links) == "q2fy26duolingo6-30x26share.htm"


def test_duolingo_shar_truncation_beats_press_release():
    # Batch-94: Duolingo's Q4/FY letter is truncated one step further —
    # q4fy25duolingo12-31x25shar.htm ("shar", no "e"). The EX-99.1
    # ...x25pres.htm is a stub pointing at the IR website and must lose.
    links = [
        "duol-20260226.htm",
        "q4fy25duolingo12-31x25pres.htm",
        "q4fy25duolingo12-31x25shar.htm",
    ]
    assert _pick_release_doc(links) == "q4fy25duolingo12-31x25shar.htm"


def test_shar_truncation_requires_quarter_marker():
    # The "shar" truncation needs the quarter/fy guard: bare "shar" or a
    # lookalike like "shark" must not match.
    assert _pick_release_doc(["shar.htm", "duol-20260226.htm"]) is None
    assert _pick_release_doc(["sharkweekq1.htm", "duol-20260226.htm"]) is None


def test_shareholder_meeting_not_a_release():
    # "shareholder" must be followed by end/separator or letter-truncation —
    # a shareholder-meeting doc is not the earnings release.
    links = ["shareholdermeeting.htm", "jnj-20260715.htm"]
    assert _pick_release_doc(links) is None


def test_corteva_earnings_news_release():
    # Corteva: a2q_2026xearningsxnewsxr.htm ("earnings news release");
    # the a6302026enrschedules.htm tables must lose.
    links = [
        "ctva-20260730.htm",
        "a2q_2026xearningsxnewsxr.htm",
        "a6302026enrschedules.htm",
        "R1.htm",
    ]
    assert _pick_release_doc(links) == "a2q_2026xearningsxnewsxr.htm"


def test_lilly_sales_and_earnings():
    links = ["lly-20260805.htm", "q226lillysalesandearningsp.htm", "R1.htm"]
    assert _pick_release_doc(links) == "q226lillysalesandearningsp.htm"


def test_southwest_er_doc():
    # Southwest: er-6302026xerdoc.htm ("ER doc" = earnings release document).
    links = ["luv-20260722.htm", "er-6302026xerdoc.htm", "R1.htm"]
    assert _pick_release_doc(links) == "er-6302026xerdoc.htm"


def test_superdocuments_not_an_er_doc():
    # The "erdoc" signal must not fire inside a longer word.
    links = ["superdocuments.htm", "jnj-20260715.htm"]
    assert _pick_release_doc(links) is None


def test_mccormick_headline_style_reports():
    # McCormick names the exhibit after the release headline:
    # mkcreportssolidthirdquar.htm.
    links = ["mkc-20261001.htm", "mkcreportssolidthirdquar.htm", "R1.htm"]
    assert _pick_release_doc(links) == "mkcreportssolidthirdquar.htm"


def test_servicenow_bare_er_quarter():
    # ServiceNow: erq2fy26.htm — bare "er" + quarter marker.
    links = ["now-20260722.htm", "erq2fy26.htm", "R1.htm"]
    assert _pick_release_doc(links) == "erq2fy26.htm"


def test_pnc_financial_highlights_beats_supplement():
    # PNC's "financial highlights" doc is the release; the
    # "financialsupplement" tables must lose.
    links = [
        "pnc-20261015.htm",
        "q32026financialhighlightsa.htm",
        "q32026financialsupplement.htm",
    ]
    assert _pick_release_doc(links) == "q32026financialhighlightsa.htm"


def test_snowflake_quarter_adjacent_earnings():
    # Snowflake: fy2027q2earnings.htm — "earnings" with a quarter marker.
    links = ["snow-20260902.htm", "fy2027q2earnings.htm", "R1.htm"]
    assert _pick_release_doc(links) == "fy2027q2earnings.htm"


def test_newmont_earnings_and_year():
    # Newmont: newmontq42025earningsand20.htm.
    links = ["nem-20260219.htm", "newmontq42025earningsand20.htm", "R1.htm"]
    assert _pick_release_doc(links) == "newmontq42025earningsand20.htm"
