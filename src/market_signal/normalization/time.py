from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def to_display_timezone(value: datetime, timezone: str = "Asia/Seoul") -> datetime:
    return to_utc(value).astimezone(ZoneInfo(timezone))
