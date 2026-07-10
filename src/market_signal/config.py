from decimal import Decimal
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MARKET_SIGNAL_",
        extra="ignore",
    )

    app_env: str = "local"
    timezone: str = "Asia/Seoul"
    database_url: str = "sqlite:///data/market_signal.sqlite3"

    max_quote_age_seconds: int = Field(default=30, gt=0)
    max_spread_ratio: Decimal = Field(default=Decimal("0.003"), gt=Decimal("0"))

    kis_app_key: SecretStr | None = None
    kis_app_secret: SecretStr | None = None
    kis_account: SecretStr | None = None
    kis_account_product_code: SecretStr | None = None
    kis_env: Literal["live", "paper"] = "live"
    kis_rest_base_url: AnyHttpUrl = AnyHttpUrl("https://openapi.koreainvestment.com:9443")
    kis_websocket_url: str = "ws://ops.koreainvestment.com:21000"
    kis_timeout_seconds: float = Field(default=10.0, gt=0)
    kis_token_cache_path: str = ".cache/kis_access_token.json"
    kis_rate_limit_retry_seconds: float = Field(default=1.0, gt=0)
    kis_rate_limit_max_attempts: int = Field(default=3, gt=0)
    kis_qqq_exchange_code: str = "NAS"
    kis_qqq_symbol: str = "QQQ"
    qqq_distribution_year: int = 2025
    qqq_distribution_confidence: Decimal = Field(default=Decimal("0.90"), gt=0, lt=1)
    qqq_distribution_threshold_path: str = "data/qqq_2025_distribution_thresholds.json"
    qqq_distribution_chart_path: str = "reports/qqq_2025_daily_return_distribution.png"
    qqq_strategy_state_path: str = ".cache/qqq_epu_strategy_state.json"
    qqq_daily_briefing_state_path: str = ".cache/qqq_daily_briefing_state.json"

    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = Field(default=7497, gt=0)
    ibkr_client_id: int = Field(default=1, ge=0)

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: SecretStr | None = None
    telegram_timeout_seconds: float = Field(default=10.0, gt=0)

    def require_kis_credentials(self) -> None:
        missing = [
            name
            for name, value in (
                ("MARKET_SIGNAL_KIS_APP_KEY", self.kis_app_key),
                ("MARKET_SIGNAL_KIS_APP_SECRET", self.kis_app_secret),
                ("MARKET_SIGNAL_KIS_ACCOUNT", self.kis_account),
                ("MARKET_SIGNAL_KIS_ACCOUNT_PRODUCT_CODE", self.kis_account_product_code),
            )
            if value is None or value.get_secret_value() == ""
        ]
        if missing:
            raise ValueError(f"Missing KIS settings: {', '.join(missing)}")

    def require_telegram_credentials(self) -> None:
        missing = [
            name
            for name, value in (
                ("MARKET_SIGNAL_TELEGRAM_BOT_TOKEN", self.telegram_bot_token),
                ("MARKET_SIGNAL_TELEGRAM_CHAT_ID", self.telegram_chat_id),
            )
            if value is None or value.get_secret_value() == ""
        ]
        if missing:
            raise ValueError(f"Missing Telegram settings: {', '.join(missing)}")

    @property
    def kis_rest_base_url_text(self) -> str:
        return str(self.kis_rest_base_url).rstrip("/")


def load_settings() -> Settings:
    return Settings()
