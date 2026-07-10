from __future__ import annotations

from datetime import date
from decimal import Decimal

from market_signal.signals.epu_strategy import StrategySignal, format_strategy_signal_message


def test_format_strategy_signal_message() -> None:
    signal = StrategySignal(
        signal_date=date(2025, 3, 6),
        current_position=Decimal("1"),
        target_position=Decimal("0.5"),
        close=Decimal("488.1561"),
        regime="NEUTRAL",
        reason="epu_extreme_stress_cap",
        epu_z=Decimal("5.62"),
    )

    message = format_strategy_signal_message(signal)

    assert "[Market Signal] QQQ SELL" in message
    assert "target_position: 50%" in message
    assert "reason: epu_extreme_stress_cap" in message
