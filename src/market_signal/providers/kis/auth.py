from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field, SecretStr

from market_signal.config import Settings


class KISAuthError(RuntimeError):
    """Raised when KIS authentication fails."""


class KISAccessToken(BaseModel):
    access_token: SecretStr
    token_type: str = "Bearer"
    expires_in: int | None = None
    access_token_token_expired: str | None = None


class KISApprovalKey(BaseModel):
    approval_key: SecretStr = Field(min_length=1)


class KISAuthClient:
    def __init__(self, *, settings: Settings, http_client: httpx.Client) -> None:
        settings.require_kis_credentials()
        self._settings = settings
        self._http_client = http_client

    def issue_access_token(self) -> KISAccessToken:
        response = self._post_json(
            "/oauth2/tokenP",
            {
                "grant_type": "client_credentials",
                "appkey": self._secret_value(self._settings.kis_app_key),
                "appsecret": self._secret_value(self._settings.kis_app_secret),
            },
        )
        data = self._response_json(response)
        if "access_token" not in data:
            raise KISAuthError("KIS access token response did not include access_token")
        return KISAccessToken.model_validate(data)

    def issue_approval_key(self) -> KISApprovalKey:
        response = self._post_json(
            "/oauth2/Approval",
            {
                "grant_type": "client_credentials",
                "appkey": self._secret_value(self._settings.kis_app_key),
                "secretkey": self._secret_value(self._settings.kis_app_secret),
            },
        )
        data = self._response_json(response)
        if "approval_key" not in data:
            raise KISAuthError("KIS approval response did not include approval_key")
        return KISApprovalKey.model_validate(data)

    def _post_json(self, path: str, payload: dict[str, str]) -> httpx.Response:
        url = f"{self._settings.kis_rest_base_url_text}{path}"
        try:
            response = self._http_client.post(
                url,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json; charset=UTF-8",
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise KISAuthError(self._format_http_error(exc.response)) from exc
        return response

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise KISAuthError("KIS auth response was not valid JSON") from exc
        if not isinstance(data, dict):
            raise KISAuthError("KIS auth response JSON was not an object")
        return data

    @staticmethod
    def _format_http_error(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return f"KIS auth HTTP {response.status_code}: non-JSON response"

        code = data.get("error_code") or data.get("rt_cd") or data.get("code") or "unknown"
        message = data.get("error_description") or data.get("msg1") or data.get("message")
        if message:
            return f"KIS auth HTTP {response.status_code}: {code} {message}"
        return f"KIS auth HTTP {response.status_code}: {code}"

    @staticmethod
    def _secret_value(value: SecretStr | None) -> str:
        if value is None:
            raise KISAuthError("required KIS secret was missing")
        return value.get_secret_value()
