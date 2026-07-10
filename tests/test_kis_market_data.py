from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from market_signal.config import Settings
from market_signal.domain import QualityStatus
from market_signal.providers.kis import KISMarketDataClient, KISMarketDataError


def test_get_overseas_quote_snapshot_builds_market_quote() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/price"):
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "output": {
                        "last": "500.25",
                        "base": "498.00",
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output1": {"pbid1": "500.20", "pask1": "500.30"},
                "output2": {"vbid1": "10", "vask1": "12"},
            },
        )

    client = KISMarketDataClient(
        settings=_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        access_token=SecretStr("access-token"),
    )

    snapshot = client.get_overseas_quote_snapshot(exchange="NAS", symbol="QQQ")
    quote = snapshot.to_market_quote(
        max_quote_age_seconds=30,
        max_spread_ratio=Decimal("0.003"),
    )

    assert quote.symbol == "QQQ"
    assert quote.last_price == Decimal("500.25")
    assert quote.bid_price == Decimal("500.20")
    assert quote.ask_price == Decimal("500.30")
    assert quote.bid_size == Decimal("10")
    assert quote.ask_size == Decimal("12")
    assert quote.reference_price == Decimal("498.00")
    assert quote.quality_status == QualityStatus.VALID_MID
    assert requests[0].headers["authorization"] == "Bearer access-token"
    assert requests[0].headers["tr_id"] == "HHDFS00000300"
    assert requests[1].headers["tr_id"] == "HHDFS76200100"


def test_market_data_client_raises_for_kis_body_error_without_leaking_secrets() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rt_cd": "1", "msg_cd": "EGW123", "msg1": "denied"})

    client = KISMarketDataClient(
        settings=_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        access_token=SecretStr("access-token"),
    )

    with pytest.raises(KISMarketDataError) as exc_info:
        client.get_overseas_price(exchange="NAS", symbol="QQQ")

    message = str(exc_info.value)
    assert "EGW123 denied" in message
    assert "app-secret" not in message
    assert "access-token" not in message


def test_market_data_client_retries_rate_limit_response() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                500,
                json={"error_code": "EGW00201", "error_description": "초당 거래건수 초과"},
            )
        return httpx.Response(200, json={"rt_cd": "0", "output": {"last": "500.25"}})

    settings = _settings()
    settings.kis_rate_limit_retry_seconds = 0.001
    client = KISMarketDataClient(
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        access_token=SecretStr("access-token"),
    )

    output = client.get_overseas_price(exchange="NAS", symbol="QQQ")

    assert output == {"last": "500.25"}
    assert calls == 2


def test_get_overseas_daily_bars_year_pages_until_start_of_year() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "output2": [
                        {"xymd": "20251231", "clos": "110"},
                        {"xymd": "20250901", "clos": "105"},
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output2": [
                    {"xymd": "20250831", "clos": "104"},
                    {"xymd": "20250101", "clos": "100"},
                    {"xymd": "20241231", "clos": "99"},
                ],
            },
        )

    settings = _settings()
    settings.kis_rate_limit_retry_seconds = 0.001
    client = KISMarketDataClient(
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        access_token=SecretStr("access-token"),
    )

    bars = client.get_overseas_daily_bars_year(exchange="NAS", symbol="QQQ", year=2025)

    assert [bar.date.isoformat() for bar in bars] == [
        "2025-01-01",
        "2025-08-31",
        "2025-09-01",
        "2025-12-31",
    ]
    assert calls[0].url.params["BYMD"] == "20251231"
    assert calls[1].url.params["BYMD"] == "20250831"


def test_get_overseas_daily_ohlc_year_parses_open_high_low_close() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output2": [
                    {
                        "xymd": "20250103",
                        "open": "100",
                        "high": "103",
                        "low": "99",
                        "clos": "102",
                    },
                    {
                        "xymd": "20250102",
                        "open": "98",
                        "high": "101",
                        "low": "97",
                        "clos": "100",
                    },
                ],
            },
        )

    client = KISMarketDataClient(
        settings=_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        access_token=SecretStr("access-token"),
    )

    bars = client.get_overseas_daily_ohlc_year(exchange="NAS", symbol="QQQ", year=2025)

    assert [bar.date.isoformat() for bar in bars] == ["2025-01-02", "2025-01-03"]
    assert bars[0].open == Decimal("98")
    assert bars[1].close == Decimal("102")


def _settings() -> Settings:
    return Settings(
        kis_env="live",
        kis_app_key=SecretStr("app-key"),
        kis_app_secret=SecretStr("app-secret"),
        kis_account=SecretStr("12345678"),
        kis_account_product_code=SecretStr("01"),
        kis_rest_base_url="https://openapi.koreainvestment.com:9443",
        kis_websocket_url="ws://ops.koreainvestment.com:21000",
    )
