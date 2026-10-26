"""Batch 128: Cognizant's 99.1 exhibit carries the quarter-end date directly
after the 99.1 marker (exhibit9916302026.htm = 99.1, 6/30/2026)."""

from tickerlens.services.ir_download import (
    _pick_release_doc,
    _release_name_rank,
)


def test_ctsh_date_run_991_exhibit_wins():
    # CTSH Q2-2026 8-K index: the 99.1 release, the 99.2 tables exhibit,
    # the 99.3 exhibit, and the primary 8-K doc. Only the 99.1 release
    # may win — the 99.2/99.3 supplements carry 992/993, not 991.
    links = [
        "/Archives/edgar/data/1058290/000105829026000030/ctsh-20260729.htm",
        "/Archives/edgar/data/1058290/000105829026000030/exhibit9916302026.htm",
        "/Archives/edgar/data/1058290/000105829026000030/exhibit9926302026.htm",
        "/Archives/edgar/data/1058290/000105829026000030/exhibit9936302026.htm",
        "/Archives/edgar/data/1058290/000105829026000030/R1.htm",
    ]
    assert _pick_release_doc(links) == "exhibit9916302026.htm"
    assert _pick_release_doc(list(reversed(links))) == "exhibit9916302026.htm"


def test_date_run_991_ranks_tier_0():
    assert _release_name_rank("exhibit9916302026.htm") == (0, 0)
    # 8-digit (zero-padded) date run, same convention.
    assert _release_name_rank("exhibit99106302026.htm") == (0, 0)


def test_date_run_guards_preserved():
    # 99.2/99.3 supplements never match, whatever follows the marker.
    assert _release_name_rank("exhibit9926302026.htm") is None
    assert _release_name_rank("exhibit9936302026.htm") is None
    # A short digit run after 991 is still not a date (doc9912final guard).
    assert _release_name_rank("doc9912final.htm") is None
    # A 5-digit run is not a date run either.
    assert _release_name_rank("exhibit99163020.htm") is None
