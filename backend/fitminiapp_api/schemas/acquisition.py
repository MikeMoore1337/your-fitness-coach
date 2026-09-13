from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

AttributionSource = Literal["google", "yandex", "telegram", "direct", "referral", "utm"]
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$")


def _validate_token(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > max_length or not _SAFE_TOKEN.fullmatch(normalized):
        raise ValueError("attribution token contains unsupported characters")
    if "@" in normalized or re.fullmatch(r"[+0-9(). -]{7,}", normalized):
        raise ValueError("attribution token must not contain personal contact data")
    return normalized


def _validate_path(value: str) -> str:
    if not value.startswith("/") or "?" in value or "#" in value:
        raise ValueError("first_landing_path must be a clean absolute path")
    if len(value) > 256 or any(ord(character) < 0x20 for character in value):
        raise ValueError("first_landing_path is invalid")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        raise ValueError("first_landing_path must not contain an origin")
    return value


def _validate_referrer(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    try:
        parsed = urlsplit(normalized)
    except ValueError as exc:
        raise ValueError("first_referrer is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or any(ord(character) < 0x20 for character in normalized)
    ):
        raise ValueError("first_referrer must contain only an HTTP(S) origin and safe path")
    if len(normalized) > 512:
        raise ValueError("first_referrer is too long")
    return normalized


class FirstTouchAttributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_touch_source: AttributionSource
    first_touch_medium: str = Field(min_length=1, max_length=64)
    first_touch_campaign: str | None = Field(default=None, max_length=128)
    first_landing_path: str = Field(min_length=1, max_length=256)
    first_referrer: str | None = Field(default=None, max_length=512)
    first_touch_at: datetime
    utm_source: str | None = Field(default=None, max_length=128)
    utm_medium: str | None = Field(default=None, max_length=128)
    utm_campaign: str | None = Field(default=None, max_length=128)
    utm_content: str | None = Field(default=None, max_length=128)
    utm_term: str | None = Field(default=None, max_length=128)

    @field_validator("first_touch_medium")
    @classmethod
    def validate_medium(cls, value: str) -> str:
        return _validate_token(value, max_length=64) or "unknown"

    @field_validator("first_touch_campaign")
    @classmethod
    def validate_campaign(cls, value: str | None) -> str | None:
        return _validate_token(value, max_length=128)

    @field_validator("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
    @classmethod
    def validate_utm(cls, value: str | None) -> str | None:
        return _validate_token(value, max_length=128)

    _validate_landing_path = field_validator("first_landing_path")(_validate_path)
    _validate_first_referrer = field_validator("first_referrer")(_validate_referrer)

    @field_validator("first_touch_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("first_touch_at must include a timezone")
        return value
