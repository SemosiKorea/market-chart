from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from market_signal.analysis.qqq_distribution import DailyBar
from market_signal.config import load_settings
from market_signal.notifications.telegram import TelegramNotifier
from market_signal.providers.fred import fetch_daily_epu_points
from market_signal.providers.kis import KISAuthClient, KISMarketDataClient
from market_signal.signals.epu_strategy import (
    StrategySignal,
    format_strategy_signal_message,
    latest_epu_extreme_signal,
)


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(
        description="Send Telegram alerts for the QQQ EPU extreme stress strategy."
    )
    parser.add_argument("--symbol", default=settings.kis_qqq_symbol)
    parser.add_argument("--exchange", default=settings.kis_qqq_exchange_code)
    parser.add_argument("--start-year", type=int, default=2017)
    parser.add_argument("--end-year", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--state-path", default=settings.qqq_strategy_state_path)
    parser.add_argument("--dry-run", action="store_true", help="Print the message without sending it.")
    parser.add_argument("--force", action="store_true", help="Send even if the same signal was sent before.")
    args = parser.parse_args()

    settings.require_kis_credentials()
    if not args.dry_run:
        settings.require_telegram_credentials()

    bars = _fetch_bars(
        settings=settings,
        exchange=args.exchange,
        symbol=args.symbol,
        start_year=args.start_year,
        end_year=args.end_year,
    )
    if args.as_of is None:
        end_date = max(bar.date for bar in bars)
    else:
        end_date = args.as_of

    epu_points = fetch_daily_epu_points(timeout=settings.telegram_timeout_seconds * 3)
    signal = latest_epu_extreme_signal(
        bars=bars,
        epu_points=epu_points,
        start_date=date(args.start_year + 1, 1, 1),
        end_date=end_date,
    )
    if signal is None or signal.signal_date != end_date:
        print("QQQ EPU strategy alert: no new signal")
        print(f"  as_of: {end_date.isoformat()}")
        return 0

    state_path = Path(args.state_path)
    signal_key = _signal_key(signal)
    if not args.force and _already_sent(state_path, signal_key):
        print("QQQ EPU strategy alert: already sent")
        print(f"  signal: {signal_key}")
        return 0

    message = format_strategy_signal_message(signal, symbol=args.symbol)
    if args.dry_run:
        print(message)
    else:
        assert settings.telegram_bot_token is not None
        assert settings.telegram_chat_id is not None
        notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            timeout_seconds=settings.telegram_timeout_seconds,
        )
        notifier.send_message(message)
        _write_state(state_path, signal_key, signal)
        print("QQQ EPU strategy alert: sent")
        print(f"  signal: {signal_key}")

    return 0


def _fetch_bars(
    *,
    settings,
    exchange: str,
    symbol: str,
    start_year: int,
    end_year: int,
) -> list[DailyBar]:
    bars: list[DailyBar] = []
    with httpx.Client(timeout=settings.kis_timeout_seconds) as http_client:
        token = KISAuthClient(settings=settings, http_client=http_client).issue_access_token_cached()
        market_data = KISMarketDataClient(
            settings=settings,
            http_client=http_client,
            access_token=token.access_token,
        )
        for year in range(start_year, end_year + 1):
            try:
                bars.extend(
                    market_data.get_overseas_daily_bars_year(
                        exchange=exchange,
                        symbol=symbol,
                        year=year,
                        adjusted=True,
                    )
                )
            except Exception:
                if year == end_year and datetime.now(UTC).year == year:
                    continue
                raise
    return sorted({bar.date: bar for bar in bars}.values(), key=lambda bar: bar.date)


def _signal_key(signal: StrategySignal) -> str:
    return "|".join(
        [
            signal.signal_date.isoformat(),
            signal.action,
            str(signal.target_position),
            signal.reason,
        ]
    )


def _already_sent(path: Path, signal_key: str) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("last_signal_key") == signal_key


def _write_state(path: Path, signal_key: str, signal: StrategySignal) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "last_signal_key": signal_key,
                "last_signal": _json_safe_signal(signal),
                "sent_at_utc": datetime.now(UTC).isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _json_safe_signal(signal: StrategySignal) -> dict[str, str]:
    data = asdict(signal)
    return {key: str(value) for key, value in data.items()}


if __name__ == "__main__":
    raise SystemExit(main())
