"""Rules-based valuation signal: model target price vs current price.

v1 methodology (PRD §4.11) — deliberately a simple, explainable heuristic, not
a DCF. All inputs come from the company's own EDGAR-derived financials plus a
Yahoo quote; every number on the card is auditable from the reasoning bullets.

Primary method ("peg"): PEG-implied P/E for profitable companies.
    fair_pe = PEG_TARGET * eps_growth_pct   (growth clamped, P/E clamped)
    target  = ttm_diluted_eps * fair_pe

Fallback ("sales"): for companies without usable earnings. The fair P/S is
margin-anchored via the accounting identity P/S = P/E x net margin, using
the same PEG-implied fair P/E curve as the primary method and the company's
own TTM net margin (batch 26). A growth-implied P/S with no profitability
anchor overvalues structurally low-margin businesses (e.g. Ford at 1.9x
sales on 3.8% revenue growth while loss-making). When the TTM net margin is
not positive there is nothing to anchor the multiple to, so the model
returns Watch/unavailable instead of a fabricated target.

Signal thresholds are on implied upside = (target - price) / price.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# PEG of 1.5 ~= "fair" multiple for a quality grower (Peter Lynch's rule of
# thumb is PEG <= 1 for cheap; 1.5 leaves headroom so only genuine growers
# screen as Buys).
PEG_TARGET = 1.5
# Growth above 40% rarely persists; below 2% deserves no growth premium.
_MIN_GROWTH_PCT = 2.0
_MAX_GROWTH_PCT = 40.0
# Sanity clamps so the model never emits a 200x P/E or a distressed 3x.
_MIN_PE = 8.0
_MAX_PE = 40.0
# Upper sanity bound on the margin-anchored fair P/S (batch 26). There is no
# lower bound: the identity P/S = P/E x margin can legitimately be small for
# thin-margin businesses, and a floor would inflate the target.
_MAX_PS = 10.0

# Rate-aware guardrail (batch 12): the PEG multiple is blind to the discount
# rate. A 40x fair P/E implies a 2.5% earnings yield — indefensible when the
# 10-year Treasury pays 5%+. Cap fair P/E so the implied earnings yield stays
# at least _YIELD_COVERAGE of the 10-year yield. Growth equities earn
# latitude vs risk-free (they grow), so coverage is < 1; at low yields the
# 40x clamp binds first and this guardrail sleeps.
_TEN_YEAR_YIELD_DEFAULT_PCT = 4.5
_YIELD_COVERAGE = 0.6

_STRONG_BUY_UP = 30.0
_BUY_UP = 10.0
_SELL_DOWN = -10.0
_STRONG_SELL_DOWN = -25.0


class ValuationSignal(BaseModel):
    """Everything the Overview valuation card needs."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    current_price: float | None
    target_price: float | None
    upside_pct: float | None  # implied upside in percent, e.g. 23.5
    signal: str  # Strong Buy | Buy | Hold | Sell | Strong Sell | Watch
    confidence: str  # High | Medium | Low
    method: str  # "peg" | "sales" | "unavailable"
    fair_multiple: float | None  # the P/E or P/S the model deemed fair
    current_multiple: float | None  # where the market prices it today
    growth_pct: float | None  # the growth input, in percent
    reasoning: list[str]
    fcf_note: str | None = None  # FCF-yield cross-check footnote (PRD §4.11)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _signal_for_upside(upside_pct: float) -> str:
    if upside_pct >= _STRONG_BUY_UP:
        return "Strong Buy"
    if upside_pct >= _BUY_UP:
        return "Buy"
    if upside_pct >= _SELL_DOWN:
        return "Hold"
    if upside_pct >= _STRONG_SELL_DOWN:
        return "Sell"
    return "Strong Sell"


