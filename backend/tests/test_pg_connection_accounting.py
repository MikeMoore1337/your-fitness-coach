"""Execute the shipped capacity SQL on PostgreSQL with isolated activity rows."""

import json
import os

import psycopg
import pytest
from scripts.trusted_legacy_pg_snapshot import APPLICATION_NAMES, snapshot_sql


@pytest.mark.parametrize(
    ("activity", "counts"),
    (
        ([], (0, 0, 0, 0)),
        ([("client backend", "yfc-backend")], (1, 1, 0, 0)),
        ([("client backend", "unknown")], (1, 0, 0, 1)),
        ([("client backend", ""), ("client backend", None)], (2, 0, 2, 0)),
        ([("background writer", ""), ("checkpointer", None)], (0, 0, 0, 0)),
        ([("autovacuum worker", "yfc-backend")], (0, 0, 0, 0)),
        (
            [
                ("client backend", "yfc-worker"),
                ("client backend", "tool"),
                ("client backend", ""),
                ("walwriter", ""),
            ],
            (3, 1, 1, 1),
        ),
        ([("walsender", "replica")], None),
        ([("walreceiver", "")], None),
        ([("logical replication worker", "")], None),
        ([("extension worker", "")], None),
        ([(None, "")], None),
    ),
)
def test_postgres_executes_single_scan_accounting(activity, counts):
    url = os.environ["DATABASE_URL"]
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("PostgreSQL integration requires the existing PostgreSQL test profile")
    query = snapshot_sql(", ".join(f"'{name}'" for name in APPLICATION_NAMES))
    query = query.replace(
        "FROM pg_stat_activity",
        """FROM jsonb_to_recordset(%s::jsonb)
        AS activity(backend_type text, application_name text)""",
    )
    rows = [{"backend_type": kind, "application_name": name} for kind, name in activity]
    with (
        psycopg.connect(
            url.replace("postgresql+psycopg://", "postgresql://", 1),
            options="-c default_transaction_read_only=on",
        ) as db,
        db.cursor() as cursor,
    ):
        cursor.execute(query, (json.dumps(rows),))
        observed = cursor.fetchone()
    if counts is None:
        assert observed is None
    else:
        assert observed[4:8] == counts
        assert observed[4] == sum(observed[5:8])
