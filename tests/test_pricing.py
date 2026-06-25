from datetime import UTC, datetime, timedelta
from decimal import Decimal

from market_signal.domain import QualityStatus
from market_signal.normalization.pricing import (
    calculate_return,
    classify_qqq_quality,
    mid_price,
    spread_ratio,
)


def test_calculate_return() -> None:
    assert calculate_return(Decimal("105"), Decimal("100")) == Decimal("0.05")
    assert calculate_return(Decimal("105"), Decimal("0")) is None
    assert calculate_return(None, Decimal("100")) is None


def test_mid_price_and_spread_ratio() -> None:
    assert mid_price(Decimal("100"), Decimal("101")) == Decimal("100.5")
    assert spread_ratio(Decimal("100"), Decimal("101")) == Decimal("1") / Decimal("100.5")
    assert mid_price(Decimal("101"), Decimal("100")) is None
    assert spread_ratio(Decimal("101"), Decimal("100")) is None


def test_classify_qqq_quality_uses_valid_midpoint() -> None:
    received_at = datetime(2026, 6, 25, 0, 0, 10, tzinfo=UTC)

    quality = classify_qqq_quality(
        bid=Decimal("100"),
        ask=Decimal("100.10"),
        last_price=Decimal("100.04"),
        quote_timestamp=received_at - timedelta(seconds=5),
        received_at=received_at,
        max_quote_age=timedelta(seconds=30),
        max_spread=Decimal("0.003"),
    )

    assert quality.status == QualityStatus.VALID_MID
    assert quality.selected_price == Decimal("100.05")


def test_classify_qqq_quality_falls_back_to_last_price_when_quote_invalid() -> None:
    received_at = datetime(2026, 6, 25, 0, 0, 10, tzinfo=UTC)

    quality = classify_qqq_quality(
        bid=Decimal("101"),
        ask=Decimal("100"),
        last_price=Decimal("100.25"),
        quote_timestamp=received_at,
        received_at=received_at,
        max_quote_age=timedelta(seconds=30),
        max_spread=Decimal("0.003"),
    )

    assert quality.status == QualityStatus.VALID_LAST
    assert quality.selected_price == Decimal("100.25")


def test_classify_qqq_quality_rejects_stale_quote_without_last_price() -> None:
    received_at = datetime(2026, 6, 25, 0, 1, 0, tzinfo=UTC)

    quality = classify_qqq_quality(
        bid=Decimal("100"),
        ask=Decimal("100.10"),
        last_price=None,
        quote_timestamp=received_at - timedelta(seconds=31),
        received_at=received_at,
        max_quote_age=timedelta(seconds=30),
        max_spread=Decimal("0.003"),
    )

    assert quality.status == QualityStatus.STALE_QUOTE
    assert quality.selected_price is None


def test_classify_qqq_quality_rejects_wide_spread_without_last_price() -> None:
    received_at = datetime(2026, 6, 25, 0, 0, 10, tzinfo=UTC)

    quality = classify_qqq_quality(
        bid=Decimal("100"),
        ask=Decimal("101"),
        last_price=None,
        quote_timestamp=received_at,
        received_at=received_at,
        max_quote_age=timedelta(seconds=30),
        max_spread=Decimal("0.003"),
    )

    assert quality.status == QualityStatus.WIDE_SPREAD
    assert quality.selected_price is None
