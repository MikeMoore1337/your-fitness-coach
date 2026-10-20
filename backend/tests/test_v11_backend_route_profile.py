"""Representative synthetic PG16 read-route profiling for Product V11-02.

Run with pytest -s to print sanitized route metrics. These are synthetic
local/CI diagnostics; they are not production p95/p99 measurements.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from statistics import median
from time import perf_counter

import pytest

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import engine


@contextmanager
def _http_records(caplog):
    logger = logging.getLogger("app.http")
    old_disabled = logger.disabled
    old_propagate = logger.propagate
    # Existing migration/test fixtures can disable named loggers.
    logger.disabled = False
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="app.http"):
            yield
    finally:
        logger.removeHandler(caplog.handler)
        logger.disabled = old_disabled
        logger.propagate = old_propagate


def _test_token(client, telegram_user_id: int, *, is_coach: bool) -> str:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "username": f"v11_test_{telegram_user_id}",
            "is_coach": is_coach,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="V11 read-path diagnostics require isolated PostgreSQL fixtures",
)
@pytest.mark.parametrize(
    ("path", "actor"),
    (
        ("/api/v1/me", "athlete"),
        ("/api/v1/workouts/today", "athlete"),
        ("/api/v1/programs/templates/mine", "athlete"),
        ("/api/v1/nutrition/diary", "athlete"),
        ("/api/v1/coach/clients", "coach"),
        ("/api/v1/coach/inbox", "coach"),
    ),
)
def test_v11_representative_read_paths_emit_bounded_sanitized_metrics(
    client, caplog, path: str, actor: str
) -> None:
    """Record request/SQL/response costs without external or production data."""
    token = _test_token(
        client,
        1001 if actor == "coach" else 2001,
        is_coach=actor == "coach",
    )
    request_path = (
        f"{path}?diary_date={today_msk().isoformat()}"
        if path == "/api/v1/nutrition/diary"
        else path
    )
    headers = {"Authorization": f"Bearer {token}"}
    elapsed_ms: list[float] = []
    sql_queries: list[int] = []
    sql_ms: list[float] = []
    response_sizes: list[int] = []

    with _http_records(caplog):
        for _ in range(3):
            caplog.clear()
            started = perf_counter()
            response = client.get(request_path, headers=headers)
            elapsed_ms.append((perf_counter() - started) * 1000)
            assert response.status_code == 200, (path, response.status_code)
            assert response.headers.get("X-Request-ID")
            response_sizes.append(len(response.content))
            records = [
                record
                for record in caplog.records
                if record.name == "app.http"
                and record.getMessage() == "http_request_completed"
                and getattr(record, "method", None) == "GET"
            ]
            assert len(records) == 1, (path, len(records))
            record = records[0]
            assert record.status_code == 200
            # FastAPI exposes registered route templates: nested routers can
            # log /templates/mine, and the root /me subrouter logs an empty
            # local route. Both are valid sanitized template identifiers.
            assert isinstance(record.path, str)
            assert record.path == "" or record.path.startswith("/")
            assert "?" not in record.path
            assert record.sql_query_count >= 0
            assert record.sql_duration_ms >= 0
            assert record.duration_ms >= 0
            sql_queries.append(int(record.sql_query_count))
            sql_ms.append(float(record.sql_duration_ms))

    assert len(response_sizes) == 3
    assert all(size > 0 for size in response_sizes)
    # This read-only scenario must serialize the same fixture data each time.
    assert len(set(response_sizes)) == 1
    assert len(sql_queries) == 3

    # Deliberately no absolute CI latency/pass-fail budget. Synthetic runner
    # scheduling and DB cache produce noise; true product budgets need field data.
    print(
        f"V11_02_SYNTHETIC_ROUTE path={path}"
        f" athlete_or_coach={actor}"
        f" requests={len(elapsed_ms)}"
        f" http_p50_ms={median(elapsed_ms):.3f}"
        f" sql_p50_ms={median(sql_ms):.3f}"
        f" sql_min_queries={min(sql_queries)}"
        f" sql_max_queries={max(sql_queries)}"
        f" response_bytes={response_sizes[0]}"
    )
