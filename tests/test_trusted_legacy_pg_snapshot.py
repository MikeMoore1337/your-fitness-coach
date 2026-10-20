"""Offline contract tests for the self-contained legacy PostgreSQL probe."""

from __future__ import annotations

import json
import runpy
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import trusted_legacy_pg_snapshot as legacy

VALID_ROW = (160000, 300, 3, 2, 20, 8, 3, 9, True, False)


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.queries: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query: str) -> None:
        self.queries.append(query)

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, cursor: _Cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_value


def _fake_driver(monkeypatch, row):
    cursor = _Cursor(row)
    calls = []

    def connect(url, *, connect_timeout, options):
        calls.append((url, connect_timeout, options))
        return _Connection(cursor)

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:secret@db/app")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    return calls, cursor


def test_legacy_probe_collects_only_sanitized_counts_in_read_only_transaction(
    monkeypatch,
) -> None:
    calls, cursor = _fake_driver(monkeypatch, VALID_ROW)
    data = legacy.collect()

    assert data["status"] == "PASS"
    assert data["postgres"] == {
        "server_version_major": 16,
        "max_connections": 300,
        "superuser_reserved_connections": 3,
        "reserved_connections": 2,
        "current_connections": 20,
        "observed_yfc_connections": 8,
        "observed_non_yfc_connections": 12,
        "unattributed_connections": 3,
    }
    assert len(cursor.queries) == 1
    sql = cursor.queries[0]
    assert sql.lstrip().startswith("SELECT")
    assert "FROM pg_stat_activity" in sql
    assert "pg_read_all_stats" in sql
    assert "application_name" in sql
    assert "INSERT " not in sql and "UPDATE " not in sql and "DELETE " not in sql
    assert calls[0][0] == "postgresql://test:secret@db/app"
    assert calls[0][1] == 5
    assert "default_transaction_read_only=on" in calls[0][2]
    assert "statement_timeout=5000" in calls[0][2]
    assert "lock_timeout=1000" in calls[0][2]
    assert "secret" not in json.dumps(data)
    assert "test@" not in json.dumps(data)


@pytest.mark.parametrize(
    "row",
    (
        (160000, 300, 3, 2, 20, 8, 3, 9, False, False),
        (160000, 300, 3, 2, 20, 8, 3, 9, True, True),
        (160000, 300, 3, None, 20, 8, 3, 9, True, False),
        (160000, 300, 3, 2, 19, 8, 3, 9, True, False),
        (160000, 300, 3, 2, 20, 8, 3, -1, True, False),
        (160000, 300, 3, 2, 20, 8, 3, 9, True, 0),
        (160000, 300, 3, 2, 20, True, 3, 9, True, False),
        (160000, 300, 3, 2, 20, 8, 3, 9),
    ),
)
def test_legacy_probe_refuses_privilege_and_data_ambiguity(monkeypatch, row) -> None:
    _fake_driver(monkeypatch, row)
    with pytest.raises((ValueError, TypeError)):
        legacy.collect()


def test_legacy_probe_accepts_pg15_absent_reserved_connections(monkeypatch) -> None:
    _fake_driver(monkeypatch, (150000, 300, 3, None, 20, 8, 3, 9, True, False))
    result = legacy.collect()
    assert result["postgres"]["reserved_connections"] is None
    assert result["postgres"]["server_version_major"] == 15


def test_legacy_probe_output_is_accepted_by_main_trusted_snapshot_parser(monkeypatch) -> None:
    from scripts.trusted_runtime_collector import (
        RuntimeContext,
        _parse_child_snapshot,
    )

    _fake_driver(monkeypatch, VALID_ROW)
    report = legacy.collect()
    observed = _parse_child_snapshot(
        report,
        RuntimeContext(
            environment="production",
            host_fingerprint="synthetic-host",
            revisions=("a" * 40,),
            captured_at=datetime.now(UTC),
        ),
    )
    assert observed.capacity.max_connections == 300
    assert observed.capacity.observed_non_yfc_connections == 12


def test_legacy_probe_cli_failure_never_prints_database_secrets(
    monkeypatch, capsys
) -> None:
    def refuse_connection(*_args, **_kwargs):
        raise RuntimeError("password=top-secret uri=postgresql://private")

    monkeypatch.setenv("DATABASE_URL", "postgresql://test:password-secret@db/app")
    monkeypatch.setitem(
        sys.modules, "psycopg", SimpleNamespace(connect=refuse_connection)
    )
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(Path(legacy.__file__)), run_name="__main__")
    assert raised.value.code == 1
    output = capsys.readouterr().out
    assert json.loads(output) == {"status": "BLOCKED"}
    assert "secret" not in output
    assert "postgresql://" not in output


def test_legacy_probe_without_database_url_is_blocked(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="missing PostgreSQL"):
        legacy.collect()
