import json
import logging
import sys
from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from fitminiapp_api.core.logging_config import JsonFormatter
from fitminiapp_api.db.session import engine
from fitminiapp_api.middleware.request_context import RequestContextMiddleware


@contextmanager
def _capture_http_logs(caplog):
    logger = logging.getLogger("app.http")
    previous_disabled = logger.disabled
    previous_propagate = logger.propagate
    # Alembic's in-process replay can disable pre-existing loggers on this worker.
    logger.disabled = False
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="app.http"):
            yield
    finally:
        logger.removeHandler(caplog.handler)
        logger.disabled = previous_disabled
        logger.propagate = previous_propagate


def test_json_formatter_includes_request_context() -> None:
    record = logging.LogRecord(
        name="app.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request_completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-123"
    record.method = "GET"
    record.path = "/api/v1/me"
    record.status_code = 200
    record.duration_ms = 12.345
    record.sql_query_count = 7
    record.sql_duration_ms = 4.321
    record.db_pool_size = 10
    record.db_pool_checked_out = 1
    record.db_pool_overflow = 0

    payload = json.loads(JsonFormatter(service="api").format(record))

    assert payload["service"] == "api"
    assert payload["message"] == "http_request_completed"
    assert payload["request_id"] == "request-123"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/me"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.345
    assert payload["sql_query_count"] == 7
    assert payload["sql_duration_ms"] == 4.321
    assert payload["db_pool_size"] == 10
    assert payload["db_pool_checked_out"] == 1
    assert payload["db_pool_overflow"] == 0


def test_json_formatter_preserves_worker_lifecycle_markers() -> None:
    formatter = JsonFormatter(service="notification-worker")

    for event_name in ("worker_started", "worker_drain_requested", "worker_stopped"):
        record = logging.LogRecord(
            name="fitminiapp_api.services.worker",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=event_name,
            args=(),
            exc_info=None,
        )

        assert json.loads(formatter.format(record))["message"] == event_name


def test_json_formatter_preserves_bounded_ai_coach_metadata_without_content() -> None:
    record = logging.LogRecord(
        name="app.ai_coach",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ai_coach_generation",
        args=(),
        exc_info=None,
    )
    fields = {
        "request_id": "request-ai-123",
        "job": "nutrition_knowledge",
        "data_class": "generic",
        "tool_name": "get_period_report_insights",
        "prompt_version": "ai-coach-period-report-v2",
        "schema_version": "ai-coach-period-report-output-v1",
        "policy_revision": "verified-generic-v1",
        "provider": "groq",
        "configured_model": "openai/gpt-oss-120b",
        "actual_model": "openai/gpt-oss-120b",
        "outcome": "answer",
        "error_code": "provider_unavailable",
        "safety_category": "clear",
        "attempts": 1,
        "retry_count": 0,
        "latency_ms": 123,
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
        "cost_microunits": 0,
        "report_version": "progress-report-v1",
        "report_revision": "report:0123456789abcdef",
    }
    for key, value in fields.items():
        setattr(record, key, value)
    record.prompt = "private prompt"
    record.answer = "private answer"
    record.user_id = 99887766

    payload = json.loads(JsonFormatter(service="api").format(record))

    assert payload["message"] == "ai_coach_generation"
    assert {key: payload[key] for key in fields} == fields
    assert "prompt" not in payload
    assert "answer" not in payload
    assert "user_id" not in payload


def test_news_cycle_summary_preserves_required_bounded_counters() -> None:
    record = logging.LogRecord(
        name="fitminiapp_api.services.news_worker",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="news_pipeline_cycle_completed",
        args=(),
        exc_info=None,
    )
    fields = {
        "sources_total": 3,
        "sources_checked": 2,
        "sources_success": 1,
        "sources_failed": 1,
        "candidates_fetched": 20,
        "candidates_new": 8,
        "candidates_duplicate": 4,
        "candidates_stale": 3,
        "candidates_below_threshold": 2,
        "candidates_eligible": 3,
        "drafts_created": 2,
        "drafts_skipped_daily_limit": 1,
        "llm_failures": 1,
        "telegram_delivery_failures": 0,
    }
    for key, value in fields.items():
        setattr(record, key, value)

    payload = json.loads(JsonFormatter(service="notification-worker").format(record))

    assert payload["message"] == "news_pipeline_cycle_completed"
    assert {key: payload[key] for key in fields} == fields


def test_candidate_reference_with_numeric_digest_remains_visible() -> None:
    record = logging.LogRecord(
        name="fitminiapp_api.services.news_ingestion",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="news_candidate_evaluated",
        args=(),
        exc_info=None,
    )
    record.candidate_ref = "candidate:0123456789abcdef"
    record.pipeline_stage = "scoring"
    record.outcome = "eligible"
    record.reason = "score_threshold_met"

    payload = json.loads(JsonFormatter(service="notification-worker").format(record))

    assert payload["candidate_ref"] == "candidate:0123456789abcdef"


def test_json_formatter_rejects_arbitrary_values_and_keeps_safe_diagnostics() -> None:
    markers = (
        "private_note_marker",
        "configured-database-password",
        "https://backend.example/private",
        "Иван Иванов",
        "личная заметка",
        "талия 81.4",
        "chat_id=99887766",
    )
    try:
        raise RuntimeError(" ".join(markers))
    except RuntimeError:
        record = logging.LogRecord(
            name="app",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="private_note_marker",
            args=(),
            exc_info=sys.exc_info(),
        )
    record.request_id = "request-safe-123"
    record.reason = "личная заметка"
    record.chat_id = 99887766

    rendered = JsonFormatter(service="api").format(record)
    payload = json.loads(rendered)

    assert payload["message"] == "application_log"
    assert payload["exception_type"] == "RuntimeError"
    assert payload["request_id"] == "request-safe-123"
    assert "exception" not in payload
    assert "reason" not in payload
    assert "chat_id" not in payload
    for marker in markers:
        assert marker not in rendered


def test_request_log_has_duration_and_health_probes_are_quiet(caplog) -> None:
    test_app = FastAPI()
    test_app.add_middleware(RequestContextMiddleware)

    @test_app.get("/example")
    def example() -> dict[str, str]:
        return {"status": "ok"}

    @test_app.get("/health/ready")
    def health_ready() -> dict[str, str]:
        return {"status": "ok"}

    @test_app.get("/profiles/{profile_id}")
    def profile(profile_id: str) -> dict[str, str]:
        return {"profile_id": profile_id}

    with TestClient(test_app) as test_client, _capture_http_logs(caplog):
        response = test_client.get("/example", headers={"X-Request-ID": "edge-123"})
        health_response = test_client.get("/health/ready")
        profile_response = test_client.get("/profiles/private-user-99887766")

    assert response.headers["X-Request-ID"] == "edge-123"
    assert health_response.status_code == 200
    records = [record for record in caplog.records if record.name == "app.http"]
    assert profile_response.status_code == 200
    assert len(records) == 2
    assert records[0].request_id == "edge-123"
    assert records[0].method == "GET"
    assert records[0].path == "/example"
    assert records[0].status_code == 200
    assert records[0].duration_ms >= 0
    assert records[0].sql_query_count == 0
    assert records[0].sql_duration_ms == 0
    assert records[0].db_pool_checked_out >= 0
    assert records[1].path == "/profiles/{profile_id}"
    assert "private-user-99887766" not in records[1].path


def test_request_log_includes_sql_metrics_from_sync_endpoint(caplog) -> None:
    test_app = FastAPI()
    test_app.add_middleware(RequestContextMiddleware)

    @test_app.get("/database-example")
    def database_example() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    with TestClient(test_app) as test_client, _capture_http_logs(caplog):
        response = test_client.get("/database-example")

    assert response.status_code == 200
    records = [record for record in caplog.records if record.name == "app.http"]
    assert len(records) == 1
    assert records[0].sql_query_count == 1
    assert records[0].sql_duration_ms >= 0
