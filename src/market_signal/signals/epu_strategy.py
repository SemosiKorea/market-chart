from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import NormalDist

import pandas as pd

from market_signal.analysis.qqq_distribution import DailyBar
from market_signal.providers.fred import EPUPoint


@dataclass(frozen=True)
class StrategySignal:
    signal_date: date
    current_position: Decimal
    target_position: Decimal
    close: Decimal
    regime: str
    reason: str
    epu_z: Decimal

    @property
    def action(self) -> str:
        if self.target_position > self.current_position:
            return "BUY"
        if self.target_position < self.current_position:
            return "SELL"
        return "HOLD"


def latest_epu_extreme_signal(
    *,
    bars: list[DailyBar],
    epu_points: list[EPUPoint],
    start_date: date,
    end_date: date,
) -> StrategySignal | None:
    signals = evaluate_epu_extreme_strategy(
        bars=bars,
        epu_points=epu_points,
        start_date=start_date,
        end_date=end_date,
    )
    return signals[-1] if signals else None


def evaluate_epu_extreme_strategy(
    *,
    bars: list[DailyBar],
    epu_points: list[EPUPoint],
    start_date: date,
    end_date: date,
) -> list[StrategySignal]:
    df = _build_frame(bars=bars, epu_points=epu_points)
    thresholds = _prior_year_thresholds(df)
    idx = df.loc[str(start_date) : str(end_date)].dropna(subset=["sma200", "epu_z"]).index

    state = "RISK_ON"
    sell_streak = 0
    buy_streak = 0
    position = Decimal("1")
    pending_position: Decimal | None = None
    signals: list[StrategySignal] = []

    for timestamp in idx:
        row = df.loc[timestamp]
        signal_date = timestamp.date()

        if pending_position is not None:
            position = pending_position
            pending_position = None

        year = signal_date.year
        if year not in thresholds:
            continue

        reg = _regime(row)
        stat_target, stat_reason = _statistical_overlay_target(
            row=row,
            thresholds=thresholds[year],
            position=position,
            regime=reg,
        )
        if stat_target is not None:
            target = _cap_target_for_extreme_epu(target=stat_target, row=row, regime=reg)
            if target != position:
                signals.append(_signal(signal_date, row, position, target, reg, stat_reason))
                pending_position = target
            if target == Decimal("0"):
                state = "RISK_OFF"
            elif target == Decimal("1"):
                state = "RISK_ON"
            continue

        if _should_epu_cap(row=row, regime=reg, position=position):
            target = Decimal("0.5")
            signals.append(_signal(signal_date, row, position, target, reg, "epu_extreme_stress_cap"))
            pending_position = target
            state = "RISK_OFF"
            continue

        if state == "RISK_ON":
            if _warning_score(row=row, thresholds=thresholds[year]) >= 2:
                state = "WARNING"
                sell_streak = 0
        elif state == "WARNING":
            bull = bool(row.close > row.sma200 and row.sma200_slope_up)
            should_sell = (
                _sell_score(row) >= 3 or _severe_sell_score(row) >= 2
                if bull
                else _sell_score(row) >= 2
            )
            if should_sell:
                sell_streak += 1
                if sell_streak >= 3:
                    target = _cap_target_for_extreme_epu(
                        target=Decimal("0"),
                        row=row,
                        regime=reg,
                    )
                    if target != position:
                        signals.append(_signal(signal_date, row, position, target, reg, "trend_exit"))
                        pending_position = target
                    state = "RISK_OFF"
                    sell_streak = 0
            elif _warning_score(row=row, thresholds=thresholds[year]) < 2:
                state = "RISK_ON"
                sell_streak = 0
            else:
                sell_streak = 0
        elif state == "RISK_OFF":
            if position == Decimal("0.5") and _conservative_buy_score(row) >= 3:
                target = Decimal("1")
                signals.append(_signal(signal_date, row, position, target, reg, "half_to_full_reentry"))
                pending_position = target
                state = "RISK_ON"
            elif _recovery_score(row=row, thresholds=thresholds[year]) >= 2:
                state = "RECOVERY"
                buy_streak = 0
        elif state == "RECOVERY":
            if _conservative_buy_score(row) >= 3:
                buy_streak += 1
                if buy_streak >= 3:
                    target = _cap_target_for_extreme_epu(
                        target=Decimal("1"),
                        row=row,
                        regime=reg,
                    )
                    if target != position:
                        signals.append(_signal(signal_date, row, position, target, reg, "reentry"))
                        pending_position = target
                    state = "RISK_ON" if target == Decimal("1") else "RISK_OFF"
                    buy_streak = 0
            elif _recovery_score(row=row, thresholds=thresholds[year]) < 2:
                state = "RISK_OFF"
                buy_streak = 0
            else:
                buy_streak = 0

    return signals


def format_strategy_signal_message(signal: StrategySignal, *, symbol: str = "QQQ") -> str:
    return "\n".join(
        [
            f"[Market Signal] {symbol} {signal.action}",
            f"date: {signal.signal_date.isoformat()}",
            f"target_position: {_pct(signal.target_position)}",
            f"current_position: {_pct(signal.current_position)}",
            f"close: {signal.close}",
            f"regime: {signal.regime}",
            f"reason: {signal.reason}",
            f"EPU z-score: {signal.epu_z:.2f}",
            "execution: next trading session / user confirmation required",
        ]
    )


