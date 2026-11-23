"""Batch 242: highlights sweep gate S4 — the 82 SKIP-first-diff rows
from the batch 231/232 source-verified stale-row sweep (as
re-censused by batch 241).

Root causes, all in the sweep comparison / gate (scripts/
batch231_repair.py norm, scripts/batch242_repair.py gate S4), not
the extractor — the live extraction was already right; only the
stored rows were stale or the census was wrong:

- Stored-leading chrome the live extraction never carries: a bare
  release-date line (AGNC "October 21, 2024", NFLX + "Fellow
  shareholders,"), a contact block (ECL name+phone, AWK role lines
  + bare phone, EL "Investors:"/"Media:" labels), a masthead (GD
  street address / city-state-ZIP / "www.gd.com"). Stripped from
  the front only; the loss check behind the strip still proves
  every remaining stored line is in live.
- Headline wrap / prefix: the stored headline is the live headline
  split across two lines (DGX/DKS JOIN) or truncated at a clause
  boundary (DD/EQIX/ET/DRI PREFIX). JOIN is tried before PREFIX —
  a wrapped headline is also a prefix, but only JOIN consumes the
  continuation line. OFFSET covers stored rows that never carried
  the live headline lines at all (AGNC/ECL/AWK bullets start at
  live's line 1 or 2).
- Single-line flattening (CTVA): the stored row is one line,
  headline + bullets joined with " • ". Splitting on the bullet
  glyph recovers the lines; adjacent parts re-join with " – " where
  the live extraction fuses them (dateline-into-lede, "Cash provided
  by operating activities – continuing operations ..."). The dash
  join is verified against the live lines.
- Spacing-only (norm fixes): a space before a comma/period
  ("The Perfect Couple , Nobody", Netflix), a spaced ordinal
  ("3 rd Quarter", Booking), a footnote key spaced off a word
  ("sales 1 increase", "Consolidated Darden 1", Darden). All three
  only remove spaces and preserve every non-space character, so
  content differences still differ after norm.

The gate pins below use synthetic stored/live pairs modeled line
for line on the real rows (the DB rows are already re-synced, so
the pre-repair text is reconstructed from the probe diffs); the
norm pins use the real line strings verbatim.
"""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def _load_script(name: str):
    path = REPO / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sweep = _load_script("batch231_repair")
rep = _load_script("batch242_repair")
norm = sweep.norm


# --- norm() canonicalization (batch 242) --------------------------------

def test_norm_space_before_comma_or_period():
    for stored, live in [
        ("The Perfect Couple , Nobody Wants This",
         "The Perfect Couple, Nobody Wants This"),
        ("returned favorites like Emily in Paris and Cobra Kai , and big film",
         "returned favorites like Emily in Paris and Cobra Kai, and big film"),
        ("Sales rose 5% .", "Sales rose 5%."),
    ]:
        assert norm(stored) == norm(live), (stored, live)
    # Unchanged where there is no space to remove; content still differs.
    assert norm("a, b") == "a, b"
    assert norm("Couple , Nobody") != norm("Couple, Somebody")


def test_norm_spaced_ordinal():
    for stored, live in [
        ("Booking Holdings Reports Financial Results for 3 rd Quarter 2024",
         "Booking Holdings Reports Financial Results for 3rd Quarter 2024"),
        ("the 21 st Century", "the 21st Century"),
        ("2 nd Quarter 2025", "2nd Quarter 2025"),
    ]:
        assert norm(stored) == norm(live), (stored, live)
    # No collapse without the digit+space+ordinal shape.
    assert norm("Q3 2024") == "Q3 2024"
    assert norm("1 story") == "1 story"
    assert norm("3 rd Quarter") != norm("3 th Quarter")


