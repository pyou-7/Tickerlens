from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from tickerlens.data import yahoo


class _FakeTicker:
    def __init__(
        self,
        frame: pd.DataFrame,
        metadata: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._frame = frame
        self.history_metadata = metadata or {}
        self.error = error
        self.history_kwargs: dict[str, object] = {}

    def history(self, **kwargs: object) -> pd.DataFrame:
        self.history_kwargs = kwargs
        if self.error:
            raise self.error
        return self._frame


def _history_frame(values: list[float], frequency: str = "D") -> pd.DataFrame:
    index = pd.date_range("2025-01-02", periods=len(values), freq=frequency, tz="America/New_York")
    return pd.DataFrame({"Close": values}, index=index)


def test_get_price_history_normalizes_adjusted_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeTicker(_history_frame([100.0, 105.0]), {"currency": "USD"})
    monkeypatch.setattr(yahoo.yf, "Ticker", lambda ticker: fake)

    result = yahoo.get_price_history("aapl", "1y")

    assert result.ticker == "AAPL"
    assert result.range_label == "1Y"
    assert result.currency == "USD"
    assert result.prices == [100.0, 105.0]
    assert result.change_amount == pytest.approx(5.0)
    assert result.change_pct == pytest.approx(5.0)
    assert result.is_intraday is False
    assert fake.history_kwargs == {
        "period": "1y",
        "interval": "1d",
        "auto_adjust": True,
        "actions": False,
        "raise_errors": True,
    }


def test_today_change_uses_previous_close(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeTicker(
        _history_frame([101.0, 102.0], frequency="5min"),
        {"currency": "USD", "chartPreviousClose": 100.0},
    )
    monkeypatch.setattr(yahoo.yf, "Ticker", lambda ticker: fake)

    result = yahoo.get_price_history("AAPL", "1d")

    assert result.change_amount == pytest.approx(2.0)
    assert result.change_pct == pytest.approx(2.0)
    assert result.is_intraday is True
    assert fake.history_kwargs["interval"] == "5m"


def test_three_year_range_uses_explicit_start(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeTicker(_history_frame([100.0]))
    monkeypatch.setattr(yahoo.yf, "Ticker", lambda ticker: fake)

    yahoo.get_price_history("AAPL", "3y")

    expected_year = dt.date.today().year - 3
    assert "period" not in fake.history_kwargs
    assert str(fake.history_kwargs["start"]).startswith(str(expected_year))
    assert fake.history_kwargs["interval"] == "1d"


def test_price_history_failure_returns_empty_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeTicker(pd.DataFrame(), error=RuntimeError("upstream unavailable"))
    monkeypatch.setattr(yahoo.yf, "Ticker", lambda ticker: fake)

    result = yahoo.get_price_history("AAPL", "5d")

    assert result.range_label == "5D"
    assert result.timestamps == []
    assert result.prices == []
    assert result.is_intraday is True
