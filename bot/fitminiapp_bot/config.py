from typing import Literal
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    bot_token: str = Field(validation_alias="TELEGRAM_BOT_TOKEN")
    frontend_base_url: str = "https://app.your-fitness-coach.ru"
    backend_internal_url: str = "http://backend:8000"
    bot_internal_token: str
    bot_polling_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("BOT_POLLING_ENABLED", "TELEGRAM_BOT_POLLING_ENABLED"),
    )
    bot_polling_lock_dir: str = "/var/lock/fitminiapp-bot"
    bot_polling_health_path: str = ""  # Opt-in read-only observer; no change to bot runtime.
    bot_conflict_retry_seconds: int = Field(default=300, ge=30)
    bot_profile_sync_state_path: str = "/var/lock/fitminiapp-bot/profile-sync-state.json"
    telegram_bot_proxy_url: str = Field(default="", validation_alias="TELEGRAM_BOT_PROXY_URL")
    admin_telegram_user_ids: str = ""
    privacy_policy_url: str = ""
    news_channel_username: str = ""

    @field_validator("telegram_bot_proxy_url")
    @classmethod
    def validate_telegram_proxy_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "socks5", "socks5h"} or not parsed.hostname:
            raise ValueError("Telegram proxy URL must be an absolute HTTP or SOCKS5 URL")
        if parsed.query or parsed.fragment:
            raise ValueError("Telegram proxy URL must not contain query parameters or a fragment")
        return normalized

    @property
    def bot_api_proxy_url(self) -> str:
        """Return only the explicitly configured Bot API route."""

        return self.telegram_bot_proxy_url

    @property
    def admin_telegram_id_set(self) -> set[int]:
        result: set[int] = set()
        for item in self.admin_telegram_user_ids.replace(";", ",").split(","):
            value = item.strip()
            if not value:
                continue
            try:
                result.add(int(value))
            except ValueError as exc:
                raise ValueError(f"Invalid ADMIN_TELEGRAM_USER_IDS value: {value}") from exc
        return result

    @model_validator(mode="after")
    def validate_runtime(self) -> Settings:
        _ = self.admin_telegram_id_set
        if self.app_env != "prod":
            return self
        if not self.bot_token.strip() or self.bot_token.strip().lower() in {
            "change-me",
            "replace-me",
        }:
            raise ValueError("TELEGRAM_BOT_TOKEN must be configured in prod")
        normalized_internal_token = self.bot_internal_token.strip().lower()
        if len(self.bot_internal_token) < 32 or normalized_internal_token.startswith(
            ("change-", "replace-")
        ):
            raise ValueError(
                "BOT_INTERNAL_TOKEN must be at least 32 characters and non-placeholder in prod"
            )
        frontend = urlparse(self.frontend_base_url)
        if frontend.scheme != "https" or not frontend.netloc:
            raise ValueError("FRONTEND_BASE_URL must be an absolute HTTPS URL in prod")
        backend = urlparse(self.backend_internal_url)
        if backend.scheme not in {"http", "https"} or not backend.netloc:
            raise ValueError("BACKEND_INTERNAL_URL must be an absolute HTTP(S) URL in prod")
        return self


settings = Settings()
