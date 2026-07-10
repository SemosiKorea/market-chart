from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx


FRED_EPU_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_EPU_SERIES_ID = "USEPUINDXD"


@dataclass(frozen=True)
class EPUPoint:
    date: date
    value: Decimal


def fetch_daily_epu_points(
    *,
    series_id: str = FRED_EPU_SERIES_ID,
    timeout: float = 30.0,
) -> list[EPUPoint]:
    response = httpx.get(FRED_EPU_CSV_URL, params={"id": series_id}, timeout=timeout)
    response.raise_for_status()
    return parse_fred_epu_csv(response.text, value_column=series_id)


def parse_fred_epu_csv(csv_text: str, *, value_column: str = FRED_EPU_SERIES_ID) -> list[EPUPoint]:
    points: list[EPUPoint] = []
    reader = csv.DictReader(csv_text.splitlines())
    for row in reader:
        date_raw = row.get("observation_date")
        value_raw = row.get(value_column)
        if not date_raw or value_raw in (None, "", "."):
            continue
        try:
            points.append(EPUPoint(date=date.fromisoformat(date_raw), value=Decimal(value_raw)))
        except (ValueError, InvalidOperation):
            continue
    if not points:
        raise ValueError("FRED EPU CSV did not include any usable observations")
    return points
