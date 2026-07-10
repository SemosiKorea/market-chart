from __future__ import annotations

from datetime import date
from decimal import Decimal

from market_signal.providers.fred import EPUPoint, parse_fred_epu_csv


def test_parse_fred_epu_csv_skips_missing_values() -> None:
    csv_text = "\n".join(
        [
            "observation_date,USEPUINDXD",
            "2025-01-01,100.5",
            "2025-01-02,.",
            "2025-01-03,110",
        ]
    )

    points = parse_fred_epu_csv(csv_text)

    assert points == [
        EPUPoint(date=date(2025, 1, 1), value=Decimal("100.5")),
        EPUPoint(date=date(2025, 1, 3), value=Decimal("110")),
    ]
