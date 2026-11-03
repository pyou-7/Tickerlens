"""Unit tests for ir_download._pick_release_doc (pure filename matching)
and _assign_fy_and_quarter (pure FY/quarter labeling)."""

from datetime import date
from unittest.mock import MagicMock

from tickerlens.services.ir_download import (
    _assign_fy_and_quarter,
    _lone_exhibit_fallback,
    _merge_filings_recent,
    _pick_release_doc,
    discover_earnings_filings,
)


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


def test_cinf_digit_quarter_991_token():
    # Cincinnati Financial names the 99.1 exhibit exhibit9911q25.htm (99.1
    # + digit-quarter token 1q25) for Q1–Q3, and exhibit991q424.htm for
    # Q4; the 99.2 supplements (exhibit9921q25.htm) must lose.
    links = [
        "cinf-20250428.htm",
        "exhibit9921q25.htm",
        "exhibit9911q25.htm",
        "R1.htm",
    ]
    assert _pick_release_doc(links) == "exhibit9911q25.htm"
    links = [
        "cinf-20250728.htm",
        "exhibit9912q25.htm",
        "exhibit9922q25.htm",
        "R1.htm",
    ]
    assert _pick_release_doc(links) == "exhibit9912q25.htm"


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


# ── Batch 97: partial-highlight residual forensics ────────────────────────────

def test_acn_bare_8k_exhibit():
    # ACN's older convention: fy24q4plc8-kexhibit.htm — a bare "8-K exhibit"
    # in an Item 2.02 filing is the furnished release.
    links = ["acn-20240926.htm", "fy24q4plc8-kexhibit.htm", "R1.htm"]
    assert _pick_release_doc(links) == "fy24q4plc8-kexhibit.htm"


def test_affirm_shareholderlett_truncation():
    # Affirm truncates one letter further: afrm-q225shareholderlett.htm.
    links = ["afrm-20250206.htm", "afrm-q225shareholderlett.htm", "R1.htm"]
    assert _pick_release_doc(links) == "afrm-q225shareholderlett.htm"


def test_cart_sha_truncation_with_ordinal_guard():
    # CART: cartfourthquarter2025sha.htm — "sha" truncation with a spelled-out
    # ordinal quarter marker.
    links = ["cart-20260212.htm", "cartfourthquarter2025sha.htm", "R1.htm"]
    assert _pick_release_doc(links) == "cartfourthquarter2025sha.htm"
    links = ["cart-20251110.htm", "cartthirdquarter2025shar.htm", "R1.htm"]
    assert _pick_release_doc(links) == "cartthirdquarter2025shar.htm"


def test_sha_truncation_requires_quarter_marker():
    # "sha" without any quarter/fy/ordinal marker must not match.
    assert _pick_release_doc(["sharkweek2026.htm"]) is None
    assert _pick_release_doc(["nebraskashares.htm"]) is None


def test_cci_month_year_release():
    # Crown Castle: may2026release.htm — month+year+"release". The proforma
    # doc in the same index must not match.
    links = [
        "/Archives/edgar/data/1051470/000105147026000052/cci-20260501.htm",
        "/Archives/edgar/data/1051470/000105147026000052/crowncastleincproforma.htm",
        "/Archives/edgar/data/1051470/000105147026000052/may2026release.htm",
    ]
    assert _pick_release_doc(links) == "may2026release.htm"
    assert _pick_release_doc(["crowncastleincproforma.htm"]) is None


def test_ctva_reversed_quarter_marker():
    # Corteva: final_4qx2024xearningsxn.htm — "4q" reversed quarter marker.
    links = ["ctva-20250205.htm", "final_4qx2024xearningsxn.htm", "R1.htm"]
    assert _pick_release_doc(links) == "final_4qx2024xearningsxn.htm"


def test_ctva_narrative_beats_schedules():
    # Corteva furnishes the narrative release plus an "enrschedules" tables
    # doc — the schedules (like "supplement") must lose.
    links = ["a123124enrschedules.htm", "final_4qx2024xearningsxn.htm"]
    assert _pick_release_doc(links) == "final_4qx2024xearningsxn.htm"


