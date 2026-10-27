"""Real PG16 privilege/session proof in the existing isolated migrated-stack job."""

from __future__ import annotations

import ipaddress
import os
import uuid

import pytest
from scripts.sequential_deploy_safety import OBSERVER_SQL, SafetyError, validate_snapshot

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MIGRATED_STACK_TEST") != "1",
    reason="requires the explicitly enabled isolated PostgreSQL migrated-stack environment",
)


@pytest.fixture
def postgres_observer():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    parameters = conninfo_to_dict(dsn)
    assert parameters["host"] in {"127.0.0.1", "localhost", "db"}
    assert "test" in parameters["dbname"], "never provision roles in a non-test database"
    name = "yfc_observer_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN CONNECTION LIMIT 1 PASSWORD 'isolated-test-only'").format(
                sql.Identifier(name)
            )
        )
        admin.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(parameters["dbname"]), sql.Identifier(name)
            )
        )
        admin.execute(sql.SQL("GRANT pg_read_all_stats TO {}").format(sql.Identifier(name)))
    observer_dsn = make_conninfo(
        dsn,
        user=name,
        password="isolated-test-only",
        options="-c default_transaction_read_only=on -c statement_timeout=5000",
    )
    try:
        with psycopg.connect(observer_dsn, autocommit=True) as observer:
            yield dsn, observer, name
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(name)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))


def read(observer):
    return observer.execute(OBSERVER_SQL).fetchone()[0]


def test_non_superuser_observer_survives_application_disconnect_and_detects_lingering_transaction(
    postgres_observer,
):
    import psycopg

    dsn, observer, _ = postgres_observer
    with psycopg.connect(dsn, application_name="") as application:
        pid = application.execute("SELECT pg_backend_pid()").fetchone()[0]
        application.execute("SELECT 1")
        observed = read(observer)
        clients = validate_snapshot(
            observed, addresses={observed["server"]}, database=observed["database"]
        )
        legacy = next(row for row in clients if row["pid"] == pid)
        assert legacy["address"] and legacy["port"] > 0
        assert str(ipaddress.ip_address(legacy["address"])) == legacy["address"]
        assert str(ipaddress.ip_address(observed["server"])) == observed["server"]
        assert legacy["state"] == "idle in transaction"
        assert legacy["transaction"] is not None
    after = read(observer)
    assert all(row["pid"] != pid for row in after["clients"])
    assert after["stats"] is True and after["superuser"] is False
    assert after["readonly"] is True and after["application_access"] is False


def test_observer_cannot_write_and_extra_privileges_are_rejected(postgres_observer):
    import psycopg
    from psycopg import sql

    dsn, observer, name = postgres_observer
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        observer.execute("CREATE TABLE observer_must_not_write (id integer)")
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("GRANT pg_signal_backend TO {}").format(sql.Identifier(name)))
        observed = read(observer)
        assert observed["dangerous"] is True
        with pytest.raises(SafetyError, match="identity_or_visibility"):
            validate_snapshot(
                observed, addresses={observed["server"]}, database=observed["database"]
            )


def test_missing_stats_privileges_are_not_a_partial_pass(postgres_observer):
    import psycopg
    from psycopg import sql

    dsn, observer, name = postgres_observer
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("REVOKE pg_read_all_stats FROM {}").format(sql.Identifier(name)))
    observed = read(observer)
    assert observed["stats"] is False
    with pytest.raises(SafetyError, match="identity_or_visibility"):
        validate_snapshot(observed, addresses={observed["server"]}, database=observed["database"])
