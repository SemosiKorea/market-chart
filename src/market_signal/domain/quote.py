from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from market_signal.normalization.time import to_utc


class Source(StrEnum):
    IBKR = "ibkr"
    KIS = "kis"


class InstrumentType(StrEnum):
    FUTURE = "future"
    ETF = "etf"


class MarketSession(StrEnum):
    REGULAR = "regular"
    DAYTIME = "daytime"
    OVERNIGHT = "overnight"
    UNKNOWN = "unknown"


class DataDelayType(StrEnum):
    REALTIME = "realtime"
    DELAYED = "delayed"
    UNKNOWN = "unknown"


class QualityStatus(StrEnum):
    VALID_MID = "valid_mid"
    VALID_LAST = "valid_last"
    STALE_QUOTE = "stale_quote"
    INVALID_QUOTE = "invalid_quote"
    WIDE_SPREAD = "wide_spread"
    MISSING_PRICE = "missing_price"


class MarketQuote(BaseModel):
    """Provider-independent market quote normalized for storage and comparison."""

    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=False)

    source: Source
    instrument_type: InstrumentType
    symbol: str = Field(min_length=1)
    session: MarketSession = MarketSession.UNKNOWN
    market_timestamp: datetime
    received_at: datetime
    last_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    bid_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    ask_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    bid_size: Decimal | None = Field(default=None, ge=Decimal("0"))
    ask_size: Decimal | None = Field(default=None, ge=Decimal("0"))
    reference_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    data_delay_type: DataDelayType = DataDelayType.UNKNOWN
    quality_status: QualityStatus = QualityStatus.MISSING_PRICE

    @field_validator("market_timestamp", "received_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return to_utc(value)
