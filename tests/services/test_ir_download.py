"""Unit tests for ir_download._pick_release_doc (pure filename matching)."""

from tickerlens.services.ir_download import _pick_release_doc


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