def test_delta_announces_month():
    # Delta: deltaairlinesannouncessept.htm — "announces" + truncated month.
    for name in [
        "deltaairlinesannouncessept.htm",
        "deltaairlinesannouncesjune.htm",
        "deltaairlinesannouncesmarc.htm",
        "deltaairlinesannouncesdece.htm",
    ]:
        assert _pick_release_doc(["dal-20261009.htm", name]) == name


def test_eqix_pr_with_trailing_junk():
    # EQIX: eqix-033125xpr8k.htm / eqix-093024xpruploadhyperl.htm — "pr" with
    # trailing junk plus a date guard. The separator before "pr" keeps
    # "express"/"improper" out.
    links = ["eqix-20250430.htm", "eqix-033125xpr8k.htm", "R1.htm"]
    assert _pick_release_doc(links) == "eqix-033125xpr8k.htm"
    links = ["eqix-20241030.htm", "eqix-093024xpruploadhyperl.htm", "R1.htm"]
    assert _pick_release_doc(links) == "eqix-093024xpruploadhyperl.htm"
    assert _pick_release_doc(["expressdelivery2026.htm"]) is None


def test_gpc_truncated_earn_quarter():
    # GPC: gpc-earnq22026.htm — truncated "earn" + quarter. The left boundary
    # keeps "learn..."/"earned..." out.
    links = ["gpc-20260721.htm", "gpc-earnq22026.htm", "R1.htm"]
    assert _pick_release_doc(links) == "gpc-earnq22026.htm"
    # The left boundary keeps "learn..."/"earned..." (no "earnings") out.
    assert _pick_release_doc(["gpc-learnq22026.htm"]) is None


def test_mkc_truncated_headline_reports():
    # McCormick's truncated headline names: the quarter word didn't survive
    # truncation (mccormickreportsstrongfi.htm). Bare "reports" matches;
    # "annual" is excluded.
    for name in [
        "mccormickreportsstrongfi.htm",
        "mccormickreportsstrong20.htm",
        "mccormickreportsstrong2024.htm",
    ]:
        assert _pick_release_doc(["mkc-20260331.htm", name]) == name
    assert _pick_release_doc(["annualreports2024.htm"]) is None


def test_unh_991_prefix_beats_992_supplement():
    # United Health: a991unherq42025.htm is the 99.1 release; q42025er992.htm
    # is the 99.2 supplement and must never be picked as the release.
    links = ["unh-20260127.htm", "a991unherq42025.htm", "q42025er992.htm", "R1.htm"]
    assert _pick_release_doc(links) == "a991unherq42025.htm"
    assert _pick_release_doc(["q42025er992.htm"]) is None


def test_991_letter_suffix_still_excludes_longer_numbers():
    # doc9912final.htm must stay unmatched even with the letter-run lookahead.
    assert _pick_release_doc(["doc9912final.htm"]) is None


# ── Batch 97: lone-exhibit fallback (2.02-only 8-Ks) ──────────────────────────

_TSLA_LINKS = [
    "/index.htm",
    "/search/search.htm",
    "/news/newsroom/howinvestigationswork.html",
    "/Archives/edgar/data/1616707/000162828024043432/0001628280-24-043432-index.html",
    "/Archives/edgar/data/1616707/000162828024043432/0001628280-24-043432-index-headers.html",
    "/Archives/edgar/data/1616707/000162828024043432/exhibit.htm",
    "/Archives/edgar/data/1616707/000162828024043432/R1.htm",
    "/Archives/edgar/data/1616707/000162828024043432/tsla-20241023.htm",
    "/eeoinfo/sec_access.htm",
    "/privacy.htm",
]


def test_lone_exhibit_fallback_tsla():
    # Tesla's bare "exhibit.htm": the only non-primary filing doc in a
    # 2.02-only 8-K is the furnished release.
    assert (
        _lone_exhibit_fallback(_TSLA_LINKS, "tsla-20241023.htm", "2.02")
        == "exhibit.htm"
    )


def test_lone_exhibit_fallback_requires_single_exhibit():
    links = _TSLA_LINKS + [
        "/Archives/edgar/data/1616707/000162828024043432/exhibit2.htm"
    ]
    assert _lone_exhibit_fallback(links, "tsla-20241023.htm", "2.02") is None


