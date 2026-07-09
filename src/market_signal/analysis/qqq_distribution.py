from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import NormalDist
from typing import Iterable

import httpx
import matplotlib.pyplot as plt
import numpy as np


STOOQ_DAILY_CSV_URL = "https://stooq.com/q/d/l/"


@dataclass(frozen=True)
class DailyBar:
    date: date
    close: Decimal


@dataclass(frozen=True)
class DistributionThresholds:
    symbol: str
    year: int
    confidence: Decimal
    sample_size: int
    mean_return: Decimal
    std_return: Decimal
    lower_threshold: Decimal
    upper_threshold: Decimal
    empirical_min_return: Decimal
    empirical_max_return: Decimal
    source: str

    def should_alert(self, daily_return: Decimal) -> bool:
        return daily_return <= self.lower_threshold or daily_return >= self.upper_threshold

    def side(self, daily_return: Decimal) -> str | None:
        if daily_return <= self.lower_threshold:
            return "down"
        if daily_return >= self.upper_threshold:
            return "up"
        return None

    def to_json_dict(self) -> dict[str, str | int]:
        return {
            "symbol": self.symbol,
            "year": self.year,
            "confidence": str(self.confidence),
            "sample_size": self.sample_size,
            "mean_return": str(self.mean_return),
            "std_return": str(self.std_return),
            "lower_threshold": str(self.lower_threshold),
            "upper_threshold": str(self.upper_threshold),
            "empirical_min_return": str(self.empirical_min_return),
            "empirical_max_return": str(self.empirical_max_return),
            "source": self.source,
        }


def fetch_stooq_daily_bars(*, symbol: str, year: int, timeout: float = 15.0) -> list[DailyBar]:
    response = httpx.get(
        STOOQ_DAILY_CSV_URL,
        params={
            "s": f"{symbol.lower()}.us",
            "d1": f"{year}0101",
            "d2": f"{year}1231",
            "i": "d",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return parse_stooq_daily_csv(response.text)


def parse_stooq_daily_csv(csv_text: str) -> list[DailyBar]:
    bars: list[DailyBar] = []
    reader = csv.DictReader(csv_text.splitlines())
    for row in reader:
        close_raw = row.get("Close")
        date_raw = row.get("Date")
        if not date_raw or not close_raw:
            continue
        bars.append(DailyBar(date=date.fromisoformat(date_raw), close=Decimal(close_raw)))
    if len(bars) < 2:
        raise ValueError("daily bar data must include at least two rows")
    return bars


def parse_kis_daily_bars(rows: Iterable[dict[str, object]]) -> list[DailyBar]:
    bars: list[DailyBar] = []
    for row in rows:
        date_raw = row.get("xymd")
        close_raw = row.get("clos")
        if not isinstance(date_raw, str) or close_raw in (None, ""):
            continue
        bars.append(
            DailyBar(
                date=date.fromisoformat(f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"),
                close=Decimal(str(close_raw)),
            )
        )
    if len(bars) < 2:
        raise ValueError("KIS daily bar data must include at least two rows")
    return sorted(bars, key=lambda bar: bar.date)


def close_to_close_returns(bars: Iterable[DailyBar]) -> list[Decimal]:
    ordered = sorted(bars, key=lambda bar: bar.date)
    returns: list[Decimal] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.close <= 0:
            continue
        returns.append((current.close - previous.close) / previous.close)
    if not returns:
        raise ValueError("daily returns could not be calculated")
    return returns


def fit_normal_thresholds(
    *,
    symbol: str,
    year: int,
    returns: list[Decimal],
    confidence: Decimal,
    source: str,
) -> DistributionThresholds:
    if len(returns) < 2:
        raise ValueError("at least two returns are required")
    if not Decimal("0") < confidence < Decimal("1"):
        raise ValueError("confidence must be between 0 and 1")

    values = np.array([float(value) for value in returns], dtype=float)
    mean = float(values.mean())
    std = float(values.std(ddof=1))
    if std <= 0 or math.isnan(std):
        raise ValueError("standard deviation must be positive")

    tail_probability = (1 - float(confidence)) / 2
    normal = NormalDist(mu=mean, sigma=std)
    lower = normal.inv_cdf(tail_probability)
    upper = normal.inv_cdf(1 - tail_probability)

    return DistributionThresholds(
        symbol=symbol,
        year=year,
        confidence=confidence,
        sample_size=len(returns),
        mean_return=Decimal(str(mean)),
        std_return=Decimal(str(std)),
        lower_threshold=Decimal(str(lower)),
        upper_threshold=Decimal(str(upper)),
        empirical_min_return=min(returns),
        empirical_max_return=max(returns),
        source=source,
    )


def write_thresholds(path: Path, thresholds: DistributionThresholds) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(thresholds.to_json_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def read_thresholds(path: Path) -> DistributionThresholds:
    data = json.loads(path.read_text(encoding="utf-8"))
    return DistributionThresholds(
        symbol=str(data["symbol"]),
        year=int(data["year"]),
        confidence=Decimal(str(data["confidence"])),
        sample_size=int(data["sample_size"]),
        mean_return=Decimal(str(data["mean_return"])),
        std_return=Decimal(str(data["std_return"])),
        lower_threshold=Decimal(str(data["lower_threshold"])),
        upper_threshold=Decimal(str(data["upper_threshold"])),
        empirical_min_return=Decimal(str(data["empirical_min_return"])),
        empirical_max_return=Decimal(str(data["empirical_max_return"])),
        source=str(data["source"]),
    )


def plot_distribution(
    *,
    returns: list[Decimal],
    thresholds: DistributionThresholds,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    values = np.array([float(value) for value in returns], dtype=float)
    mean = float(thresholds.mean_return)
    std = float(thresholds.std_return)
    lower = float(thresholds.lower_threshold)
    upper = float(thresholds.upper_threshold)

    x_min = min(float(values.min()), lower) * 1.15
    x_max = max(float(values.max()), upper) * 1.15
    xs = np.linspace(x_min, x_max, 500)
    normal_pdf = (1 / (std * math.sqrt(2 * math.pi))) * np.exp(
        -0.5 * ((xs - mean) / std) ** 2
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(values, bins=32, density=True, alpha=0.55, color="#4c78a8", label="2025 daily returns")
    ax.plot(xs, normal_pdf, color="#f58518", linewidth=2, label="fitted normal distribution")
    ax.axvline(lower, color="#d62728", linestyle="--", linewidth=1.5, label="lower alert threshold")
    ax.axvline(upper, color="#2ca02c", linestyle="--", linewidth=1.5, label="upper alert threshold")
    ax.axvline(mean, color="#222222", linestyle=":", linewidth=1.2, label="mean")
    ax.set_title(f"{thresholds.symbol} {thresholds.year} Daily Close-to-Close Return Distribution")
    ax.set_xlabel("Daily return")
    ax.set_ylabel("Density")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