def test_norm_word_spaced_footnote_key():
    for stored, live in [
        ("same-restaurant sales 1 increase of 4.6%",
         "same-restaurant sales1 increase of 4.6%"),
        ("Consolidated Darden 1", "Consolidated Darden1"),
        ("Other Business 1", "Other Business1"),
        ("an increase of 12.5% 3", "an increase of 12.5%3"),
        ("an increase of 22.8% 2", "an increase of 22.8%2"),
    ]:
        assert norm(stored) == norm(live), (stored, live)
    # A different key still differs; years, two-digit numbers and
    # digit-led tokens never collapse.
    assert norm("sales 1 increase") != norm("sales 2 increase")
    assert norm("12.5% 3") != norm("12.5% 4")
    assert norm("Q3 2024") == "Q3 2024"
    assert norm("year 2024") == "year 2024"
    assert norm("up 10 percent") == "up 10 percent"
    assert norm("2024 1") == "2024 1"
    assert norm("12.5% 30") == "12.5% 30"


# --- stored-leading chrome predicates ------------------------------------

def test_chrome_bare_date_line():
    for ln in ["October 21, 2024", "July 17, 2025", "January 27, 2025"]:
        assert rep._is_bare_date_line(ln), ln
    for ln in [
        "October 21, 2024 — American Airlines",
        "FORT WORTH, Texas, October 24, 2024",
        "Q3 2024",
    ]:
        assert not rep._is_bare_date_line(ln), ln


def test_chrome_salutation_line():
    for ln in ["Fellow shareholders,", "Dear shareholders,", "Fellow shareholders"]:
        assert rep._is_salutation_line(ln), ln
    assert not rep._is_salutation_line("Fellow shareholders, welcome")
    assert not rep._is_salutation_line("Dear shareholders, thank you")


def test_chrome_contact_line():
    for ln in [
        "Investors: Rainey Mancini",
        "Media: Jill Marvin",
        "Andrew Hedberg (651) 250-2185",
        "Andrew Hedberg (651) 250-2185 Victoria Whitney (651) 250-4724",
        "856-955-4163",
        "Vice President, Investor Relations",
        "Executive Vice President, Communications and External Affairs",
    ]:
        assert rep._is_contact_line(ln), ln
    for ln in [
        "• Andrew Hedberg (651) 250-2185",
        "American Tower Corporation Reports Third Quarter 2024 Financial Results",
        "Revenue grew 10% to $2,522 million",
        "Senior Vice President, Investor Relations and FP&A Reports",
    ]:
        assert not rep._is_contact_line(ln), ln


def test_chrome_masthead_line():
    for ln in [
        "11011 Sunset Hills Road",
        "Reston, Virginia 20190 News",
        "www.gd.com",
        # The street number itself is five digits, so the ZIP rule
        # catches this too — still masthead, still the right call.
        "11011 Sunset Hills Road, Suite 100",
    ]:
        assert rep._is_masthead_line(ln), ln
    for ln in [
        "• Reston, Virginia 20190",
        "Revenue of $12 billion, up 18% from year-ago quarter",
        "Reston, Virginia 20190, up 18%",
    ]:
        assert not rep._is_masthead_line(ln), ln


def test_strip_leading_chrome_sequences():
    assert rep._strip_leading_chrome([
        "October 17, 2024",
        "Fellow shareholders,",
        "• In Q3, revenue grew 15% year over year.",
    ]) == ["• In Q3, revenue grew 15% year over year."]
    assert rep._strip_leading_chrome([
        "11011 Sunset Hills Road",
        "Reston, Virginia 20190 News",
        "www.gd.com",
        "General Dynamics Reports Second-Quarter 2024 Financial Results",
        "• Revenue of $12 billion, up 18% from year-ago quarter",
    ]) == [
        "General Dynamics Reports Second-Quarter 2024 Financial Results",
        "• Revenue of $12 billion, up 18% from year-ago quarter",
    ]
    # Only the front is stripped: a contact line later in the text stays.
    assert rep._strip_leading_chrome([
        "• Reported sales $4.0 billion, +1% versus last year",
        "Andrew Hedberg (651) 250-2185",
    ]) == [
        "• Reported sales $4.0 billion, +1% versus last year",
        "Andrew Hedberg (651) 250-2185",
    ]


# --- headline alignment ---------------------------------------------------