def test_lone_exhibit_fallback_requires_202_first():
    # Most earnings 8-Ks carry 9.01/7.01 alongside 2.02 — those must fire.
    # An 8-K led by another item (incidental 2.02) must never be guessed.
    assert (
        _lone_exhibit_fallback(_TSLA_LINKS, "tsla-20241023.htm", "2.02, 9.01")
        == "exhibit.htm"
    )
    assert (
        _lone_exhibit_fallback(_TSLA_LINKS, "tsla-20241023.htm", "2.02,7.01,9.01")
        == "exhibit.htm"
    )
    assert _lone_exhibit_fallback(_TSLA_LINKS, "tsla-20241023.htm", "5.02, 2.02") is None
    assert _lone_exhibit_fallback(_TSLA_LINKS, "tsla-20241023.htm", "1.01, 2.02") is None
    assert _lone_exhibit_fallback(_TSLA_LINKS, "tsla-20241023.htm", None) is None


def test_lone_exhibit_fallback_relative_hrefs():
    # Older indexes use relative hrefs for filing docs.
    links = ["exhibit.htm", "hal-20260421.htm", "R1.htm"]
    assert _lone_exhibit_fallback(links, "hal-20260421.htm", "2.02") == "exhibit.htm"


# ── Batch 97: paginated submissions buckets ───────────────────────────────────

def _recent_forms(*forms):
    n = len(forms)
    return {
        "form": list(forms),
        "accessionNumber": [f"acc-{i}" for i in range(n)],
        "reportDate": ["2026-06-30"] * n,
        "filingDate": ["2026-07-30"] * n,
        "primaryDocument": [f"doc-{i}.htm" for i in range(n)],
        "items": ["" for _ in range(n)],
    }


def test_merge_filings_recent_concatenates_parallel_arrays():
    base = _recent_forms("10-Q", "8-K")
    extra = _recent_forms("10-K", "10-Q")
    merged = _merge_filings_recent(base, extra)
    assert merged["form"] == ["10-Q", "8-K", "10-K", "10-Q"]
    assert merged["accessionNumber"] == ["acc-0", "acc-1", "acc-0", "acc-1"]
    # Base dict is not mutated.
    assert base["form"] == ["10-Q", "8-K"]


def test_discover_paginates_when_recent_is_short():
    # High-volume filer: recent holds 1 10-Q + 1 10-K; the older 10-Q lives in
    # bucket 001. discover_earnings_filings must page to find it.
    recent = _recent_forms("10-Q", "10-K", "8-K", "8-K", "4")
    recent["items"][2] = "2.02"
    recent["items"][3] = "2.02"
    bucket = _recent_forms("10-Q", "8-K")
    bucket["items"][1] = "2.02"
    # Make the bucket 8-K fall in the older quarter's 60-day window.
    bucket["filingDate"] = ["2026-04-15", "2026-04-16"]
    bucket["reportDate"] = ["2026-03-31", "2026-04-16"]
    client = MagicMock()
    client.cik_for_ticker.return_value = "0000001"
    client.submissions.return_value = {
        "filings": {"recent": recent, "files": [{"name": "CIK0000001-submissions-001.json"}]}
    }
    client.submissions_bucket.return_value = bucket
    client.filing_index_url.side_effect = lambda cik, acc: f"https://x/{acc}/"
    client.fetch_text.return_value = "<html></html>"

    periods = discover_earnings_filings("FAKE", client, n_quarters=3)
    assert client.submissions_bucket.called  # had to paginate
    assert len(periods) == 3
    # The older quarter came from the bucket.
    assert periods[0].period_end == date(2026, 3, 31)


def test_discover_stops_paginating_when_enough():
    recent = _recent_forms("10-Q", "10-K")
    client = MagicMock()
    client.cik_for_ticker.return_value = "0000001"
    client.submissions.return_value = {"filings": {"recent": recent, "files": []}}
    periods = discover_earnings_filings("FAKE", client, n_quarters=2)
    assert not client.submissions_bucket.called
    assert len(periods) == 2