def _fair_pe_for_growth(
    growth_pct: float, ten_year_yield_pct: float | None
) -> tuple[float, str | None]:
    """PEG-implied fair P/E for a growth rate, with the batch-12 rate guardrail.

    Shared by the primary (earnings) path and the sales fallback so both
    value the same growth curve (batch 26).
    """
    growth = _clamp(growth_pct, _MIN_GROWTH_PCT, _MAX_GROWTH_PCT)
    fair_pe = _clamp(PEG_TARGET * growth, _MIN_PE, _MAX_PE)
    yld = ten_year_yield_pct
    if yld is None or yld <= 0:
        yld = _TEN_YEAR_YIELD_DEFAULT_PCT
    max_pe_by_yield = 100.0 / (yld * _YIELD_COVERAGE)
    rate_note: str | None = None
    if fair_pe > max_pe_by_yield:
        fair_pe = max_pe_by_yield
        rate_note = _rate_guardrail_note(yld, max_pe_by_yield)
    return fair_pe, rate_note


# FCF-yield hurdle for the cross-check footnote: roughly the long-run
# earnings yield of the broad market.
_FCF_YIELD_HURDLE_PCT = 4.0

_BULLISH_SIGNALS = {"Strong Buy", "Buy"}
_BEARISH_SIGNALS = {"Strong Sell", "Sell"}


def _rate_guardrail_note(
    ten_year_yield_pct: float,
    max_pe_by_yield: float,
) -> str:
    """Explain a binding rate guardrail (batch 12).

    Mirrors the _guardrail_note contract: the target is driven by the rate
    environment rather than the company's data, so confidence is capped.
    """
    return (
        f"Note: the 10-year Treasury is at {ten_year_yield_pct:.1f}% — fair P/E "
        f"capped at {max_pe_by_yield:.1f}× so the implied earnings yield stays "
        f"competitive with risk-free rates; the target is driven by the rate "
        f"environment, so confidence is capped at Medium."
    )


def _fcf_cross_check_note(
    signal: str,
    ttm_free_cash_flow: float | None,
    market_cap: float | None,
) -> str:
    """One-line cash-flow footnote for the valuation card (PRD §4.11).

    Independent of the PEG/sales model — it never changes the signal, only
    adds context. Negative or missing FCF is reported honestly instead of
    hidden.
    """
    if ttm_free_cash_flow is None or market_cap is None or market_cap <= 0:
        return "Cross-check unavailable: TTM free cash flow or market cap not reported."
    fcf_yield = ttm_free_cash_flow / market_cap * 100.0
    if ttm_free_cash_flow <= 0:
        if signal in _BEARISH_SIGNALS:
            return (
                f"Cross-check: TTM free cash flow is negative "
                f"(FCF yield {fcf_yield:.1f}%) — consistent with the {signal} signal."
            )
        return (
            f"Cross-check: TTM free cash flow is negative "
            f"(FCF yield {fcf_yield:.1f}%) — the business is burning cash, "
            f"which tempers the {signal} signal."
        )
    base = (
        f"Cross-check: FCF yield {fcf_yield:.1f}% "
        f"({'above' if fcf_yield >= _FCF_YIELD_HURDLE_PCT else 'below'} "
        f"the {_FCF_YIELD_HURDLE_PCT:.0f}% hurdle)."
    )
    if signal in _BULLISH_SIGNALS:
        verdict = (
            "Supports the signal — cheap on cash too."
            if fcf_yield >= _FCF_YIELD_HURDLE_PCT
            else "Tempers the signal — pricey on cash flow."
        )
    elif signal in _BEARISH_SIGNALS:
        verdict = (
            "Tempers the signal — cheap on cash flow."
            if fcf_yield >= _FCF_YIELD_HURDLE_PCT
            else "Supports the signal — expensive on cash as well."
        )
    else:
        verdict = ""
    return f"{base} {verdict}".rstrip()


