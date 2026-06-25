from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from market_signal.domain import (
    DataDelayType,
    InstrumentType,
    MarketQuote,
    MarketSession,
    QualityStatus,
    Source,
)


def test_market_quote_normalizes_timestamps_to_utc() -> None:
    quote = MarketQuote(
        source=Source.KIS,
        instrument_type=InstrumentType.ETF,
        symbol="QQQ",
        session=MarketSession.DAYTIME,
        market_timestamp=datetime(2026, 6, 25, 9, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        received_at=datetime(2026, 6, 25, 9, 0, 1, tzinfo=ZoneInfo("Asia/Seoul")),
        last_price=Decimal("525.12"),
        reference_price=Decimal("524.00"),
        data_delay_type=DataDelayType.REALTIME,
        quality_status=QualityStatus.VALID_LAST,
    )

    assert quote.market_timestamp == datetime(2026, 6, 25, 0, 0, tzinfo=UTC)
    assert quote.received_at == datetime(2026, 6, 25, 0, 0, 1, tzinfo=UTC)


def test_market_quote_rejects_naive_timestamps() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(
            source=Source.IBKR,
            instrument_type=InstrumentType.FUTURE,
            symbol="MNQ",
            market_timestamp=datetime(2026, 6, 25, 0, 0),
            received_at=datetime(2026, 6, 25, 0, 0, tzinfo=UTC),
        )