def test_992_993_supplements_excluded_from_tier0():
    # BAC: bac-09302026ex993.htm is the 99.3 supplement — the 99.1 release
    # must win. A 99.2-only index honestly yields None.
    links = [
        "bac-09302026ex993.htm",
        "bac-20261014.htm",
        "bac09302026ex991.htm",
        "bac09302026ex992.htm",
    ]
    assert _pick_release_doc(links) == "bac09302026ex991.htm"
    assert _pick_release_doc(["ex992qfsq325.htm"]) is None
    assert _pick_release_doc(["ex993q32025totalaum.htm"]) is None
    # 99.1 forms still match.
    assert _pick_release_doc(["ex99-1.htm"]) == "ex99-1.htm"
    assert _pick_release_doc(["exhibit991-8k_20250628.htm"]) == "exhibit991-8k_20250628.htm"


def test_match_8k_excludes_8k_filed_after_10q():
    # PNC: a 2.02 investor-conference 8-K (2025-11-07) filed AFTER the 10-Q
    # (2025-11-03) cannot be the earnings release — the 10-15 earnings 8-K
    # wins even though the conference is nearer the filing date.
    from tickerlens.services.ir_download import _match_8k

    filing = _sec_filing("10-Q", date(2025, 9, 30), date(2025, 11, 3))
    earnings = _er(date(2025, 10, 15))
    conference = _er(date(2025, 11, 7))
    assert _match_8k(filing, [conference, earnings]) == earnings
    assert _match_8k(filing, [earnings, conference]) == earnings


def test_match_8k_post_filing_grace_berkshire():
    # Batch 113: Berkshire files the 10-Q a day or two BEFORE furnishing the
    # earnings-release 8-K (Q1'25: 10-Q 2025-05-05, release 2025-05-06) — the
    # 1-3-day post-filing grace pool rescues quarters with no pre-filing
    # 2.02 candidate.
    from tickerlens.services.ir_download import _match_8k

    filing = _sec_filing("10-Q", date(2025, 3, 31), date(2025, 5, 5))
    release = _er(date(2025, 5, 6))
    assert _match_8k(filing, [release]) == release
    # Three days out still qualifies (BRK.B Q1'26: 2026-05-04 -> 2026-05-07).
    release3 = _er(date(2025, 5, 8))
    assert _match_8k(filing, [release3]) == release3


def test_match_8k_grace_capped_at_3_days():
    # A 2.02 8-K 4 days after the formal filing is not the earnings release
    # when no pre-filing candidate exists — the PNC conference shape
    # (2025-11-07, 4 days after the 11-03 10-Q) without the genuine one.
    from tickerlens.services.ir_download import _match_8k

    filing = _sec_filing("10-Q", date(2025, 9, 30), date(2025, 11, 3))
    late = _er(date(2025, 11, 7))
    assert _match_8k(filing, [late]) is None


def test_match_8k_primary_beats_post_filing_grace():
    # A genuine pre-filing 2.02 always wins over a post-filing one — the
    # grace pool only fills quarters with no primary candidate.
    from tickerlens.services.ir_download import _match_8k

    filing = _sec_filing("10-Q", date(2025, 9, 30), date(2025, 11, 3))
    earnings = _er(date(2025, 10, 15))
    post = _er(date(2025, 11, 5))
    assert _match_8k(filing, [post, earnings]) == earnings


def test_match_8k_annual_window_75_days():
    # Batch 113: Berkshire's FY-2025 earnings 8-K came 61 days after year-end
    # (2025-12-31 -> 2026-03-02, same day as the 10-K) — annual periods get a
    # 75-day window, quarterly periods keep 60.
    from tickerlens.services.ir_download import _match_8k

    annual = _sec_filing("10-K", date(2025, 12, 31), date(2026, 3, 2))
    release = _er(date(2026, 3, 2))
    assert _match_8k(annual, [release]) == release
    quarterly = _sec_filing("10-Q", date(2025, 12, 31), date(2026, 3, 2))
    assert _match_8k(quarterly, [release]) is None


