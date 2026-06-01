# Product Requirements Document: Tickerlens (Personal Tool)

**Product name:** Tickerlens
**Version:** 1.0 (Personal-Use Scope)
**Last Updated:** May 27, 2026
**Status:** Personal project — single user (founder)

---

## 1. Purpose

A personal research tool for analyzing US public companies. Built by and for the founder to streamline earnings analysis on their own portfolio and watchlist. **Not a commercial product.** No users besides the founder, no payments, no marketing.

If the tool proves useful in practice, commercialization is a possible future direction — but that decision is deferred until the tool has been used personally for a meaningful period and has demonstrated real value.

---

## 2. Why Build This for Yourself First

- **Validate the product against reality.** The founder is an active investor — daily use will surface what actually matters versus what sounded good in planning.
- **Zero customer overhead.** No support, no billing, no legal docs, no privacy obligations, no onboarding flow. All energy goes into the analysis itself.
- **Fast iteration.** Change anything at any time. Refactor when needed. No backwards-compatibility burden.
- **Cost discipline.** Built on free data sources only — no subscription expenses to justify.
- **Optionality.** If the tool turns out to be valuable, the productization PRD (v0.4) is in the archive and ready to revisit.

---

## 3. Scope

### In Scope
- US public companies only (SEC EDGAR as primary source)
- Data extraction: 10-K, 10-Q (and amendments), earnings press releases, transcripts (where freely available), segment KPIs
- **Overview view** as default landing for any company (description + latest quarter + TTM + revenue breakdown)
- Time slicer with three modes: single period, range, side-by-side compare
- Two separate selectors: Quarterly (e.g., "Q3 FY2025") and Yearly (e.g., "FY2025")
- 3-year historical depth
- Ticker / company-name search with autocomplete
- Watchlist (unlimited; this is your tool)
- Earnings calendar with customizable alerts
- Organized ZIP downloads
- **Market-cap-aware AI analysis** producing factor-based signals (Invest / Swing / Watch / Avoid) with reasoning
- Daily news feed scoped to watchlist (if free APIs allow)

