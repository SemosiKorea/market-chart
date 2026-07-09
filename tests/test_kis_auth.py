from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from market_signal.config import Settings
from market_signal.providers.kis import KISAuthClient, KISAuthError


def test_settings_require_kis_credentials_accepts_complete_values() -> None:
    settings = _settings()

    settings.require_kis_credentials()


def test_settings_require_kis_credentials_reports_missing_product_code() -> None:
    settings = _settings(kis_account_product_code=None)

    with pytest.raises(ValueError, match="MARKET_SIGNAL_KIS_ACCOUNT_PRODUCT_CODE"):
        settings.require_kis_credentials()


def test_issue_access_token_posts_expected_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "access_token": "access-token-value",
                "token_type": "Bearer",
                "expires_in": 86400,
                "access_token_token_expired": "2026-07-11 01:00:00",
            },
        )

    client = KISAuthClient(
        settings=_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    token = client.issue_access_token()

    assert token.access_token.get_secret_value() == "access-token-value"
    assert requests[0].url == "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    assert requests[0].read() == (
        b'{"grant_type":"client_credentials","appkey":"app-key","appsecret":"app-secret"}'
    )


def test_issue_approval_key_posts_secretkey_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"approval_key": "approval-key-value"})

    client = KISAuthClient(
        settings=_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    approval = client.issue_approval_key()

    assert approval.approval_key.get_secret_value() == "approval-key-value"
    assert requests[0].url == "https://openapi.koreainvestment.com:9443/oauth2/Approval"
    assert requests[0].read() == (
        b'{"grant_type":"client_credentials","appkey":"app-key","secretkey":"app-secret"}'
    )


def test_auth_client_raises_redacted_error_on_http_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error_code": "EGW00123", "error_description": "denied"})

    client = KISAuthClient(
        settings=_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(KISAuthError) as exc_info:
        client.issue_access_token()

    message = str(exc_info.value)
    assert "EGW00123 denied" in message
    assert "app-secret" not in message
    assert "app-key" not in message


def test_issue_access_token_cached_reuses_fresh_cache(tmp_path) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "access_token": "new-token",
                "token_type": "Bearer",
                "expires_in": 86400,
            },
        )

    settings = _settings(kis_token_cache_path=str(tmp_path / "kis_access_token.json"))
    client = KISAuthClient(
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    first = client.issue_access_token_cached()
    second = client.issue_access_token_cached()

    assert first.access_token.get_secret_value() == "new-token"
    assert second.access_token.get_secret_value() == "new-token"
    assert calls == 1


def _settings(**overrides: object) -> Settings:
    values = {
        "kis_env": "live",
        "kis_app_key": SecretStr("app-key"),
        "kis_app_secret": SecretStr("app-secret"),
        "kis_account": SecretStr("12345678"),
        "kis_account_product_code": SecretStr("01"),
        "kis_rest_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_websocket_url": "ws://ops.koreainvestment.com:21000",
    }
    values.update(overrides)
    return Settings(**values)