def test_discover_extends_to_oldest_stored_period():
    # Batch 97: the stored 8-quarter window can lag submissions (EDGAR
    # companyfacts delay) — discovery must extend past n_quarters to cover
    # the oldest stored period_end.
    def filing(report, filed):
        return {
            "form": "10-Q", "accession": f"acc-{report}", "report_date": report,
            "filing_date": filed, "primary_doc": "d.htm",
        }

    # 9 filings; n_quarters=8 but oldest stored needs the 9th.
    sec = [filing(date(2026, 3, 31) , date(2026, 5, 1))]
    sec += [filing(date(2025, 12, 31), date(2026, 2, 1))]
    sec += [filing(date(2025, 9, 30), date(2025, 11, 1))]
    sec += [filing(date(2025, 6, 30), date(2025, 8, 1))]
    sec += [filing(date(2025, 3, 31), date(2025, 5, 1))]
    sec += [filing(date(2024, 12, 31), date(2025, 2, 1))]
    sec += [filing(date(2024, 9, 30), date(2024, 11, 1))]
    sec += [filing(date(2024, 6, 30), date(2024, 8, 1))]
    sec += [filing(date(2024, 3, 31), date(2024, 5, 1))]
    recent = {
        "form": ["10-Q"] * 9,
        "accessionNumber": [f["accession"] for f in sec],
        "reportDate": [f["report_date"].isoformat() for f in sec],
        "filingDate": [f["filing_date"].isoformat() for f in sec],
        "primaryDocument": ["d.htm"] * 9,
        "items": [""] * 9,
    }
    client = MagicMock()
    client.cik_for_ticker.return_value = "0000001"
    client.submissions.return_value = {"filings": {"recent": recent, "files": []}}
    client.filing_index_url.side_effect = lambda cik, acc: f"https://x/{acc}/"
    client.fetch_text.return_value = "<html></html>"

    periods = discover_earnings_filings(
        "FAKE", client, n_quarters=8, oldest_period_end=date(2024, 3, 31)
    )
    assert len(periods) == 9
    assert periods[0].period_end == date(2024, 3, 31)
    # Without the hint, exactly n_quarters.
    periods = discover_earnings_filings("FAKE", client, n_quarters=8)
    assert len(periods) == 8


def test_match_8k_ignores_8k_too_soon_after_period_end():
    # Tesla: a 2.02 deliveries/production 8-K two days after quarter end is
    # not the earnings release — the later earnings 8-K wins.
    from tickerlens.services.ir_download import _match_8k

    filing = _sec_filing("10-Q", date(2024, 9, 30), date(2024, 10, 24))
    deliveries = _er(date(2024, 10, 2))
    earnings = _er(date(2024, 10, 23))
    assert _match_8k(filing, [deliveries, earnings]) == earnings


def test_pick_release_doc_undotted_9901():
    # Cadence's cdns07222024ex9901.htm is a 99.1 release ("ex99"+"01") — the
    # 99.2/99.3 guard must not block the undotted 99.1 form, while ex992/ex993
    # (and ex9902/ex9903) stay excluded.
    links = [
        "/Archives/edgar/data/813672/000081367224000150/cdns07222024ex9901.htm",
        "/Archives/edgar/data/813672/000081367224000150/cfocommentary07222024ex9902.htm",
    ]
    assert _pick_release_doc(links) == "cdns07222024ex9901.htm"
    # 99.2/99.3 undotted forms are still excluded.
    assert _pick_release_doc(["/x/bac-09302026ex993.htm"]) is None
    assert _pick_release_doc(["/x/met-ex9902qfs.htm"]) is None


# ── Batch 101: guarded fallback for earnings 8-Ks without Item 2.02 ───────────
# Citi/MTD file 9.01-only earnings 8-Ks, Colgate 8.01+9.01, GE Vernova
# 2.01+9.01 — the 2.02 gate missed all four quarters. The fallback only runs
# when _match_8k finds nothing, keeps the 7–60d / ≤filing-date guards, and
# requires a release-looking exhibit whose filename references the period
# (filing date, quarter token, or ticker) — an unrelated ex99 (Citi's Trust
# Preferred Securities 8-K) must never win.

from tickerlens.services.ir_download import (  # noqa: E402
    _exhibit_matches_period,
    _extract_other_8ks,
    _match_8k_non202_fallback,
)


