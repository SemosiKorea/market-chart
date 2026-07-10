from __future__ import annotations

from datetime import date
from decimal import Decimal

from market_signal.analysis.daily_briefing import (
    build_daily_briefing,
    format_daily_briefing_message,
)
from market_signal.providers.gdelt import GDELTArticle
from market_signal.providers.kis import DailyOHLCBar


def test_build_and_format_daily_briefing() -> None:
    previous = DailyOHLCBar(
        date=date(2025, 5, 12),
        open=Decimal("100"),
        high=Decimal("103"),
        low=Decimal("99"),
        close=Decimal("101"),
    )
    current = DailyOHLCBar(
        date=date(2025, 5, 13),
        open=Decimal("101"),
        high=Decimal("106"),
        low=Decimal("100"),
        close=Decimal("105"),
    )

    briefing = build_daily_briefing(
        symbol="QQQ",
        bar=current,
        previous_bar=previous,
        epu_z=Decimal("2.1"),
        articles=[
            GDELTArticle(
                title="Nasdaq rises as CPI cools and Fed rate hopes improve",
                domain="example.com",
                url="https://example.com",
            )
        ],
    )
    message = format_daily_briefing_message(briefing)

    assert briefing.epu_status == "extreme"
    assert "open_to_close: +3.96%" in message
    assert "Fed/금리" in message
    assert "물가/CPI" in message
