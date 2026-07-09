from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from market_signal.analysis.qqq_distribution import DistributionThresholds


@dataclass(frozen=True)
class DailyMoveAlertDecision:
    should_alert: bool
    side: str | None
    daily_return: Decimal
    threshold: Decimal | None


def evaluate_daily_move_alert(
    *,
    current_mid: Decimal,
    day_start_mid: Decimal,
    thresholds: DistributionThresholds,
) -> DailyMoveAlertDecision:
    if day_start_mid <= 0:
        raise ValueError("day_start_mid must be positive")

    daily_return = (current_mid - day_start_mid) / day_start_mid
    side = thresholds.side(daily_return)
    threshold = None
    if side == "up":
        threshold = thresholds.upper_threshold
    elif side == "down":
        threshold = thresholds.lower_threshold

    return DailyMoveAlertDecision(
        should_alert=side is not None,
        side=side,
        daily_return=daily_return,
        threshold=threshold,
    )