def _other_8k_forms(*form_items):
    n = len(form_items)
    return {
        "form": [fi[0] for fi in form_items],
        "accessionNumber": [f"acc-{i}" for i in range(n)],
        "reportDate": ["2024-06-30"] * n,
        "filingDate": [fi[2] for fi in form_items],
        "primaryDocument": [f"doc-{i}.htm" for i in range(n)],
        "items": [fi[1] for fi in form_items],
    }


def test_extract_other_8ks_splits_on_202():
    raw = _other_8k_forms(
        ("8-K", "2.02,9.01", "2024-07-12"),   # primary path — excluded
        ("8-K", "9.01", "2024-07-12"),        # Citi/MTD shape — included
        ("8-K", "8.01,9.01", "2024-07-12"),   # Colgate shape — included
        ("8-K", "2.01,9.01", "2024-07-12"),   # GEV shape — included
        ("8-K", "8.01", "2024-07-12"),        # no exhibits — excluded
        ("8-K", "", "2024-07-12"),            # no items — excluded
        ("4", "9.01", "2024-07-12"),          # not an 8-K — excluded
    )
    others = _extract_other_8ks(raw, src_cik="0000001")
    assert [e["items"] for e in others] == ["9.01", "8.01,9.01", "2.01,9.01"]
    assert all(e["src_cik"] == "0000001" for e in others)


def test_exhibit_matches_period_guards():
    r = date(2024, 6, 30)
    f = date(2024, 7, 12)
    # Filing-date form (Citi).
    assert _exhibit_matches_period("c-20240712xex99d1.htm", "C", r, f)
    # Quarter-token forms (Colgate / MTD / GEV).
    assert _exhibit_matches_period("q32024pressreleasetables.htm", "CL", date(2024, 9, 30), date(2024, 10, 25))
    assert _exhibit_matches_period("ex-991mtd8xkq42024.htm", "MTD", date(2024, 12, 31), date(2025, 2, 6))
    assert _exhibit_matches_period("gevpressrelease2q25.htm", "GEV", date(2025, 6, 30), date(2025, 7, 23))
    # Ticker form.
    assert _exhibit_matches_period("mtd-earnings-release.htm", "MTD", r, f)
    # Unrelated ex99: no date, no quarter token, single-letter ticker is noise.
    assert not _exhibit_matches_period("d240560dex991.htm", "C", r, f)
    assert not _exhibit_matches_period("underwriting-ex99.htm", "MTD", date(2024, 12, 31), date(2025, 2, 6))


def _discovery_client(recent, index_docs):
    client = MagicMock()
    client.cik_for_ticker.return_value = "0000831001"
    client.submissions.return_value = {"filings": {"recent": recent, "files": []}}
    client.filing_index_url.side_effect = lambda cik, acc: f"https://x/{acc}/"
    def _fetch(url):
        acc = url.rstrip("/").rsplit("/", 1)[-1]
        docs = index_docs.get(acc)
        if docs is None:
            raise Exception("index unreadable")
        links = "".join(f'<a href="/Archives/x/{d}">{d}</a>' for d in docs)
        return f"<html><body>{links}</body></html>"
    client.fetch_text.side_effect = _fetch
    return client


def _recent_with_fallback_shapes():
    # One 10-Q (Q2 2024, filed 2024-08-02) + a 9.01-only 8-K (Citi shape).
    return {
        "form": ["10-Q", "8-K"],
        "accessionNumber": ["acc-10q", "acc-8k"],
        "reportDate": ["2024-06-30", "2024-06-30"],
        "filingDate": ["2024-08-02", "2024-07-12"],
        "primaryDocument": ["c-20240802.htm", "c-20240712x8k.htm"],
        "items": ["", "9.01"],
    }


def test_fallback_rescues_901_only_earnings_8k():
    client = _discovery_client(
        _recent_with_fallback_shapes(),
        {"acc-8k": ["c-20240712x8k.htm", "c-20240712xex99d1.htm", "R1.htm"]},
    )
    periods = discover_earnings_filings("C", client, n_quarters=1)
    assert len(periods) == 1
    assert periods[0].er_doc == "c-20240712xex99d1.htm"
    assert periods[0].er_accession == "acc-8k"