def test_align_headline_prefix():
    stored = [
        "DuPont Reports Third Quarter 2025 Results;",
        "• Net Sales of $3.1 billion increased 7%",
    ]
    live = [
        "DuPont Reports Third Quarter 2025 Results; Announces Plans to Return Cash to Shareholders",
        "• Net Sales of $3.1 billion increased 7%",
    ]
    eff, rel = rep._align_headline(stored, live)
    assert rel == "PREFIX"
    assert eff[0] == live[0]


def test_align_headline_join_before_prefix():
    stored = [
        "Quest Diagnostics Reports Third Quarter 2024 Financial Results;",
        "Updates Guidance for Full Year 2024",
        "• Third quarter revenues of $2.49 billion, up 8.5% from 2023",
    ]
    live = [
        "Quest Diagnostics Reports Third Quarter 2024 Financial Results; Updates Guidance for Full Year 2024",
        "• Third quarter revenues of $2.49 billion, up 8.5% from 2023",
    ]
    eff, rel = rep._align_headline(stored, live)
    # The stored first line is also a prefix of the live headline, but
    # JOIN must win: only it consumes the continuation line.
    assert rel == "JOIN"
    assert eff == live


def test_align_headline_join_refuses_bullet_continuation():
    # Darden: the second stored line is a bullet, so JOIN is refused
    # and PREFIX aligns the headline instead.
    stored = [
        "Darden Restaurants Reports Fiscal 2025 Second Quarter Results;",
        "• Total sales increased 6.0% to $2.9 billion",
    ]
    live = [
        "Darden Restaurants Reports Fiscal 2025 Second Quarter Results; Declares Quarterly Dividend; And Updates Fiscal 2025 Financial Outlook",
        "• Total sales increased 6.0% to $2.9 billion",
    ]
    eff, rel = rep._align_headline(stored, live)
    assert rel == "PREFIX"
    assert eff[0] == live[0]
    assert eff[1] == stored[1]


def test_align_headline_offset():
    stored = [
        "• $0.63 comprehensive income per common share, comprised of:",
        "◦ $0.39 net income per common share",
    ]
    live = [
        "AGNC INVESTMENT CORP. ANNOUNCES THIRD QUARTER 2024 FINANCIAL RESULTS",
        "• $0.63 comprehensive income per common share, comprised of:",
        "◦ $0.39 net income per common share",
    ]
    eff, rel = rep._align_headline(stored, live)
    assert rel == "OFFSET"
    assert eff == stored


def test_align_headline_no_match():
    stored = ["• $(0.11) comprehensive loss per common share, comprised of:"]
    live = [
        "AGNC INVESTMENT CORP. ANNOUNCES FOURTH QUARTER 2024 FINANCIAL RESULTS",
        "• $0.84 comprehensive income per common share, comprised of:",
    ]
    _, rel = rep._align_headline(stored, live)
    assert rel is None


# --- single-line flattening (Corteva) -------------------------------------

_CTVA_HEADLINE = (
    "1 News Release 3Q 2024 Corteva Reports Third Quarter and "
    "Year-to-Date 2024 Results, Updates Full-Year 2024 Guidance, "
    "Provides 2025 Preliminary Outlook"
)


def test_split_flattened_basic():
    stored = (
        _CTVA_HEADLINE
        + " • 3Q YTD performance reflects Seed price / mix gains"
        + " • 3Q results and Full Year 2024 impacted by Latin America"
    )
    live = [
        _CTVA_HEADLINE,
        "• 3Q YTD performance reflects Seed price / mix gains",
        "• 3Q results and Full Year 2024 impacted by Latin America",
    ]
    assert rep._split_flattened([stored], live) == live


def test_split_flattened_dash_join():
    stored = (
        _CTVA_HEADLINE
        + " • Preliminary 2025 outlook for strong growth INDIANAPOLIS, Ind., November 6, 2024"
        + " • Corteva, Inc. (NYSE: CTVA) today reported financial results"
        + " • Net sales declined 4% versus prior year"
    )
    live = [
        _CTVA_HEADLINE,
        "• Preliminary 2025 outlook for strong growth INDIANAPOLIS, Ind., November 6, 2024 – Corteva, Inc. (NYSE: CTVA) today reported financial results",
        "• Net sales declined 4% versus prior year",
    ]
    assert rep._split_flattened([stored], live) == live


