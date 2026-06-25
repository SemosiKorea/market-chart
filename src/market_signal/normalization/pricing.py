from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from market_signal.domain.quote import QualityStatus
from market_signal.normalization.time import to_utc


@dataclass(frozen=True)
class PriceQuality:
    status: QualityStatus
    selected_price: Decimal | None
    spread: Decimal | None = None


def calculate_return(current: Decimal | None, reference: Decimal | None) -> Decimal | None:
    if current is None or reference is None or reference <= 0:
        return None
    return (current - reference) / reference


def mid_price(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (bid + ask) / Decimal("2")


def spread_ratio(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    midpoint = mid_price(bid, ask)
    if midpoint is None:
        return None
    return (ask - bid) / midpoint


def classify_qqq_quality(
    *,
    bid: Decimal | None,
    ask: Decimal | None,
    last_price: Decimal | None,
    quote_timestamp: datetime,
    received_at: datetime,
    max_quote_age: timedelta,
    max_spread: Decimal,
) -> PriceQuality:
    received_at_utc = to_utc(received_at)
    quote_timestamp_utc = to_utc(quote_timestamp)
    quote_age = received_at_utc - quote_timestamp_utc
    last_fallback = last_price if last_price is not None and last_price > 0 else None

    midpoint = mid_price(bid, ask)
    if midpoint is None:
        return _fallback_or_status(QualityStatus.INVALID_QUOTE, last_fallback)

    if quote_age < timedelta(0) or quote_age > max_quote_age:
        return _fallback_or_status(QualityStatus.STALE_QUOTE, last_fallback)

    spread = spread_ratio(bid, ask)
    if spread is None:
        return _fallback_or_status(QualityStatus.INVALID_QUOTE, last_fallback)
    if spread > max_spread:
        return _fallback_or_status(QualityStatus.WIDE_SPREAD, last_fallback, spread)

    return PriceQuality(
        status=QualityStatus.VALID_MID,
        selected_price=midpoint,
        spread=spread,
    )


def _fallback_or_status(
    status: QualityStatus,
    last_fallback: Decimal | None,
    spread: Decimal | None = None,
) -> PriceQuality:
    if last_fallback is not None:
        return PriceQuality(
            status=QualityStatus.VALID_LAST,
            selected_price=last_fallback,
            spread=spread,
        )
    return PriceQuality(status=status, selected_price=None, spread=spread)
