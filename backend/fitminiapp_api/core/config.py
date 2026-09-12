import base64
import binascii
import re
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_placeholder_secret(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"", "change-me", "replace-me", "secret", "test-secret"} or (
        normalized.startswith(("change-", "replace-"))
    )


def _decode_base64url(value: str) -> bytes:
    normalized = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", normalized):
        raise ValueError
    unpadded = normalized.rstrip("=")
    if len(unpadded) % 4 == 1:
        raise ValueError
    try:
        return base64.urlsafe_b64decode(unpadded + "=" * (-len(unpadded) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ValueError from exc


def _load_vapid_private_key(value: str) -> ec.EllipticCurvePrivateKey:
    normalized = value.strip().replace("\\n", "\n")
    if "-----BEGIN" in normalized:
        key = serialization.load_pem_private_key(normalized.encode("utf-8"), password=None)
    else:
        raw = _decode_base64url(normalized)
        if len(raw) == 32:
            key = ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())
        else:
            key = serialization.load_der_private_key(raw, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise ValueError
    return key


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )

    app_env: Literal["dev", "test", "prod"]
    app_name: str
    app_debug: bool

    secret_key: str
    access_token_expire_minutes: int = Field(gt=0, le=24 * 60)
    refresh_token_expire_days: int = Field(gt=0, le=365)
    refresh_cookie_name: str = "fit_refresh_token"
    oauth_session_cookie_name: str = "fit_oauth_session"
    oauth_transaction_ttl_seconds: int = Field(default=600, ge=60, le=3600)

    database_url: str
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    db_pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60, le=86400)
    enable_dev_auth: bool = False
    enable_web_auth: bool = False
    enable_email_auth: bool = False
    admin_telegram_user_ids: str = ""

    app_domain: str = ""
    landing_domain: str = ""
    frontend_base_url: str = "https://app.your-fitness-coach.ru"
    google_site_verification: str = ""
    yandex_verification: str = ""
    telegram_bot_token: str
    telegram_bot_username: str = ""
    telegram_init_data_max_age_seconds: int = Field(default=300, ge=60, le=3600)
    telegram_bot_proxy_url: str = ""
    bot_internal_token: str = ""

    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_starttls: bool = True
    smtp_use_ssl: bool = False

    telegram_oauth_client_id: str = ""
    telegram_oauth_client_secret: str = ""
    oauth_http_timeout_seconds: float = Field(default=15, ge=5, le=60)
    oauth_force_ipv4: bool = True
    oauth_proxy_url: str = ""
    telegram_oauth_proxy_url: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    yandex_oauth_client_id: str = ""
    yandex_oauth_client_secret: str = ""
    vk_oauth_client_id: str = ""
    apple_oauth_client_id: str = ""
    apple_oauth_client_secret: str = ""

    food_provider: Literal["disabled", "open_food_facts"] = "disabled"
    open_food_facts_user_agent: str = ""
    food_usda_enabled: bool = False
    usda_fdc_api_key: SecretStr = SecretStr("")
    food_provider_timeout_seconds: float = Field(default=4, ge=1, le=15)

    worker_poll_seconds: int = Field(default=10, ge=1, le=3600)
    reminder_sync_seconds: int = Field(default=60, ge=10, le=3600)
    notification_delivery_concurrency: int = Field(default=8, ge=1, le=30)
    program_import_max_file_bytes: int = Field(default=2_000_000, ge=256_000, le=8_000_000)
    program_import_max_request_bytes: int = Field(default=2_400_000, ge=300_000, le=10_000_000)
    program_import_max_rows: int = Field(default=500, ge=20, le=2_000)
    program_import_max_columns: int = Field(default=64, ge=8, le=128)
    program_import_max_cells: int = Field(default=8_000, ge=100, le=100_000)
    program_import_max_cell_chars: int = Field(default=512, ge=64, le=4_096)
    program_import_max_xlsx_entries: int = Field(default=32, ge=8, le=128)
    program_import_max_xlsx_physical_rows: int = Field(default=2_000, ge=100, le=10_000)
    program_import_max_xlsx_physical_cells: int = Field(default=20_000, ge=1_000, le=200_000)
    program_import_max_xlsx_expanded_bytes: int = Field(
        default=4_000_000, ge=512_000, le=20_000_000
    )
    program_import_max_xlsx_compression_ratio: int = Field(default=100, ge=10, le=1_000)
    program_import_parse_timeout_seconds: float = Field(default=5, ge=1, le=30)
    program_import_draft_ttl_minutes: int = Field(default=60, ge=15, le=24 * 60)
    program_import_cleanup_batch_size: int = Field(default=100, ge=10, le=1_000)
    program_import_max_txt_lines: int = Field(default=2_000, ge=20, le=10_000)
    program_import_max_docx_entries: int = Field(default=32, ge=8, le=128)
    program_import_max_docx_paragraphs: int = Field(default=2_000, ge=20, le=10_000)
    program_import_max_docx_table_cells: int = Field(default=4_000, ge=20, le=20_000)
    program_import_max_docx_expanded_bytes: int = Field(
        default=4_000_000, ge=512_000, le=20_000_000
    )
    program_import_max_docx_compression_ratio: int = Field(default=100, ge=10, le=1_000)
    # The port is deliberately disabled for user-uploaded documents.  A future
    # synthetic-only adapter can be exercised without adding provider settings here.
    program_import_ai_enabled: bool = False
    program_import_ai_data_policy: Literal["disabled", "synthetic_only"] = "disabled"
    web_push_enabled: bool = False
    web_push_vapid_subject: str = ""
    web_push_vapid_public_key: str = ""
    web_push_vapid_private_key: SecretStr = SecretStr("")
    web_push_endpoint_hosts: str = (
        "fcm.googleapis.com,*.push.services.mozilla.com,*.push.apple.com,*.notify.windows.com"
    )
    web_push_delivery_timeout_seconds: float = Field(default=10, ge=3, le=30)
    audit_event_retention_days: int = Field(default=365, ge=90, le=3650)
    news_ingestion_enabled: bool = False
    news_channel_id: int | None = None
    news_channel_username: str = ""
    news_ingestion_cycle_seconds: int = Field(default=900, ge=60, le=86400)
    news_source_timeout_seconds: float = Field(default=10, ge=2, le=30)
    news_source_max_bytes: int = Field(default=1_048_576, ge=16_384, le=2_097_152)
    news_fetch_concurrency: int = Field(default=4, ge=1, le=8)
    news_candidate_score_threshold: int = Field(default=55, ge=1, le=100)
    news_retention_days: int = Field(default=90, ge=7, le=365)
    news_defer_hours: int = Field(default=24, ge=1, le=168)
    news_max_regenerations: int = Field(default=3, ge=0, le=10)
    news_draft_max_chars: int = Field(default=2600, ge=800, le=3200)
    news_daily_draft_limit: int = Field(default=3, ge=1, le=20)
    news_draft_profile: Literal["standard", "extended"] = "standard"
    news_auto_publish_low_risk: bool = False
    hermes_intake_enabled: bool = False
    hermes_intake_key_id: str = "hermes-local"
    hermes_intake_shared_secret: SecretStr = SecretStr("")
    hermes_intake_max_body_bytes: int = Field(default=262_144, ge=16_384, le=1_048_576)
    hermes_intake_max_source_count: int = Field(default=20, ge=1, le=20)
    hermes_intake_clock_skew_seconds: int = Field(default=300, ge=30, le=900)
    hermes_intake_replay_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    hermes_intake_rate_limit_per_minute: int = Field(default=30, ge=1, le=600)
    # AI Coach is a separate generic-only boundary.
    ai_coach_enabled: bool = False
    ai_coach_kill_switch: bool = False
    # The UI is separately gated for a small internal cohort. A runtime provider
    # flag must never implicitly expose a user-facing beta entry point.
    ai_coach_ui_enabled: bool = False
    ai_coach_internal_user_ids: str = ""
    ai_coach_provider: Literal["disabled", "groq"] = "disabled"
    groq_api_key: SecretStr = SecretStr("")
    ai_coach_endpoint: str = "https://api.groq.com/openai/v1/chat/completions"
    ai_coach_model: Literal["openai/gpt-oss-120b"] = "openai/gpt-oss-120b"
    ai_coach_cost_policy: Literal["free_only"] = "free_only"
    ai_coach_cost_class: Literal["free", "developer", "paid", "promo", "trial", "unknown"] = (
        "unknown"
    )
    ai_coach_data_policy: Literal["verified_generic_only", "unknown"] = "unknown"
    ai_coach_personal_enabled: bool = False
    ai_coach_personal_data_policy: Literal["verified_personal_user", "disabled"] = "disabled"
    ai_coach_structured_output: bool = True
    ai_coach_policy_revision: str = "unverified"
    ai_coach_timeout_seconds: float = Field(default=20, ge=1, le=60)
    ai_coach_max_attempts: int = Field(default=1, ge=1, le=2)
    ai_coach_max_output_tokens: int = Field(default=1024, ge=256, le=2048)
    ai_coach_max_context_chars: int = Field(default=8_000, ge=1_000, le=16_000)
    ai_coach_content_max_age_days: int = Field(default=365, ge=1, le=1_095)
    ai_coach_quota_window_seconds: int = Field(default=86_400, ge=60, le=604_800)
    ai_coach_per_user_request_limit: int = Field(default=5, ge=1, le=100)
    ai_coach_global_request_limit: int = Field(default=100, ge=1, le=10_000)
    ai_coach_cooldown_seconds: int = Field(default=30, ge=1, le=3_600)
    news_image_provider: Literal["disabled", "cloudflare_workers_ai"] = "disabled"
    news_image_cloudflare_account_id: str = ""
    news_image_cloudflare_api_token: str = ""
    news_image_cloudflare_free_plan_confirmed: bool = False
    news_image_model: Literal["@cf/black-forest-labs/flux-1-schnell"] = (
        "@cf/black-forest-labs/flux-1-schnell"
    )
    news_image_steps: Literal[4] = 4
    news_image_daily_request_limit: int = Field(default=20, ge=1, le=40)
    news_image_timeout_seconds: float = Field(default=60, ge=10, le=180)
    news_image_prompt_version: str = "news-image-v1"
    news_image_max_bytes: int = Field(default=8_388_608, ge=262_144, le=9_500_000)
    news_image_upload_max_bytes: int = Field(default=8_388_608, ge=262_144, le=9_500_000)
    news_publication_enabled: bool = False
    news_publication_renderer: Literal["news-publication-html-v1"] = "news-publication-html-v1"
    news_channel_environment: Literal["staging", "production"] = "staging"
    news_production_publication_confirmed: bool = False
    news_publication_timezone: str = "Europe/Moscow"
    news_schedule_min_minutes: int = Field(default=5, ge=1, le=1440)
    news_schedule_max_days: int = Field(default=30, ge=1, le=90)
    news_schedule_missed_minutes: int = Field(default=120, ge=5, le=1440)
    news_daily_publication_limit: int = Field(default=1, ge=1, le=10)
    weekly_digest_enabled: bool = False
    weekly_digest_consent_version: str = "weekly-news-v1"
    weekly_digest_min_items: int = Field(default=3, ge=1, le=5)
    weekly_digest_delivery_concurrency: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def validate_production_safety(self) -> Settings:
        if self.app_env != "prod":
            return self

        if _is_placeholder_secret(self.secret_key) or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters and non-placeholder in prod"
            )
        if _is_placeholder_secret(self.telegram_bot_token):
            raise ValueError("TELEGRAM_BOT_TOKEN must be configured in prod")
        if _is_placeholder_secret(self.bot_internal_token) or len(self.bot_internal_token) < 32:
            raise ValueError(
                "BOT_INTERNAL_TOKEN must be at least 32 characters and non-placeholder in prod"
            )
        if self.enable_dev_auth:
            raise ValueError("ENABLE_DEV_AUTH must be false in prod")
        if self.app_debug:
            raise ValueError("APP_DEBUG must be false in prod")
        if self.enable_email_auth and (
            not self.smtp_host.strip() or not self.smtp_from_email.strip()
        ):
            raise ValueError(
                "SMTP_HOST and SMTP_FROM_EMAIL must be configured when email auth is enabled in prod"
            )
        if (
            self.enable_web_auth
            and "telegram" in self.oauth_provider_names
            and not self.telegram_oauth_proxy_url
        ):
            raise ValueError(
                "TELEGRAM_OAUTH_PROXY_URL must be configured when Telegram browser OAuth "
                "is enabled in prod"
            )
        _ = self.admin_telegram_id_set

        parsed = urlparse(self.frontend_base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("FRONTEND_BASE_URL must be an absolute HTTPS URL in prod")
        return self

    @model_validator(mode="after")
    def validate_food_provider(self) -> Settings:
        if self.food_provider == "open_food_facts":
            user_agent = self.open_food_facts_user_agent.strip()
            if (
                not user_agent
                or "/" not in user_agent
                or "(" not in user_agent
                or ")" not in user_agent
            ):
                raise ValueError(
                    "OPEN_FOOD_FACTS_USER_AGENT must identify the app, version, and contact"
                )
        if self.food_usda_enabled and not self.usda_fdc_api_key.get_secret_value().strip():
            raise ValueError("USDA_FDC_API_KEY must be configured when FOOD_USDA_ENABLED is true")
        return self

    @model_validator(mode="after")
    def validate_web_push(self) -> Settings:
        hosts = self.web_push_endpoint_host_allowlist
        if not hosts:
            raise ValueError("WEB_PUSH_ENDPOINT_HOSTS must contain at least one host")
        for host in hosts:
            if not re.fullmatch(
                r"(?:\*\.)?[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*",
                host,
            ):
                raise ValueError("WEB_PUSH_ENDPOINT_HOSTS contains an invalid host")

        if not self.web_push_enabled:
            return self

        subject = self.web_push_vapid_subject.strip()
        try:
            parsed_subject = urlparse(subject)
            subject_hostname = parsed_subject.hostname
            subject_port = parsed_subject.port
        except ValueError as exc:
            raise ValueError(
                "WEB_PUSH_VAPID_SUBJECT must be an absolute credential-free mailto or HTTPS URL"
            ) from exc
        valid_mailto = (
            parsed_subject.scheme == "mailto"
            and bool(
                re.fullmatch(
                    r"[^@\s]+@(?:localhost|[a-z0-9%_-]+(?:\.[a-z0-9%_-]+)+)",
                    parsed_subject.path,
                    re.IGNORECASE,
                )
            )
            and not parsed_subject.netloc
            and not parsed_subject.query
            and not parsed_subject.fragment
        )
        valid_https = (
            parsed_subject.scheme == "https"
            and isinstance(subject_hostname, str)
            and (
                subject_hostname == "localhost"
                or "." in subject_hostname
                or ":" in subject_hostname
            )
            and not parsed_subject.username
            and not parsed_subject.password
            and not parsed_subject.path
            and not parsed_subject.query
            and not parsed_subject.fragment
            and (subject_port is None or 1 <= subject_port <= 65535)
        )
        if not (valid_mailto or valid_https):
            raise ValueError(
                "WEB_PUSH_VAPID_SUBJECT must be an absolute credential-free mailto or HTTPS URL"
            )

        try:
            public_key = _decode_base64url(self.web_push_vapid_public_key)
        except ValueError as exc:
            raise ValueError("WEB_PUSH_VAPID_PUBLIC_KEY must be a base64url P-256 key") from exc
        if len(public_key) != 65 or public_key[0] != 4:
            raise ValueError("WEB_PUSH_VAPID_PUBLIC_KEY must be an uncompressed P-256 key")

        try:
            private_key = _load_vapid_private_key(
                self.web_push_vapid_private_key.get_secret_value()
            )
            derived_public_key = private_key.public_key().public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        except Exception as exc:
            raise ValueError("WEB_PUSH_VAPID_PRIVATE_KEY must be a valid P-256 key") from exc
        if derived_public_key != public_key:
            raise ValueError("WEB_PUSH_VAPID_PUBLIC_KEY does not match the private key")
        return self

    @model_validator(mode="after")
    def validate_news_pipeline(self) -> Settings:
        news_active = (
            self.news_ingestion_enabled
            or self.news_publication_enabled
            or self.weekly_digest_enabled
        )
        if news_active and not self.admin_telegram_id_set:
            raise ValueError(
                "ADMIN_TELEGRAM_USER_IDS must be configured when the news workflow is enabled"
            )
        if news_active and self.news_channel_id is None:
            raise ValueError(
                "NEWS_CHANNEL_ID must be confirmed before the news workflow is enabled"
            )
        if self.news_channel_id is not None and self.news_channel_id >= 0:
            raise ValueError("NEWS_CHANNEL_ID must be a negative Telegram channel id")
        username = self.news_channel_username.strip().removeprefix("@").lower()
        if username and not re.fullmatch(r"[a-z][a-z0-9_]{4,31}", username):
            raise ValueError("NEWS_CHANNEL_USERNAME is invalid")
        self.news_channel_username = username
        if self.news_image_provider == "cloudflare_workers_ai":
            if not self.news_image_cloudflare_account_id.strip() or not (
                self.news_image_cloudflare_api_token.strip()
            ):
                raise ValueError(
                    "NEWS_IMAGE_CLOUDFLARE_ACCOUNT_ID and "
                    "NEWS_IMAGE_CLOUDFLARE_API_TOKEN are required"
                )
            if not self.news_image_cloudflare_free_plan_confirmed:
                raise ValueError(
                    "NEWS_IMAGE_CLOUDFLARE_FREE_PLAN_CONFIRMED must be true; "
                    "paid image generation is prohibited"
                )
        if self.news_publication_enabled and not self.news_ingestion_enabled:
            raise ValueError(
                "NEWS_INGESTION_ENABLED must be true when NEWS_PUBLICATION_ENABLED=true"
            )
        if self.weekly_digest_enabled and not self.news_publication_enabled:
            raise ValueError(
                "NEWS_PUBLICATION_ENABLED must be true when WEEKLY_DIGEST_ENABLED=true"
            )
        if self.weekly_digest_enabled and not self.news_channel_username:
            raise ValueError("NEWS_CHANNEL_USERNAME is required when WEEKLY_DIGEST_ENABLED=true")
        if self.hermes_intake_enabled:
            if not re.fullmatch(r"[a-z][a-z0-9_-]{2,63}", self.hermes_intake_key_id.strip()):
                raise ValueError("HERMES_INTAKE_KEY_ID is invalid")
            if len(self.hermes_intake_shared_secret.get_secret_value().strip()) < 32:
                raise ValueError(
                    "HERMES_INTAKE_SHARED_SECRET must be at least 32 characters when intake is enabled"
                )
        if (
            self.app_env == "prod"
            and self.news_publication_enabled
            and self.news_channel_environment != "production"
        ):
            raise ValueError(
                "NEWS_CHANNEL_ENVIRONMENT must be production for enabled production publishing"
            )
        if (
            self.news_publication_enabled
            and self.news_channel_environment == "production"
            and not self.news_production_publication_confirmed
        ):
            raise ValueError(
                "NEWS_PRODUCTION_PUBLICATION_CONFIRMED must be true after separate "
                "owner authorization"
            )
        try:
            ZoneInfo(self.news_publication_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("NEWS_PUBLICATION_TIMEZONE must be a valid IANA timezone") from exc
        return self

    @model_validator(mode="after")
    def validate_ai_coach(self) -> Settings:
        if not self.ai_coach_enabled:
            return self
        if self.ai_coach_kill_switch:
            return self
        if self.ai_coach_provider != "groq":
            raise ValueError("AI_COACH_PROVIDER must be groq when AI_COACH_ENABLED is true")
        if not self.groq_api_key.get_secret_value().strip():
            raise ValueError("GROQ_API_KEY must be configured when AI Coach is enabled")
        if self.ai_coach_cost_policy != "free_only" or self.ai_coach_cost_class != "free":
            raise ValueError(
                "AI Coach requires a verified free provider under the free_only cost policy"
            )
        if self.ai_coach_data_policy != "verified_generic_only":
            raise ValueError("AI_COACH_DATA_POLICY must verify generic-only processing")
        if not self.ai_coach_structured_output:
            raise ValueError("AI_COACH_STRUCTURED_OUTPUT must remain true")
        parsed = urlparse(self.ai_coach_endpoint)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.groq.com"
            or parsed.path != "/openai/v1/chat/completions"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "AI_COACH_ENDPOINT must be the credential-free Groq HTTPS chat completions URL"
            )
        return self

    @field_validator("weekly_digest_consent_version")
    @classmethod
    def validate_weekly_digest_consent_version(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", normalized):
            raise ValueError("WEEKLY_DIGEST_CONSENT_VERSION is invalid")
        return normalized

    @field_validator("open_food_facts_user_agent")
    @classmethod
    def normalize_open_food_facts_user_agent(cls, value: str) -> str:
        normalized = value.strip()
        if "\r" in normalized or "\n" in normalized or len(normalized) > 256:
            raise ValueError(
                "OPEN_FOOD_FACTS_USER_AGENT must be a single line up to 256 characters"
            )
        return normalized

    @field_validator("news_channel_id", mode="before")
    @classmethod
    def normalize_optional_news_channel_id(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("oauth_proxy_url", "telegram_oauth_proxy_url", "telegram_bot_proxy_url")
    @classmethod
    def validate_oauth_proxy_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.hostname:
            raise ValueError("OAuth proxy URL must be an absolute HTTP(S) or SOCKS5 URL")
        if parsed.query or parsed.fragment:
            raise ValueError("OAuth proxy URL must not contain query parameters or a fragment")
        return normalized

    @property
    def bot_api_proxy_url(self) -> str:
        return self.telegram_bot_proxy_url

    @property
    def web_push_endpoint_host_allowlist(self) -> tuple[str, ...]:
        return tuple(
            host.strip().lower() for host in self.web_push_endpoint_hosts.split(",") if host.strip()
        )

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

    @property
    def ai_coach_internal_user_id_set(self) -> set[int]:
        result: set[int] = set()
        for item in self.ai_coach_internal_user_ids.replace(";", ",").split(","):
            value = item.strip()
            if not value:
                continue
            try:
                result.add(int(value))
            except ValueError as exc:
                raise ValueError(f"Invalid AI_COACH_INTERNAL_USER_IDS value: {value}") from exc
        return result

    @property
    def oauth_provider_names(self) -> list[str]:
        configured = [
            (
                "telegram",
                bool(
                    self.telegram_oauth_client_id.strip()
                    and self.telegram_oauth_client_secret.strip()
                ),
            ),
            (
                "google",
                bool(
                    self.google_oauth_client_id.strip() and self.google_oauth_client_secret.strip()
                ),
            ),
            (
                "yandex",
                bool(
                    self.yandex_oauth_client_id.strip() and self.yandex_oauth_client_secret.strip()
                ),
            ),
            ("vk", bool(self.vk_oauth_client_id.strip())),
            (
                "apple",
                bool(self.apple_oauth_client_id.strip() and self.apple_oauth_client_secret.strip()),
            ),
        ]
        return [name for name, enabled in configured if enabled]


settings = Settings()