### Out of Scope
- User accounts, signup, login (single-user local or self-hosted)
- Payments, plans, trials, paywalls
- Multi-user features (sharing, public links, collaboration)
- Onboarding flows
- Terms of Service, Privacy Policy, cookie consent
- Marketing emails, newsletter
- Customer support
- International equities, OTC, ADRs
- Options, fixed income, crypto
- Native mobile apps (web responsive is enough)
- Disclaimer modals (you know it's not investment advice — you built it)
- Trial / refund / deletion flows
- Email opt-in mechanics

---

## 4. Core Features

### 4.1 Overview View (Default Landing for Every Company)

When you open a company page, you land on the Overview by default. Contents:

1. **Company header** — name, ticker, current market cap, NAICS-mapped sector bucket, last close price; "Also trades as: [other class]" link if applicable
2. **Company description** — pulled from Wikipedia API. Fallback to first paragraph of SEC 10-K "Item 1: Business" (truncated ~200 words) if Wikipedia returns under 50 words.
3. **Latest quarter snapshot** — KPI cards (Revenue, EPS, Net Income, FCF) with YoY change indicators
4. **TTM annual snapshot** — same KPIs, trailing-twelve-months aggregated
5. **Revenue breakdown** — auto-detected:
   - If both segment and geography data exist → tabbed view
   - If only one exists → single view
   - If neither exists → card hidden
6. **"View detailed periods" button** — navigates to the Time Slicer detail view

### 4.2 Time Slicer

**Two separate selectors:**
- **Quarterly** — pick a specific quarter (e.g., "Q3 FY2025"). Defaults to most recent reported quarter.
- **Yearly** — pick a specific fiscal year (e.g., "FY2025"). Defaults to "all available" (3-year window).

**Three modes:**
1. **Single period** — view one quarter OR one year
2. **Range** — view multiple consecutive periods (e.g., Q1 FY2023 → Q4 FY2025)
3. **Side-by-side compare** — view two specific periods in parallel; supports presets (YoY, QoQ, 5-year-ago) and free-form

**Fiscal year handling:** Years use the company's actual fiscal year (e.g., "FY2025 (ended Sept 2025)").

**Mobile UX:** Compact "Period" button → bottom sheet slides up with selectors + mode toggle + Apply button.

### 4.3 Time Slicer Detail View

1. **Company header** (persistent)
2. **Time slicer** — Quarterly + Yearly selectors + mode picker
3. **Hero KPI row** — Revenue, EPS, Net Income, FCF with color-coded YoY change arrows (QoQ toggle available)
4. **Trend chart** — Revenue + EPS line chart across selected period(s)
5. **Tabbed financial tables** — Income Statement | Balance Sheet | Cash Flow with YoY comparison columns
6. **Collapsible sections** (closed by default):
   - Press release highlights
   - Management guidance
   - Transcript excerpts (when freely available)
   - Risk factors (from 10-K/10-Q)
7. **Sticky "Download" button**

**Missing data UX:** Show "Not available for this period" — section stays visible, you'll know to look elsewhere.

### 4.4 AI Analysis (Integrated from Day 1)

Since you're the only user, AI analysis ships with v1.0 — no need to defer it to a paid tier.

**Market-cap tiers:**
- **Small-cap (<$2B):** growth rate, cash runway, dilution risk, insider ownership, debt coverage
- **Mid-cap ($2B–$10B):** growth-to-profitability transition, margin trends, market share
- **Large-cap ($10B–$200B):** ROIC, FCF generation, capital allocation, segment performance
- **Mega-cap (>$200B):** dividend sustainability, buyback efficiency, moat durability

**Sector overlay:** NAICS-based, with sector-specific weightings on top of cap-tier baseline.

**Output:**
- **Signal:** Invest / Swing / Watch / Avoid
  - Invest = long-term hold (1+ year horizon)
  - Swing = medium-term trade (weeks to months)
  - Watch = wait and monitor
  - Avoid = stay away
- **Confidence:** Low / Medium / High (rule-based weighted score under the hood)
- **Reasoning bullets** — 3–6 points tied to source filings
- **Key risks** — 3–5 risk factors flagged with sources

**LLM provider:** Anthropic Claude (or alternative — defer choice to build phase). Pay-as-you-go API. Cost is your own — you can spend liberally on yourself, vs. having to ration in a paid product.

### 4.5 Earnings Calendar
- Calendar view of upcoming earnings dates for tracked companies
- Customizable alerts: 1 week / 1 day / 1 hour / day-of
- Per-company opt-in/opt-out
- Events tracked: confirmed earnings dates, pre-announcements, guidance updates, dividend dates

### 4.6 Watchlist
- Unlimited (it's your tool)
- Search by ticker or company name with autocomplete
- Companies pinned to home screen by default

### 4.7 Daily News Feed (Watchlist-Scoped)

Best-effort using free APIs:
- Finnhub free tier (60 calls/min — plenty for personal use)
- Yahoo Finance unofficial RSS feeds as a fallback
- AI-generated daily digest of watchlist-related headlines (using your LLM API)

If free APIs become unreliable, this feature degrades gracefully — calendar and earnings analysis are the core, news is the bonus.

### 4.8 Download Format (ZIP Archive)

Organized by year, with quarterly subfolders. Synchronous generation with progress bar. File naming: `TICKER_period_doc-type.pdf`. Includes both your generated PDFs and renamed original SEC PDFs.

Single Quarter, Single Year, Range, and Compare ZIP structures are unchanged from prior PRD — see Section 5.7 of v0.4 if you want the exact folder trees.

### 4.9 Edge Case Handling

| Case | Behavior |
|---|---|
| IPO with limited history | Show whatever exists, banner "Listed since [date]" |
| Ticker change (FB → META) | CIK-based canonical key, ticker is a display label |
| Multiple share classes (GOOGL/GOOG) | Separate entries; "Also trades as" link in header |
| Filing amendment (10-K/A) | Show latest; clickable "Amended on [date]" → diff view |
| Acquisition | Banner + locked read-only historical data |
| Delisting | Banner + read-only data; no calendar entry for future |
| Missing transcript | "Not available for this period" — section visible |

---

## 5. Technical Architecture

### 5.1 Platform
- **Web app, mobile-responsive** — runs in your browser, accessible from laptop and phone
- **Deployment:** Self-hosted (local Docker / Hetzner / Vercel free tier) — your choice based on convenience

### 5.2 Data Sources (All Free)
- **SEC filings:** SEC EDGAR — custom XBRL parser
- **Company descriptions:** Wikipedia API; fallback to 10-K Item 1: Business
- **Sector taxonomy:** NAICS (free)
- **Stock prices:** Yahoo Finance unofficial API
- **Earnings calendar:** Finnhub free tier (60 calls/min)
- **Transcripts:** Best-effort scraping where freely available
- **News:** Finnhub free tier + Yahoo Finance RSS

**Internal canonical key:** SEC CIK — survives ticker changes and share class consolidations.

### 5.3 LLM Provider
- Anthropic Claude API (recommended) or alternative
- Pay-as-you-go; budget is your call

### 5.4 Performance Targets
- Subjective — "feels fast enough for you" replaces formal SLAs
- Solo dev can iterate on perceived performance without contractual obligation

### 5.5 Restated Financials
- Show latest restated numbers
- Every PDF export includes "As of [date]" footer

---

## 6. What's Deliberately Skipped (and Why)

| Skipped | Why |
|---|---|
| User accounts, signup, login | Single user — no auth needed (or simple HTTP basic auth if hosted publicly) |
| Payments, plans, trials | No customers, no money flow |
| Onboarding flows | You configure your own preferences directly in settings |
| Sharing, social, public links | You're the only user |
| Terms of Service, Privacy Policy | No third parties; only your data on your infrastructure |
| Customer support | You support yourself |
| Marketing emails, newsletter | No mailing list to maintain |
| Multi-trial abuse / refund logic | N/A |
| Watchlist limits / free-tier mechanics | Unlimited everything for you |
| Disclaimer modals | You don't need to be told it's not investment advice |
| Analytics, KPI tracking | You'll know if it's useful by whether you use it |
| Branding / logo polish | Functional UI is enough; no users to impress |

This is roughly 40–50% of the original PRD scope removed. You're shipping a tool, not a startup.

---

## 7. Build Sequence (Suggested)

A pragmatic order that gives you a usable tool fast:

**Phase 1 — Get data flowing (weeks 1–4)**
- SEC EDGAR XBRL parser for a single test company (e.g., AAPL)
- Wikipedia API integration for description
- Yahoo Finance prices for current market cap
- NAICS sector lookup
- Local data storage (SQLite or Postgres on your machine)

**Phase 2 — Single-company browsing (weeks 5–8)**
- Overview view for one company
- Time slicer detail view for one company
- Quarterly and yearly selectors working
- Single mode first (Range and Compare deferred slightly)

**Phase 3 — Scale to all US public companies (weeks 9–14)**
- Ingest pipeline for all CIKs
- Search bar with autocomplete
- Watchlist
- Range and Compare modes
- ZIP download

**Phase 4 — Calendar + alerts (weeks 15–18)**
- Earnings calendar
- Email alerts (you can use a free SendGrid / Postmark trial since it's just you)
- Or just write a Python script that texts you — your tool, your rules

**Phase 5 — AI analysis (weeks 19–24)**
- Market-cap-tiered rule engine
- Sector overlay
- LLM integration for reasoning and risk extraction
- Signal output

**Phase 6 — News feed (weeks 25–28)**
- Finnhub / Yahoo RSS ingest
- Daily LLM digest scoped to watchlist

Total: roughly 6 months part-time, 3 months full-time. Faster if you cut features as you build.

---

## 8. Decision Points to Revisit Later

These are explicitly parked for future-you:

1. **Productize?** After 6 months of personal use, decide whether the tool is worth commercializing. The v0.4 PRD is in the archive ready to revisit if so.
2. **Hybrid data strategy?** If self-built EDGAR parsing eats too much time, paying $50/mo to Financial Modeling Prep is a legitimate quality-of-life upgrade — even for a personal tool.
3. **Mobile app?** Only if web responsive becomes painful in your actual workflow.
4. **Sharing watchlists with friends?** Easy to add if useful; skip for now.
5. **Sector overlay precision?** NAICS is fine. If your analysis suffers without GICS, revisit.

---

## 9. Risks (Trimmed for Personal Use)

| Risk | Mitigation |
|---|---|
| Self-built EDGAR parser takes longer than expected | Acceptable. Cut features. Use FMP free or trial paid APIs to bridge if blocked. |
| Yahoo Finance unofficial API breaks | Cache aggressively. Have Finnhub free tier as fallback. |
| LLM costs add up | Cap your own usage. ~$20–50/mo is realistic for one-user daily analysis. |
| Tool isn't actually useful in practice | That's the point of personal-use phase. Better to find out solo than after building a startup around it. |
| Founder time / energy | Set a deadline. If 6 months in you're not using it daily, pivot or shelve. |

---

## 10. Decisions Carried Over from Productization PRD

For reference, decisions made during productization planning that still apply to the personal version:

| # | Decision |
|---|---|
| 1 | US public companies only |
| 2 | Two time selectors (quarterly + yearly) + 3 modes |
| 3 | 3-year historical depth |
| 4 | Fiscal year, not calendar year |
| 5 | Overview view as default landing |
| 6 | Wikipedia → 10-K fallback for company description |
| 7 | Revenue breakdown auto-detected |
| 8 | Dashboard pattern: KPI cards + chart + tabbed tables + collapsibles |
| 9 | ZIP download, year/quarter folder hierarchy |
| 10 | `TICKER_period_doc-type.pdf` naming convention |
| 11 | Show latest restated financials with "As of [date]" footer |
| 12 | Filing amendments: show latest + clickable diff |
| 13 | Multiple share classes: separate entries + "Also trades as" link |
| 14 | Ticker changes: CIK is canonical key |
| 15 | IPOs / acquisitions / delistings: explicit edge case handling |
| 16 | NAICS sectors mapped to simplified UI buckets |
| 17 | Recommendation signals: Invest / Swing / Watch / Avoid |
| 18 | Confidence: Low / Medium / High (rule-based) |
| 19 | Mobile time slicer: bottom sheet pattern |
| 20 | Default comparison column: YoY (with QoQ toggle) |
| 21 | Free-first data strategy: EDGAR + Wikipedia + Yahoo + NAICS + Finnhub free |
