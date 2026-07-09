from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

import httpx

from market_signal.analysis.qqq_distribution import (
    STOOQ_DAILY_CSV_URL,
    close_to_close_returns,
    fetch_stooq_daily_bars,
    fit_normal_thresholds,
    plot_distribution,
    write_thresholds,
)
from market_signal.config import load_settings
from market_signal.providers.kis import KISAuthClient, KISMarketDataClient


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(
        description="Build QQQ daily-return normal thresholds and distribution chart."
    )
    parser.add_argument("--symbol", default=settings.kis_qqq_symbol)
    parser.add_argument("--exchange", default=settings.kis_qqq_exchange_code)
    parser.add_argument("--year", type=int, default=settings.qqq_distribution_year)
    parser.add_argument("--source", choices=["kis", "stooq"], default="kis")
    parser.add_argument(
        "--confidence",
        type=Decimal,
        default=settings.qqq_distribution_confidence,
        help="Central normal-distribution mass. 0.90 means 5%% lower and 5%% upper tails.",
    )
    parser.add_argument("--threshold-output", default=settings.qqq_distribution_threshold_path)
    parser.add_argument("--chart-output", default=settings.qqq_distribution_chart_path)
    args = parser.parse_args()

    source = STOOQ_DAILY_CSV_URL
    if args.source == "kis":
        settings.require_kis_credentials()
        with httpx.Client(timeout=settings.kis_timeout_seconds) as http_client:
            token = KISAuthClient(settings=settings, http_client=http_client).issue_access_token_cached()
            market_data = KISMarketDataClient(
                settings=settings,
                http_client=http_client,
                access_token=token.access_token,
            )
            bars = market_data.get_overseas_daily_bars_year(
                exchange=args.exchange,
                symbol=args.symbol,
                year=args.year,
                adjusted=True,
            )
        source = "KIS overseas dailyprice"
    else:
        bars = fetch_stooq_daily_bars(symbol=args.symbol, year=args.year)

    returns = close_to_close_returns(bars)
    thresholds = fit_normal_thresholds(
        symbol=args.symbol,
        year=args.year,
        returns=returns,
        confidence=args.confidence,
        source=source,
    )
    write_thresholds(Path(args.threshold_output), thresholds)
    plot_distribution(
        returns=returns,
        thresholds=thresholds,
        output_path=Path(args.chart_output),
    )

    print("QQQ distribution thresholds: OK")
    print(f"  symbol: {thresholds.symbol}")
    print(f"  year: {thresholds.year}")
    print(f"  source: {thresholds.source}")
    print(f"  sample_size: {thresholds.sample_size}")
    print(f"  mean_return: {_pct(thresholds.mean_return)}")
    print(f"  std_return: {_pct(thresholds.std_return)}")
    print(f"  lower_threshold: {_pct(thresholds.lower_threshold)}")
    print(f"  upper_threshold: {_pct(thresholds.upper_threshold)}")
    print(f"  thresholds: {args.threshold_output}")
    print(f"  chart: {args.chart_output}")
    return 0


def _pct(value: Decimal) -> str:
    return f"{value * Decimal('100'):.4f}%"


if __name__ == "__main__":
    raise SystemExit(main())