def _guardrail_note(
    growth_pct: float,
    growth_lo: float,
    growth_hi: float,
    raw_multiple: float,
    multiple_lo: float,
    multiple_hi: float,
    multiple_name: str,
) -> str | None:
    """Name the clamp bound(s) driving the target, or None if none bound.

    Takes the *pre-clamp* multiple: when a guardrail binds, the signal is
    driven by the guardrail rather than the data — the card must say so and
    cap confidence at Medium (PRD §4.11).
    """
    hit: list[str] = []
    if growth_pct < growth_lo:
        hit.append(f"growth {growth_pct:.1f}% hit the {growth_lo:.0f}% floor")
    elif growth_pct > growth_hi:
        hit.append(f"growth {growth_pct:.1f}% hit the {growth_hi:.0f}% cap")
    if raw_multiple < multiple_lo:
        hit.append(f"fair {multiple_name} hit the {multiple_lo:.0f}× floor")
    elif raw_multiple > multiple_hi:
        hit.append(f"fair {multiple_name} hit the {multiple_hi:.0f}× cap")
    if not hit:
        return None
    return (
        "Note: " + " and ".join(hit) + " — the target is driven by the "
        "model's guardrails, so confidence is capped at Medium."
    )


def compute_valuation(
    *,
    ticker: str,
    current_price: float | None,
    ttm_eps_diluted: float | None,
    eps_growth_pct: float | None,
    ttm_revenue: float | None,
    revenue_growth_pct: float | None,
    shares_outstanding: float | None,
    ttm_quarters: int = 4,
    growth_is_fallback: bool = False,
    ttm_net_income: float | None = None,
    ttm_free_cash_flow: float | None = None,
    market_cap: float | None = None,
    ten_year_yield_pct: float | None = None,
) -> ValuationSignal:
    """Compute the valuation signal from TTM financials and a market price.

    Pure function — all inputs are plain numbers so the math is unit-testable
    without a database. ``growth_is_fallback`` marks that the growth input
    came from a quarterly YoY / net-income proxy rather than TTM-over-TTM.
    ``ttm_net_income`` anchors the sales fallback's fair P/S via the
    identity P/S = P/E x net margin (batch 26); ``ttm_free_cash_flow`` /
    ``market_cap`` feed the FCF-yield cross-check footnote only; they never
    change the signal. ``ten_year_yield_pct`` is the 10-year Treasury yield
    in percent (batch 12 rate guardrail); ``None`` uses the module default
    benchmark.
    """
    if current_price is None or current_price <= 0:
        return ValuationSignal(
            ticker=ticker,
            current_price=current_price,
            target_price=None,
            upside_pct=None,
            signal="Watch",
            confidence="Low",
            method="unavailable",
            fair_multiple=None,
            current_multiple=None,
            growth_pct=None,
            reasoning=[
                "No current price available — refresh the company to fetch a quote.",
                "Target price needs a market price to compare against.",
            ],
        )

    confidence = (
        "High"
        if ttm_quarters >= 4 and not growth_is_fallback
        else "Medium"
    )

    # ── Non-operating-earnings guard (batch 36) ───────────────────────────
    # A TTM net margin above 100% means earnings exceed the top line — only
    # possible via non-operating items (mortgage REITs book unrealized
    # portfolio gains/losses through net income; NLY's TTM net income is
    # ~162% of its net interest income). A PEG growth multiple — or a
    # margin-anchored sales multiple — on that EPS values mark-to-market
    # noise, not the business, so the model returns Watch/unavailable with
    # honest copy instead of a fabricated target (NLY rendered Strong Buy
    # +734% on the PEG path before this guard). Mirrors the batch-26
    # non-positive-margin guard on the sales path: both directions of
    # margin absurdity mean "no multiple applies".
    operating_margin: float | None = None
    if ttm_net_income is not None and ttm_revenue is not None and ttm_revenue > 0:
        operating_margin = ttm_net_income / ttm_revenue
    if operating_margin is not None and operating_margin > 1.0:
        return ValuationSignal(
            ticker=ticker,
            current_price=current_price,
            target_price=None,
            upside_pct=None,
            signal="Watch",
            confidence="Low",
            method="unavailable",
            fair_multiple=None,
            current_multiple=None,
            growth_pct=round(eps_growth_pct, 1) if eps_growth_pct is not None else None,
            reasoning=[
                f"TTM net income is {operating_margin * 100:.0f}% of TTM revenue — "
                "earnings exceed the top line, so they are dominated by "
                "non-operating items (e.g. unrealized gains/losses), not the "
                "business's earning power.",
                "A growth multiple on that EPS would value accounting noise, "
                "not the company — no target until earnings reflect operations.",
            ],
        )

    # ── Primary: PEG-implied P/E ──────────────────────────────────────────
    if ttm_eps_diluted is not None and ttm_eps_diluted > 0 and eps_growth_pct is not None:
        raw_pe = PEG_TARGET * _clamp(eps_growth_pct, _MIN_GROWTH_PCT, _MAX_GROWTH_PCT)
        fair_pe, rate_note = _fair_pe_for_growth(eps_growth_pct, ten_year_yield_pct)
        target = ttm_eps_diluted * fair_pe
        current_pe = current_price / ttm_eps_diluted
        upside = (target - current_price) / current_price * 100.0
        signal = _signal_for_upside(upside)
        guardrail_note = _guardrail_note(
            eps_growth_pct, _MIN_GROWTH_PCT, _MAX_GROWTH_PCT,
            raw_pe, _MIN_PE, _MAX_PE, "P/E",
        )
        if guardrail_note is not None:
            confidence = "Medium"  # cap: the guardrail, not the data, drives the target
        if rate_note is not None:
            confidence = "Medium"  # cap: the rate environment, not the data, drives the target
        if eps_growth_pct < _MIN_GROWTH_PCT:
            # Batch 27: PEG is undefined for flat/declining earnings — the
            # fair P/E here is the distressed-earnings floor, not a PEG
            # implication. Say so honestly instead of claiming "a PEG of 1.5
            # on that growth implies…" (13 of 64 DB companies render this
            # card with negative EPS growth).
            if eps_growth_pct < 0:
                multiple_line = (
                    f"Earnings are declining ({eps_growth_pct:.1f}% YoY), so no "
                    f"growth premium applies — valued at the {fair_pe:.1f}× floor "
                    f"multiple for declining earnings "
                    f"(current P/E is {current_pe:.1f}×)."
                )
            else:
                multiple_line = (
                    f"Earnings are essentially flat ({eps_growth_pct:+.1f}% YoY), so no "
                    f"growth premium applies — valued at the {fair_pe:.1f}× floor "
                    f"multiple (current P/E is {current_pe:.1f}×)."
                )
        elif raw_pe < _MIN_PE and rate_note is None:
            # Batch 40: 2% <= growth < 5.34% — the PEG-implied multiple sits
            # below the model's 8x floor, so the floor (not the PEG
            # implication) drives the multiple. Same honesty class as the
            # batch-27 fix: never claim "a PEG of 1.5 on that growth
            # implies" a multiple the PEG math doesn't produce. The
            # guardrail note below still names the binding floor, and the
            # target math is untouched (fair_pe already reflects the floor).
            # (Batch 45 completes the honesty class on the cap side: when a
            # cap or the rate guardrail binds, the primary bullet now names
            # the raw PEG-implied multiple and the binding driver instead
            # of claiming the PEG math implies the guarded number.)
            multiple_line = (
                f"A PEG of {PEG_TARGET} on {eps_growth_pct:.1f}% growth implies a fair "
                f"P/E of {raw_pe:.1f}× — below the {_MIN_PE:.0f}× floor for "
                f"low-growth earnings, so valued at the floor instead "
                f"(current P/E is {current_pe:.1f}×)."
            )
        elif raw_pe > _MAX_PE:
            # Batch 45: cap-side mirror of the batch-40 floor honesty fix.
            # PEG math implies raw_pe (on growth already clamped to the
            # model maximum); the 40x cap — and possibly the rate
            # guardrail — produces fair_pe. Never claim "a PEG of 1.5 on
            # that growth implies" the guarded number: 41 of 102 DB
            # companies rendered that false claim (e.g. CVX "implies a
            # fair P/E of 37.0×" when the PEG math implies 51.8×). The
            # guardrail/rate notes below still name the binding drivers,
            # and the target math is untouched (fair_pe already reflects
            # the caps).
            drivers = f"above the {_MAX_PE:.0f}× cap for high-growth earnings"
            if rate_note is not None:
                drivers += (
                    f", and further capped at {fair_pe:.1f}× "
                    f"by the rate environment"
                )
            growth_txt = (
                f"{eps_growth_pct:.1f}% growth "
                f"(above the {_MAX_GROWTH_PCT:.0f}% model maximum)"
                if eps_growth_pct > _MAX_GROWTH_PCT
                else f"{eps_growth_pct:.1f}% growth"
            )
            multiple_line = (
                f"A PEG of {PEG_TARGET} on {growth_txt} implies a fair "
                f"P/E of {raw_pe:.1f}× — {drivers}, so valued at {fair_pe:.1f}× "
                f"instead (current P/E is {current_pe:.1f}×)."
            )
        elif rate_note is not None:
            # Batch 45: rate guardrail binds alone (the 24.7%–26.67% growth
            # band at a 4.5% 10-year; or, with a very high yield, below the
            # 8x floor). Same honesty class: the PEG math implies raw_pe,
            # not the rate-capped number.
            if raw_pe > fair_pe:
                multiple_line = (
                    f"A PEG of {PEG_TARGET} on {eps_growth_pct:.1f}% growth implies a fair "
                    f"P/E of {raw_pe:.1f}× — above what the rate environment allows, "
                    f"so valued at {fair_pe:.1f}× instead (current P/E is {current_pe:.1f}×)."
                )
            else:
                # raw_pe < fair_pe only when the 8x floor bound first and
                # the rate guardrail then capped the floor value (needs a
                # >20.8% 10-year — unreachable at the default 4.5%
                # benchmark). Name the chain honestly.
                multiple_line = (
                    f"A PEG of {PEG_TARGET} on {eps_growth_pct:.1f}% growth implies a fair "
                    f"P/E of {raw_pe:.1f}× — below the {_MIN_PE:.0f}× floor for "
                    f"low-growth earnings, and the floor multiple is further capped "
                    f"at {fair_pe:.1f}× by the rate environment, so valued at "
                    f"{fair_pe:.1f}× instead (current P/E is {current_pe:.1f}×)."
                )
        else:
            multiple_line = (
                f"A PEG of {PEG_TARGET} on that growth implies a fair P/E of {fair_pe:.1f}× "
                f"(current P/E is {current_pe:.1f}×)."
            )
        reasoning = [
            f"TTM diluted EPS ${ttm_eps_diluted:.2f}, growing {eps_growth_pct:.1f}% year over year.",
            multiple_line,
            f"Fair value ≈ ${target:.2f} vs ${current_price:.2f} today "
            f"({upside:+.1f}% implied upside).",
        ]
        if guardrail_note is not None:
            reasoning.append(guardrail_note)
        if rate_note is not None:
            reasoning.append(rate_note)
        return ValuationSignal(
            ticker=ticker,
            current_price=current_price,
            target_price=round(target, 2),
            upside_pct=round(upside, 1),
            signal=signal,
            confidence=confidence,
            method="peg",
            fair_multiple=round(fair_pe, 1),
            current_multiple=round(current_pe, 1),
            growth_pct=round(eps_growth_pct, 1),
            reasoning=reasoning,
            fcf_note=_fcf_cross_check_note(signal, ttm_free_cash_flow, market_cap),
        )

    # ── Fallback: sales-based target when earnings are unusable ────────────
    # Margin-anchored (batch 26): fair P/S = fair P/E x TTM net margin, the
    # accounting identity, using the same PEG-implied fair P/E curve as the
    # primary path. Without a positive margin there is no profitability to
    # anchor the sales multiple to — a target would be a guess, so the model
    # returns Watch/unavailable instead of one (previously a margin-blind
    # 0.5 x growth curve valued loss-making Ford at 1.9x sales: +641% upside).
    if (
        ttm_revenue is not None
        and ttm_revenue > 0
        and revenue_growth_pct is not None
        and shares_outstanding is not None
        and shares_outstanding > 0
    ):
        ttm_net_margin: float | None = None
        if ttm_net_income is not None:
            ttm_net_margin = ttm_net_income / ttm_revenue
        if ttm_net_margin is None or ttm_net_margin <= 0:
            return ValuationSignal(
                ticker=ticker,
                current_price=current_price,
                target_price=None,
                upside_pct=None,
                signal="Watch",
                confidence="Low",
                method="unavailable",
                fair_multiple=None,
                current_multiple=None,
                growth_pct=round(revenue_growth_pct, 1),
                reasoning=[
                    "No positive TTM earnings, and no positive TTM net margin "
                    "to anchor a sales multiple — a target price would be a "
                    "guess, not a model.",
                    "Watch the fundamentals until the business earns.",
                ],
            )
        fair_pe_curve, sales_rate_note = _fair_pe_for_growth(
            revenue_growth_pct, ten_year_yield_pct
        )
        raw_ps = fair_pe_curve * ttm_net_margin
        fair_ps = min(raw_ps, _MAX_PS)
        target = ttm_revenue * fair_ps / shares_outstanding
        current_ps = current_price * shares_outstanding / ttm_revenue
        upside = (target - current_price) / current_price * 100.0
        signal = _signal_for_upside(upside)
        guardrail_note = _guardrail_note(
            revenue_growth_pct, _MIN_GROWTH_PCT, _MAX_GROWTH_PCT,
            raw_ps, 0.0, _MAX_PS, "P/S",
        )
        if raw_ps > _MAX_PS:
            # Batch 45: same honesty class as the PEG-path cap fix — the
            # margin×P/E identity implies raw_ps, the 10x cap produces
            # fair_ps. Say so instead of claiming the identity implies the
            # capped number (V rendered "implies a fair P/S of 10.0×" when
            # 51.7% × 21.6× = 11.2×).
            ps_line = (
                f"TTM net margin {ttm_net_margin * 100:.1f}% × fair P/E "
                f"{fair_pe_curve:.1f}× implies a fair P/S of {raw_ps:.1f}× — "
                f"above the {_MAX_PS:.0f}× cap, so valued at {fair_ps:.1f}× "
                f"instead (current P/S is {current_ps:.1f}×)."
            )
        else:
            ps_line = (
                f"TTM net margin {ttm_net_margin * 100:.1f}% × fair P/E {fair_pe_curve:.1f}× "
                f"implies a fair P/S of {fair_ps:.1f}× (current P/S is {current_ps:.1f}×)."
            )
        sales_confidence = "Medium" if confidence == "High" else confidence
        if guardrail_note is not None:
            sales_confidence = "Medium"  # cap: the guardrail, not the data, drives the target
        if sales_rate_note is not None:
            sales_confidence = "Medium"  # cap: the rate environment, not the data, drives the target
        reasoning = [
            # Batch 33: the sales path is only reachable with a positive TTM
            # net margin, so TTM earnings ARE positive here — what is missing
            # is per-share earnings data to anchor a P/E multiple (e.g. ET,
            # an MLP that files no XBRL EPS facts). The old "No positive TTM
            # earnings" claim was false for every company on this path.
            "No per-share earnings to anchor a P/E multiple — valuing on sales "
            "instead (less reliable).",
            ps_line,
            f"Fair value ≈ ${target:.2f} vs ${current_price:.2f} today "
            f"({upside:+.1f}% implied upside).",
        ]
        if guardrail_note is not None:
            reasoning.append(guardrail_note)
        if sales_rate_note is not None:
            reasoning.append(sales_rate_note)
        return ValuationSignal(
            ticker=ticker,
            current_price=current_price,
            target_price=round(target, 2),
            upside_pct=round(upside, 1),
            signal=signal,
            confidence=sales_confidence,
            method="sales",
            fair_multiple=round(fair_ps, 1),
            current_multiple=round(current_ps, 1),
            growth_pct=round(revenue_growth_pct, 1),
            reasoning=reasoning,
            fcf_note=_fcf_cross_check_note(signal, ttm_free_cash_flow, market_cap),
        )

    # ── Nothing usable ────────────────────────────────────────────────────
    return ValuationSignal(
        ticker=ticker,
        current_price=current_price,
        target_price=None,
        upside_pct=None,
        signal="Watch",
        confidence="Low",
        method="unavailable",
        fair_multiple=None,
        current_multiple=None,
        growth_pct=None,
        reasoning=[
            "Not enough earnings history to build a target price.",
            "Watch the fundamentals until TTM earnings turn positive.",
        ],
    )
