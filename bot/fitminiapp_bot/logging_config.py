from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

SAFE_CODE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
SAFE_EVENT_NAMES = frozenset(
    {
        "bot_token_not_configured",
        "frontend_url_invalid",
        "menu_button_configuration_failed",
        "menu_button_configured",
        "menu_button_verification_failed",
        "open_button_delivery_failed",
        "polling_disabled",
        "polling_file_lock_acquired",
        "polling_file_lock_unavailable",
        "polling_file_lock_waiting",
        "support_case_creation_failed",
        "support_relay_result_failed",
        "support_reply_claim_failed",
        "support_reply_result_failed",
        "support_request_delivery_failed",
        "support_request_rate_limited",
        "support_request_relayed",
        "support_response_delivered",
        "support_response_delivery_failed",
        "support_response_preamble_cleanup_failed",
        "support_response_undeliverable",
        "telegram_account_link_failed",
        "telegram_polling_failed",
        "telegram_polling_conflict",
        "telegram_polling_recovered",
        "telegram_polling_retry_scheduled",
        "telegram_polling_started",
        "telegram_polling_starting",
        "timezone_backend_update_failed",
        "weekly_digest_backend_failed",
        "weekly_digest_backend_unavailable",
    }
)
STRUCTURED_FIELDS = (
    "error_code",
    "retry_seconds",
    "retry_attempt",
    "status_code",
)


class JsonFormatter(logging.Formatter):
    """JSON formatter that emits only allowlisted operational fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": "telegram-bot",
            "logger": record.name,
            "message": (
                record.msg
                if isinstance(record.msg, str) and record.msg in SAFE_EVENT_NAMES
                else "application_log"
            ),
        }
        for field in STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if field in {"retry_seconds", "retry_attempt", "status_code"}:
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                    payload[field] = value
            elif isinstance(value, str) and SAFE_CODE_PATTERN.fullmatch(value):
                payload[field] = value
        if record.exc_info:
            exception_class = record.exc_info[0]
            if exception_class is not None and SAFE_CODE_PATTERN.fullmatch(
                exception_class.__name__
            ):
                payload["exception_type"] = exception_class.__name__
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