def test_split_flattened_guards():
    live = [_CTVA_HEADLINE, "• A bullet"]
    # No bullets to split on.
    assert rep._split_flattened(["Disclaimers Cautionary Note"], live) == [
        "Disclaimers Cautionary Note"
    ]
    # Headline does not match live: no split.
    stored = _CTVA_HEADLINE.replace("Corteva", "OtherCo") + " • A • B • C"
    assert rep._split_flattened([stored], live) == [stored]
    # Multi-line stored: no split.
    assert rep._split_flattened(["line one", "line two"], live) == [
        "line one",
        "line two",
    ]


# --- gate S4 pins (synthetic pairs modeled on the real rows) --------------

def test_gate_s4_agnc_date_offset():
    stored = (
        "October 21, 2024\n"
        "• $0.63 comprehensive income per common share, comprised of:\n"
        "◦ $0.39 net income per common share"
    )
    live = (
        "AGNC INVESTMENT CORP. ANNOUNCES THIRD QUARTER 2024 FINANCIAL RESULTS\n"
        "• $0.63 comprehensive income per common share, comprised of:\n"
        "◦ $0.39 net income per common share"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_agnc_figure_mismatch_still_blocks():
    stored = (
        "January 27, 2025\n"
        "• $(0.11) comprehensive loss per common share, comprised of:\n"
        "◦ $0.10 net income per common share"
    )
    live = (
        "AGNC INVESTMENT CORP. ANNOUNCES FOURTH QUARTER 2024 FINANCIAL RESULTS\n"
        "• $0.84 comprehensive income per common share, comprised of:\n"
        "◦ $0.93 net income per common share"
    )
    assert rep.sweep_gate_s4(stored, live) == "first-diff"


def test_gate_s4_ecl_contact_offset():
    stored = (
        "Andrew Hedberg (651) 250-2185\n"
        "● Reported sales $4.0 billion, +1% versus last year\n"
        "● Organic sales +4%"
    )
    live = (
        "ECOLAB DELIVERS CONTINUED STRONG GROWTH IN THE THIRD QUARTER REPORTED DILUTED EPS $2.58; ADJUSTED DILUTED EPS $1.83, +19%\n"
        "● Reported sales $4.0 billion, +1% versus last year\n"
        "● Organic sales +4%"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_awk_contact_offset():
    stored = (
        "Vice President, Investor Relations\n"
        "Executive Vice President, Communications and External Affairs\n"
        "856-955-4163\n"
        "• Reported 2024 earnings of $5.39 per share, compared to $4.90 per share in 2023"
    )
    live = (
        "AMERICAN WATER REPORTS 2024 RESULTS ON TRACK\n"
        "CEO HARDWICK TO RETIRE IN MAY; GRIFFITH TO ASSUME CEO ROLE\n"
        "• Reported 2024 earnings of $5.39 per share, compared to $4.90 per share in 2023"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_gd_masthead():
    stored = (
        "11011 Sunset Hills Road\n"
        "Reston, Virginia 20190 News\n"
        "General Dynamics Reports Second-Quarter 2024 Financial Results\n"
        "• Revenue of $12 billion, up 18% from year-ago quarter"
    )
    live = (
        "General Dynamics Reports Second-Quarter 2024 Financial Results\n"
        "• Revenue of $12 billion, up 18% from year-ago quarter"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_el_contact_headline():
    stored = (
        "Investors: Rainey Mancini\n"
        "Media: Jill Marvin\n"
        "THE ESTÉE LAUDER COMPANIES REPORTS FISCAL 2025 SECOND QUARTER RESULTS\n"
        "• Net sales increased 5% to $4.0 billion"
    )
    live = (
        "THE ESTÉE LAUDER COMPANIES REPORTS FISCAL 2025 SECOND QUARTER RESULTS\n"
        "• Net sales increased 5% to $4.0 billion"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_dgx_join():
    stored = (
        "Quest Diagnostics Reports Second Quarter 2025 Financial Results;\n"
        "Raises Guidance for Full Year 2025\n"
        "• Second quarter revenues of $2.76 billion, up 15.2% from 2024\n"
        "• Second quarter reported diluted earnings per share (\"EPS\") of $2.47, up 21.7% from 2024"
    )
    live = (
        "Quest Diagnostics Reports Second Quarter 2025 Financial Results; Raises Guidance for Full Year 2025\n"
        "• Second quarter revenues of $2.76 billion, up 15.2% from 2024\n"
        "• Second quarter reported diluted earnings per share (\"EPS\") of $2.47, up 21.7% from 2024"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_dgx_ceo_quote_still_blocks():
    stored = (
        "Quest Diagnostics Reports Third Quarter 2024 Financial Results;\n"
        "Updates Guidance for Full Year 2024\n"
        "• Third quarter revenues of $2.49 billion, up 8.5% from 2023\n"
        "\"We delivered a strong third quarter, with total revenue growth of 8.5%, including 4.2% organic growth,\" said Jim Davis, Chairman, CEO and President."
    )
    live = (
        "Quest Diagnostics Reports Third Quarter 2024 Financial Results; Updates Guidance for Full Year 2024\n"
        "• Third quarter revenues of $2.49 billion, up 8.5% from 2023"
    )
    assert rep.sweep_gate_s4(stored, live) == "loss"


def test_gate_s4_dks_join():
    stored = (
        "DICK'S Sporting Goods Reports First Quarter Results;\n"
        "Delivers Record First Quarter Sales and 4.5% Comparable Sales Growth\n"
        "– Delivers Double-Digit EBT Margin of 11.0% and Non-GAAP EBT Margin of 11.4% –"
    )
    live = (
        "DICK'S Sporting Goods Reports First Quarter Results; Delivers Record First Quarter Sales and 4.5% Comparable Sales Growth\n"
        "– Delivers Double-Digit EBT Margin of 11.0% and Non-GAAP EBT Margin of 11.4% –"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_dd_prefix():
    stored = (
        "DuPont Reports Third Quarter 2025 Results;\n"
        "• Net Sales of $3.1 billion increased 7%; organic sales increased 6% versus year-ago period"
    )
    live = (
        "DuPont Reports Third Quarter 2025 Results; Announces Plans to Return Cash to Shareholders\n"
        "• Net Sales of $3.1 billion increased 7%; organic sales increased 6% versus year-ago period"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_et_prefix():
    stored = (
        "ENERGY TRANSFER REPORTS FOURTH QUARTER 2024 RESULTS\n"
        "• Energy Transfer's volumes continued to grow during the fourth quarter of 2024.\n"
        "◦ Crude oil transportation volumes were up 15%."
    )
    live = (
        "ENERGY TRANSFER REPORTS FOURTH QUARTER 2024 RESULTS AND ANNOUNCES 2025 OUTLOOK\n"
        "• Energy Transfer's volumes continued to grow during the fourth quarter of 2024.\n"
        "◦ Crude oil transportation volumes were up 15%."
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_dri_prefix_with_footnote_spacing():
    stored = (
        "Darden Restaurants Reports Fiscal 2025 Fourth Quarter and Full Year Results;\n"
        "• Total sales increased 10.6% to $3.3 billion driven by a blended same-restaurant sales 1 increase of 4.6%\n"
        "Consolidated Darden 1"
    )
    live = (
        "Darden Restaurants Reports Fiscal 2025 Fourth Quarter and Full Year Results; Increases Quarterly Dividend; Authorizes New $1 Billion Share Repurchase Program; And Provides Fiscal 2026 Outlook\n"
        "• Total sales increased 10.6% to $3.3 billion driven by a blended same-restaurant sales1 increase of 4.6%\n"
        "Consolidated Darden1"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_bkng_ordinal_and_dateline():
    stored = (
        "Booking Holdings Reports Financial Results for 3 rd Quarter 2024\n"
        "NORWALK, CT – October 30, 2024. Booking Holdings Inc. (NASDAQ: BKNG) today reported its third quarter 2024 financial results.\n"
        "• Room nights booked increased 8% from the prior-year quarter."
    )
    live = (
        "Booking Holdings Reports Financial Results for 3rd Quarter 2024\n"
        "• Room nights booked increased 8% from the prior-year quarter."
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_nflx_date_salutation_and_comma_spacing():
    stored = (
        "October 17, 2024\n"
        "Fellow shareholders,\n"
        "• In Q3, revenue grew 15% year over year and operating margin was 30% vs. 22% last year.\n"
        "• We've delivered a string of hits this quarter, including new series like The Perfect Couple , Nobody Wants This and Tokyo Swindlers"
    )
    live = (
        "• In Q3, revenue grew 15% year over year and operating margin was 30% vs. 22% last year.\n"
        "• We've delivered a string of hits this quarter, including new series like The Perfect Couple, Nobody Wants This and Tokyo Swindlers\n"
        "Our summary results, and forecast for Q4, are below."
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_nflx_different_selection_still_blocks():
    stored = (
        "July 17, 2025\n"
        "• A number of hit series including Sirens (56M views), Ginny & Georgia S3 (53M views)\n"
        "• Non-English language series and films represented more than one-third of all Netflix viewing"
    )
    live = (
        "• Our business continues to perform well. In Q2, we grew revenue 16% and our operating margin of 34% expanded seven points year over year.\n"
        "• We now forecast 2025 revenue of $44.8-$45.2B, up from $43.5-$44.5B"
    )
    assert rep.sweep_gate_s4(stored, live) == "first-diff"


def test_gate_s4_ctva_split():
    stored = (
        _CTVA_HEADLINE
        + " • 3Q YTD performance reflects Seed price / mix gains"
        + " • 3Q results and Full Year 2024 impacted by Latin America"
    )
    live = (
        _CTVA_HEADLINE + "\n"
        "• 3Q YTD performance reflects Seed price / mix gains\n"
        "• 3Q results and Full Year 2024 impacted by Latin America"
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_ctva_split_with_added_bullets():
    # The 2025-09-30 shape: live adds separation bullets the stored
    # single line never carried — bullets/prose, never table rows.
    stored = (
        _CTVA_HEADLINE
        + " • 3Q YTD performance reflects Seed price / mix gains"
        + " • 3Q results and Full Year 2024 impacted by Latin America"
    )
    live = (
        _CTVA_HEADLINE + "\n"
        "• 3Q YTD performance reflects Seed price / mix gains\n"
        "• 3Q results and Full Year 2024 impacted by Latin America\n"
        "• Distinct Market Opportunities: The separation enables tailored innovation."
    )
    assert rep.sweep_gate_s4(stored, live) is None


def test_gate_s4_ctva_changed_figure_still_blocks():
    stored = (
        _CTVA_HEADLINE
        + " • 3Q YTD performance reflects Seed price / mix gains"
        + " • 3Q results and Full Year 2024 impacted by Latin America"
    )
    live = (
        _CTVA_HEADLINE + "\n"
        "• 3Q YTD performance reflects Seed price / mix gains\n"
        "• 3Q results and Full Year 2024 impacted by EMEA destocking"
    )
    assert rep.sweep_gate_s4(stored, live) == "loss"


def test_gate_s4_amt_table_still_blocks():
    stored = (
        "AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS\n"
        "On September 12, 2024, American Tower Corporation completed the sale of 100% of the equity interests in its operations in India.\n"
        "CONSOLIDATED HIGHLIGHTS"
    )
    live = (
        "Senior Vice President, Investor Relations and FP&A\n"
        "AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS\n"
        "● Total revenue grew by less than 0.1% to $2,522 million"
    )
    assert rep.sweep_gate_s4(stored, live) == "loss"


def test_gate_s4_coin_slide_junk_still_blocks():
    stored = (
        "Disclaimers Cautionary Note Regarding Forward-Looking Statements "
        "This presentation contains forward-looking statements"
    )
    live = (
        "Slide 1 Our mission is to increase economic freedom in the world\n"
        "• Global"
    )
    assert rep.sweep_gate_s4(stored, live) == "first-diff"
