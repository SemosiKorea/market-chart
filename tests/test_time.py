from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from market_signal.normalization.time import to_display_timezone, to_utc


def test_to_utc_converts_aware_datetime() -> None:
    seoul_time = datetime(2026, 6, 25, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    assert to_utc(seoul_time) == datetime(2026, 6, 25, 0, 0, tzinfo=UTC)


def test_to_utc_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        to_utc(datetime(2026, 6, 25, 9, 0))


def test_to_display_timezone_converts_from_utc() -> None:
    utc_time = datetime(2026, 6, 25, 0, 0, tzinfo=UTC)

    assert to_display_timezone(utc_time) == datetime(
        2026,
        6,
        25,
        9,
        0,
        tzinfo=ZoneInfo("Asia/Seoul"),
    )
