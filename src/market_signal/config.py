from decimal import Decimal

from pydantic import Field, SecretStr
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

    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = Field(default=7497, gt=0)
    ibkr_client_id: int = Field(default=1, ge=0)


def load_settings() -> Settings:
    return Settings()
