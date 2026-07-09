from __future__ import annotations

import argparse

import httpx

from market_signal.config import load_settings
from market_signal.normalization.pricing import classify_qqq_quality
from market_signal.providers.kis import KISAuthClient, KISAuthError, KISMarketDataClient
from market_signal.providers.kis.market_data import KISMarketDataError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch QQQ overseas stock price/quote data from KIS without calling order APIs."
    )
    parser.add_argument("--symbol", default=None, help="Overseas stock symbol. Defaults to settings.")
    parser.add_argument("--exchange", default=None, help="KIS exchange code. Defaults to settings.")
    parser.add_argument(
        "--refresh-token",
        action="store_true",
        help="Ignore the local access token cache and request a fresh REST token.",
    )
    args = parser.parse_args()

    settings = load_settings()
    symbol = args.symbol or settings.kis_qqq_symbol
    exchange = args.exchange or settings.kis_qqq_exchange_code

    try:
        settings.require_kis_credentials()
        with httpx.Client(timeout=settings.kis_timeout_seconds) as http_client:
            auth_client = KISAuthClient(settings=settings, http_client=http_client)
            token = auth_client.issue_access_token_cached(refresh=args.refresh_token)

            market_client = KISMarketDataClient(
                settings=settings,
                http_client=http_client,
                access_token=token.access_token,
            )
            snapshot = market_client.get_overseas_quote_snapshot(exchange=exchange, symbol=symbol)
            quote = snapshot.to_market_quote(
                max_quote_age_seconds=settings.max_quote_age_seconds,
                max_spread_ratio=settings.max_spread_ratio,
            )
            quality = classify_qqq_quality(
                bid=quote.bid_price,
                ask=quote.ask_price,
                last_price=quote.last_price,
                quote_timestamp=quote.market_timestamp,
                received_at=quote.received_at,
                max_quote_age=snapshot.max_quote_age,
                max_spread=settings.max_spread_ratio,
            )

        print("KIS QQQ REST quote: OK")
        print(f"  symbol: {exchange}:{symbol}")
        print(f"  last_price: {quote.last_price}")
        print(f"  bid_price: {quote.bid_price}")
        print(f"  ask_price: {quote.ask_price}")
        print(f"  quality_status: {quote.quality_status.value}")
        print(f"  selected_price: {quality.selected_price}")
        print("No order API was called.")
        return 0
    except (ValueError, KISAuthError, KISMarketDataError, httpx.HTTPError) as exc:
        print(f"KIS QQQ REST smoke test failed: {exc}")
        print("No order API was called.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