def _build_frame(*, bars: list[DailyBar], epu_points: list[EPUPoint]) -> pd.DataFrame:
    price = pd.DataFrame(
        [(pd.Timestamp(bar.date), float(bar.close)) for bar in bars],
        columns=["date", "close"],
    ).drop_duplicates("date")
    epu = pd.DataFrame(
        [(pd.Timestamp(point.date), float(point.value)) for point in epu_points],
        columns=["date", "epu"],
    ).drop_duplicates("date")

    df = price.sort_values("date").set_index("date").join(epu.sort_values("date").set_index("date"))
    df["epu"] = df["epu"].ffill()
    df["epu_mean252"] = df["epu"].shift(1).rolling(252, min_periods=120).mean()
    df["epu_std252"] = df["epu"].shift(1).rolling(252, min_periods=120).std(ddof=1)
    df["epu_z"] = (df["epu"] - df["epu_mean252"]) / df["epu_std252"]
    df["ret"] = df["close"].pct_change()
    df["sma20"] = df["close"].rolling(20).mean()
    df["sma50"] = df["close"].rolling(50).mean()
    df["sma200"] = df["close"].rolling(200).mean()
    df["sma20_slope_up"] = df["sma20"] > df["sma20"].shift(5)
    df["sma50_slope_down"] = df["sma50"] < df["sma50"].shift(10)
    df["sma200_slope_up"] = df["sma200"] > df["sma200"].shift(20)
    df["sma200_slope_down"] = df["sma200"] < df["sma200"].shift(20)
    df["dd20"] = df["close"] / df["close"].rolling(20).max() - 1
    df["dd50"] = df["close"] / df["close"].rolling(50).max() - 1
    df["rebound10"] = df["close"] / df["close"].rolling(10).min() - 1
    return df


def _prior_year_thresholds(df: pd.DataFrame) -> dict[int, dict[str, float]]:
    normal90 = NormalDist().inv_cdf(0.95)
    normal99 = NormalDist().inv_cdf(0.995)
    thresholds: dict[int, dict[str, float]] = {}
    years = sorted({int(index.year) for index in df.index})
    for year in years:
        prior_returns = df.loc[f"{year - 1}-01-01" : f"{year - 1}-12-31", "ret"].dropna()
        if len(prior_returns) < 2:
            continue
        mean = float(prior_returns.mean())
        std = float(prior_returns.std(ddof=1))
        thresholds[year] = {
            "l90": mean - normal90 * std,
            "u90": mean + normal90 * std,
            "l99": mean - normal99 * std,
            "u99": mean + normal99 * std,
        }
    return thresholds


def _warning_score(*, row: pd.Series, thresholds: dict[str, float]) -> int:
    return _score(
        [
            row.close < row.sma50,
            row.sma20 < row.sma50,
            row.ret <= thresholds["l90"],
            row.dd20 <= -0.08,
        ]
    )


def _sell_score(row: pd.Series) -> int:
    return _score([row.close < row.sma200, row.sma20 < row.sma50, row.sma50_slope_down, row.dd20 <= -0.10])


def _severe_sell_score(row: pd.Series) -> int:
    return _score([row.close < row.sma200, row.sma200_slope_down, row.dd50 <= -0.12, row.sma50 < row.sma200])


def _recovery_score(*, row: pd.Series, thresholds: dict[str, float]) -> int:
    return _score(
        [
            row.close > row.sma20,
            row.sma20_slope_up,
            row.ret >= thresholds["u90"],
            row.rebound10 >= 0.05,
        ]
    )


def _conservative_buy_score(row: pd.Series) -> int:
    return _score([row.close > row.sma20, row.sma20_slope_up, row.rebound10 >= 0.05, row.close > row.sma50])


def _statistical_overlay_target(
    *,
    row: pd.Series,
    thresholds: dict[str, float],
    position: Decimal,
    regime: str,
) -> tuple[Decimal | None, str | None]:
    if row.ret <= thresholds["l99"]:
        if regime == "BULL" and position < Decimal("1"):
            return Decimal("1"), "down99_bull_reentry"
        if regime == "BEAR" and position > Decimal("0.5"):
            return Decimal("0.5"), "down99_bear_cap"
    if row.ret >= thresholds["u99"] and regime == "BEAR" and position > Decimal("0.5"):
        return Decimal("0.5"), "up99_bear_cap"
    return None, None


def _cap_target_for_extreme_epu(*, target: Decimal, row: pd.Series, regime: str) -> Decimal:
    if bool(row.epu_z >= 2.0) and regime in ("BEAR", "NEUTRAL"):
        return min(target, Decimal("0.5"))
    return target


def _should_epu_cap(*, row: pd.Series, regime: str, position: Decimal) -> bool:
    return (
        bool(row.epu_z >= 2.0)
        and regime in ("BEAR", "NEUTRAL")
        and position > Decimal("0.5")
        and (_sell_score(row) >= 1 or row.close < row.sma50)
    )


def _regime(row: pd.Series) -> str:
    if bool(row.close > row.sma200 and row.sma200_slope_up):
        return "BULL"
    if bool(row.close < row.sma200 and row.sma200_slope_down):
        return "BEAR"
    return "NEUTRAL"


def _signal(
    signal_date: date,
    row: pd.Series,
    current_position: Decimal,
    target_position: Decimal,
    regime: str,
    reason: str | None,
) -> StrategySignal:
    return StrategySignal(
        signal_date=signal_date,
        current_position=current_position,
        target_position=target_position,
        close=Decimal(str(round(float(row.close), 4))),
        regime=regime,
        reason=reason or "strategy_signal",
        epu_z=Decimal(str(round(float(row.epu_z), 4))),
    )


def _score(values: list[object]) -> int:
    return sum(bool(value) for value in values)


def _pct(position: Decimal) -> str:
    return f"{position * Decimal('100'):.0f}%"
