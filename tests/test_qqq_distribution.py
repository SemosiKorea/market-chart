from __future__ import annotations

from datetime import date
from decimal import Decimal

from market_signal.analysis.qqq_distribution import (
    DailyBar,
    close_to_close_returns,
    fit_normal_thresholds,
    parse_kis_daily_bars,
    parse_stooq_daily_csv,
)
from market_signal.signals.daily_move import evaluate_daily_move_alert


def test_parse_stooq_daily_csv_and_returns() -> None:
    csv_text = "\n".join(
        [
            "Date,Open,High,Low,Close,Volume",
            "2025-01-02,100,101,99,100,10",
            "2025-01-03,100,103,99,102,11",
            "2025-01-06,102,103,98,99,12",
        ]
    )

    bars = parse_stooq_daily_csv(csv_text)
    returns = close_to_close_returns(bars)

    assert bars[0] == DailyBar(date=date(2025, 1, 2), close=Decimal("100"))
    assert returns == [Decimal("0.02"), Decimal("-0.02941176470588235294117647059")]


def test_parse_kis_daily_bars() -> None:
    bars = parse_kis_daily_bars(
        [
            {"xymd": "20250103", "clos": "102.5"},
            {"xymd": "20250102", "clos": "100.0"},
        ]
    )

    assert bars == [
        DailyBar(date=date(2025, 1, 2), close=Decimal("100.0")),
        DailyBar(date=date(2025, 1, 3), close=Decimal("102.5")),
    ]


def test_fit_normal_thresholds_and_alert_decision() -> None:
    returns = [
        Decimal("-0.03"),
        Decimal("-0.02"),
        Decimal("-0.01"),
        Decimal("0"),
        Decimal("0.01"),
        Decimal("0.02"),
        Decimal("0.03"),
    ]
    thresholds = fit_normal_thresholds(
        symbol="QQQ",
        year=2025,
        returns=returns,
        confidence=Decimal("0.90"),
        source="test",
    )

    assert thresholds.lower_threshold < 0
    assert thresholds.upper_threshold > 0
    assert thresholds.should_alert(thresholds.upper_threshold)
    assert thresholds.should_alert(thresholds.lower_threshold)
    assert not thresholds.should_alert(Decimal("0"))

    up = evaluate_daily_move_alert(
        current_mid=Decimal("104"),
        day_start_mid=Decimal("100"),
        thresholds=thresholds,
    )
    down = evaluate_daily_move_alert(
        current_mid=Decimal("96"),
        day_start_mid=Decimal("100"),
        thresholds=thresholds,
    )

    assert up.should_alert
    assert up.side == "up"
    assert down.should_alert
    assert down.side == "down"
