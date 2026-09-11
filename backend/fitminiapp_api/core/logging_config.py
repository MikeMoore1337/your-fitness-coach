from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
SAFE_CODE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
SAFE_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9_.:/-]{1,128}\Z")
SAFE_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
SAFE_REPORT_REVISION_PATTERN = re.compile(r"[0-9a-f]{64}\Z", re.IGNORECASE)
SAFE_METHOD_PATTERN = re.compile(r"[A-Z]{3,10}\Z")
SAFE_ROUTE_PATTERN = re.compile(r"(?:/[A-Za-z0-9_./{}:-]{0,255}|unmatched)\Z")
SAFE_EVENT_NAMES = frozenset(
    {
        "application_started",
        "application_stopped",
        "ai_coach_generation",
        "auth_email_delivery_failed",
        "food_provider_barcode_unavailable",
        "food_provider_search_unavailable",
        "http_request_completed",
        "http_request_rejected",
        "notification_delivery_failed",
        "notification_delivery_completed",
        "news_draft_generation_failed",
        "news_draft_generation_succeeded",
        "news_candidate_evaluated",
        "news_pipeline_no_enabled_sources",
        "news_pipeline_cycle_completed",
        "news_pipeline_cycle_failed",
        "news_review_delivery_failed",
        "news_review_delivery_succeeded",
        "news_source_fetch_failed",
        "news_source_fetch_succeeded",
        "oauth_link_conflict",
        "oauth_link_failed",
        "oauth_link_start_failed",
        "oauth_login_blocked",
        "oauth_login_failed",
        "oauth_start_failed",
        "telegram_auth_rejected",
        "telegram_delivery_skipped",
        "unhandled_exception",
        "worker_drain_requested",
        "worker_started",
        "worker_stopped",
        "weekly_digest_delivery_batch_completed",
    }
)
SAFE_PROVIDER_NAMES = frozenset(
    {
        "apple",
        "deterministic",
        "google",
        "groq",
        "open_food_facts",
        "openai_compatible",
        "telegram",
        "vk",
        "yandex",
        "web_push",
    }
)
STRUCTURED_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "sql_query_count",
    "sql_duration_ms",
    "db_pool_size",
    "db_pool_checked_out",
    "db_pool_overflow",
    "body_limit_bytes",
    "job",
    "data_class",
    "tool_name",
    "prompt_version",
    "schema_version",
    "policy_revision",
    "notification_ref",
    "notification_category",
    "delivery_error",
    "provider",
    "configured_model",
    "actual_model",
    "reason",
    "pipeline_stage",
    "outcome",
    "error_code",
    "safety_category",
    "source_ref",
    "candidate_ref",
    "topic",
    "score",
    "items_count",
    "duplicate_count",
    "candidate_count",
    "queue_age_seconds",
    "attempt_count",
    "attempts",
    "retry_count",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_microunits",
    "report_version",
    "report_revision",
    "issue_count",
    "queued",
    "processing",
    "sent",
    "failed",
    "cancelled",
    "uncertain",
    "sources_total",
    "sources_checked",
    "sources_success",
    "sources_failed",
    "candidates_fetched",
    "candidates_new",
    "candidates_duplicate",
    "candidates_stale",
    "candidates_below_threshold",
    "candidates_eligible",
    "drafts_created",
    "drafts_skipped_daily_limit",
    "llm_failures",
    "telegram_delivery_failures",
)
INTEGER_FIELDS = {
    "status_code",
    "sql_query_count",
    "db_pool_size",
    "db_pool_checked_out",
    "db_pool_overflow",
    "body_limit_bytes",
    "attempts",
    "retry_count",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_microunits",
    "items_count",
    "duplicate_count",
    "candidate_count",
    "queue_age_seconds",
    "attempt_count",
    "issue_count",
    "queued",
    "processing",
    "sent",
    "failed",
    "cancelled",
    "uncertain",
    "score",
    "sources_total",
    "sources_checked",
    "sources_success",
    "sources_failed",
    "candidates_fetched",
    "candidates_new",
    "candidates_duplicate",
    "candidates_stale",
    "candidates_below_threshold",
    "candidates_eligible",
    "drafts_created",
    "drafts_skipped_daily_limit",
    "llm_failures",
    "telegram_delivery_failures",
}
FLOAT_FIELDS = {"duration_ms", "sql_duration_ms", "latency_ms"}
CODE_FIELDS = {
    "notification_ref",
    "notification_category",
    "delivery_error",
    "job",
    "data_class",
    "tool_name",
    "prompt_version",
    "schema_version",
    "policy_revision",
    "reason",
    "pipeline_stage",
    "outcome",
    "error_code",
    "safety_category",
    "source_ref",
    "candidate_ref",
    "topic",
    "report_version",
    "report_revision",
}
MODEL_FIELDS = {"configured_model", "actual_model"}


class JsonFormatter(logging.Formatter):
    """Small dependency-free JSON formatter for container stdout logs."""

    def __init__(
        self,
        *,
        service: str,
        sensitive_values: tuple[str, ...] = (),
        include_exception_details: bool = False,
    ) -> None:
        super().__init__()
        self.service = service
        self.include_exception_details = include_exception_details
        self.sensitive_values = tuple(
            sorted((value for value in sensitive_values if value), key=len, reverse=True)
        )

    def _sanitize(self, value: object) -> object:
        if not isinstance(value, str):
            return value
        sanitized = value
        for secret in self.sensitive_values:
            sanitized = sanitized.replace(secret, "[redacted]")
        return URL_PATTERN.sub("[url]", sanitized)

    def _event_name(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, str) and record.msg in SAFE_EVENT_NAMES:
            return record.msg
        return "application_log"

    def _structured_value(self, field: str, value: object) -> object | None:
        if field in INTEGER_FIELDS:
            return (
                value
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0
                else None
            )
        if field in FLOAT_FIELDS:
            return (
                value
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
                else None
            )
        if not isinstance(value, str):
            return None
        if field == "request_id":
            return value if SAFE_REQUEST_ID_PATTERN.fullmatch(value) else None
        if field == "method":
            return value if SAFE_METHOD_PATTERN.fullmatch(value) else None
        if field == "path":
            return value if SAFE_ROUTE_PATTERN.fullmatch(value) else None
        if field == "provider":
            return value if value in SAFE_PROVIDER_NAMES else None
        if field in MODEL_FIELDS:
            return value if SAFE_IDENTIFIER_PATTERN.fullmatch(value) else None
        if field == "report_revision":
            return value if SAFE_REPORT_REVISION_PATTERN.fullmatch(value) else None
        if field in CODE_FIELDS:
            return value if SAFE_CODE_PATTERN.fullmatch(value) else None
        return None

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": self._event_name(record),
        }
        for field in STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                safe_value = self._structured_value(field, value)
                if safe_value is not None:
                    payload[field] = safe_value
        if record.exc_info:
            exception_class = record.exc_info[0]
            if exception_class is not None and SAFE_CODE_PATTERN.fullmatch(
                exception_class.__name__
            ):
                payload["exception_type"] = exception_class.__name__
            if self.include_exception_details:
                payload["exception"] = self._sanitize(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(
    *,
    debug: bool,
    service: str,
    sensitive_values: tuple[str, ...] = (),
) -> None:
    """Route application and Uvicorn records through one JSON stdout handler."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            service=service,
            sensitive_values=sensitive_values,
            include_exception_details=debug,
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Uvicorn installs dedicated text handlers before loading the application.
    # Propagating through root keeps startup, shutdown and application logs uniform.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
