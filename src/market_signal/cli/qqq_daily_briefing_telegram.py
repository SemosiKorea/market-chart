from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pandas as pd

from market_signal.analysis.daily_briefing import (
    DailyBriefing,
    build_daily_briefing,
    format_daily_briefing_message,
)
from market_signal.config import load_settings
from market_signal.notifications.telegram import TelegramNotifier
from market_signal.providers.fred import EPUPoint, fetch_daily_epu_points
from market_signal.providers.gdelt import fetch_market_headlines, fetch_yahoo_finance_headlines
from market_signal.providers.kis import DailyOHLCBar, KISAuthClient, KISMarketDataClient


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(
        description="Send a free-source QQQ daily close briefing to Telegram."
    )
    parser.add_argument("--symbol", default=settings.kis_qqq_symbol)
    parser.add_argument("--exchange", default=settings.kis_qqq_exchange_code)
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--headlines", type=int, default=5)
    parser.add_argument("--state-path", default=settings.qqq_daily_briefing_state_path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    settings.require_kis_credentials()
    if not args.dry_run:
        settings.require_telegram_credentials()

    end_year = args.end_year or (args.as_of.year if args.as_of else datetime.now(UTC).year)
    start_year = args.start_year or end_year - 1
    bars = _fetch_ohlc_bars(
        settings=settings,
        exchange=args.exchange,
        symbol=args.symbol,
        start_year=start_year,
        end_year=end_year,
    )
    if len(bars) < 2:
        raise ValueError("at least two OHLC bars are required for a daily briefing")

    as_of = args.as_of or max(bar.date for bar in bars)
    bar, previous_bar = _select_bars(bars, as_of=as_of)
    epu_points = fetch_daily_epu_points(timeout=settings.telegram_timeout_seconds * 3)
    epu_z = _epu_z_for_date(epu_points, target_date=bar.date)
    try:
        articles = fetch_market_headlines(
            target_date=bar.date,
            max_records=args.headlines,
            timeout=settings.telegram_timeout_seconds * 3,
        )
    except httpx.HTTPError:
        articles = []
    if not articles and _is_recent_date(bar.date):
        try:
            articles = fetch_yahoo_finance_headlines(
                symbol=args.symbol,
                max_records=args.headlines,
                timeout=settings.telegram_timeout_seconds * 3,
            )
        except httpx.HTTPError:
            articles = []
    briefing = build_daily_briefing(
        symbol=args.symbol,
        bar=bar,
        previous_bar=previous_bar,
        epu_z=epu_z,
        articles=articles,
    )

    state_path = Path(args.state_path)
    briefing_key = _briefing_key(briefing)
    if not args.force and _already_sent(state_path, briefing_key):
        print("QQQ daily briefing: already sent")
        print(f"  briefing: {briefing_key}")
        return 0

    message = format_daily_briefing_message(briefing)
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
        _write_state(state_path, briefing_key, briefing)
        print("QQQ daily briefing: sent")
        print(f"  briefing: {briefing_key}")
    return 0


def _fetch_ohlc_bars(
    *,
    settings,
    exchange: str,
    symbol: str,
    start_year: int,
    end_year: int,
) -> list[DailyOHLCBar]:
    bars: list[DailyOHLCBar] = []
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
                    market_data.get_overseas_daily_ohlc_year(
                        exchange=exchange,
                        symbol=symbol,
                        year=year,
                        adjusted=True,
                    )
                )
            except Exception:
                if year == datetime.now(UTC).year:
                    continue
                raise
    return sorted({bar.date: bar for bar in bars}.values(), key=lambda bar: bar.date)


def _select_bars(bars: list[DailyOHLCBar], *, as_of: date) -> tuple[DailyOHLCBar, DailyOHLCBar]:
    eligible = [bar for bar in bars if bar.date <= as_of]
    if len(eligible) < 2:
        raise ValueError(f"not enough bars found on or before {as_of.isoformat()}")
    return eligible[-1], eligible[-2]


def _is_recent_date(value: date) -> bool:
    return abs((datetime.now(UTC).date() - value).days) <= 3


def _epu_z_for_date(points: list[EPUPoint], *, target_date: date) -> Decimal | None:
    df = pd.DataFrame(
        [(pd.Timestamp(point.date), float(point.value)) for point in points],
        columns=["date", "epu"],
    ).drop_duplicates("date")
    df = df.sort_values("date").set_index("date")
    target = pd.Timestamp(target_date)
    df = df.loc[:target]
    if len(df) < 253:
        return None
    prior = df["epu"].shift(1)
    mean = prior.rolling(252, min_periods=120).mean().iloc[-1]
    std = prior.rolling(252, min_periods=120).std(ddof=1).iloc[-1]
    value = df["epu"].iloc[-1]
    if pd.isna(mean) or pd.isna(std) or std <= 0:
        return None
    return Decimal(str(round((value - mean) / std, 4)))


def _briefing_key(briefing: DailyBriefing) -> str:
    return f"{briefing.symbol}|{briefing.trade_date.isoformat()}|{briefing.close}"


def _already_sent(path: Path, briefing_key: str) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("last_briefing_key") == briefing_key


def _write_state(path: Path, briefing_key: str, briefing: DailyBriefing) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(briefing)
    data["articles"] = [asdict(article) for article in briefing.articles]
    path.write_text(
        json.dumps(
            {
                "last_briefing_key": briefing_key,
                "last_briefing": {key: str(value) for key, value in data.items()},
                "sent_at_utc": datetime.now(UTC).isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


if __name__ == "__main__":
    raise SystemExit(main())