def test_fallback_prefers_202_match():
    # A 2.02 8-K exists: the primary path wins even when the 9.01-only 8-K
    # is nearer the formal filing date.
    recent = {
        "form": ["10-Q", "8-K", "8-K"],
        "accessionNumber": ["acc-10q", "acc-202", "acc-901"],
        "reportDate": ["2024-06-30"] * 3,
        "filingDate": ["2024-08-02", "2024-07-15", "2024-07-25"],
        "primaryDocument": ["c-20240802.htm", "c-20240715x8k.htm", "c-20240725x8k.htm"],
        "items": ["", "2.02,9.01", "9.01"],
    }
    client = _discovery_client(
        recent,
        {
            "acc-202": ["c-20240715x8k.htm", "ex991-earnings.htm"],
            "acc-901": ["c-20240725x8k.htm", "c-20240725xex99d1.htm"],
        },
    )
    periods = discover_earnings_filings("C", client, n_quarters=1)
    assert periods[0].er_doc == "ex991-earnings.htm"
    assert periods[0].er_accession == "acc-202"


def test_fallback_skips_8k_without_release_exhibit():
    client = _discovery_client(
        _recent_with_fallback_shapes(),
        {"acc-8k": ["c-20240712x8k.htm", "underwriting-agreement-ex99.htm", "R1.htm"]},
    )
    periods = discover_earnings_filings("C", client, n_quarters=1)
    assert periods[0].er_doc is None


def test_fallback_rejects_unrelated_ex99():
    # Citi's Trust Preferred Securities 8-K: ex99-shaped name, but the
    # filename references neither the period nor the filing date.
    client = _discovery_client(
        _recent_with_fallback_shapes(),
        {"acc-8k": ["d240560x8k.htm", "d240560dex991.htm", "R1.htm"]},
    )
    periods = discover_earnings_filings("C", client, n_quarters=1)
    assert periods[0].er_doc is None


def test_fallback_keeps_window_guards():
    filing = {"form": "10-Q", "report_date": date(2024, 6, 30), "filing_date": date(2024, 8, 2)}
    good = {"accession": "a1", "filing_date": date(2024, 7, 12), "items": "9.01",
            "primary_doc": "x.htm", "src_cik": "0000831001"}
    too_soon = dict(good, accession="a2", filing_date=date(2024, 7, 2))   # 2 days after period end
    too_late = dict(good, accession="a3", filing_date=date(2024, 9, 1))    # after the 10-Q
    client = MagicMock()
    client.filing_index_url.side_effect = lambda cik, acc: f"https://x/{acc}/"
    client.fetch_text.return_value = (
        '<html><body><a href="/Archives/x/c-20240712xex99d1.htm">x</a></body></html>'
    )
    # Too soon / too late never reach the index fetch.
    assert _match_8k_non202_fallback(filing, [too_soon], "C", "0000831001", client) is None
    assert _match_8k_non202_fallback(filing, [too_late], "C", "0000831001", client) is None
    assert not client.fetch_text.called
    # In-window candidate with a period-referencing exhibit matches.
    m = _match_8k_non202_fallback(filing, [good], "C", "0000831001", client)
    assert m is not None and m[0]["accession"] == "a1" and m[1] == "c-20240712xex99d1.htm"


def test_fallback_rescues_post_filing_non202_8k():
    # Batch 113: the non-2.02 fallback shares the two-pool guards — a 9.01
    # earnings 8-K furnished 2 days after the 10-Q still matches when its
    # exhibit is release-looking and period-referencing.
    filing = {"form": "10-Q", "report_date": date(2024, 6, 30), "filing_date": date(2024, 8, 2)}
    late = {"accession": "a4", "filing_date": date(2024, 8, 4), "items": "9.01",
            "primary_doc": "c-20240804x8k.htm", "src_cik": "0000831001"}
    client = MagicMock()
    client.filing_index_url.side_effect = lambda cik, acc: f"https://x/{acc}/"
    client.fetch_text.return_value = (
        '<html><body><a href="/Archives/x/c-20240804xex99d1.htm">x</a></body></html>'
    )
    matched, doc = _match_8k_non202_fallback(filing, [late], "C", "0000831001", client)
    assert matched["accession"] == "a4"
    assert doc == "c-20240804xex99d1.htm"
