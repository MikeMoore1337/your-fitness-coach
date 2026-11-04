import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from fitminiapp_api.db.session import engine as app_engine

CASES = [
    {
        "name": "0134-completion",
        "file": "0134_workout_completed_at_utc.py",
        "setup": (
            "CREATE TABLE user_workouts (id integer primary key, completed_at_utc timestamp)",
            "INSERT INTO user_workouts (id) VALUES (1)",
        ),
        "writer": "UPDATE user_workouts SET completed_at_utc='2026-01-01' WHERE id=1",
        "table": "user_workouts",
        "column": "completed_at_utc",
        "guard": "recorded UTC workout completion",
    },
    {
        "name": "0134-cycle",
        "file": "0134_program_cycle_storage.py",
        "setup": (
            "CREATE TABLE user_workout_sets (id integer primary key, plan_version integer)",
            "CREATE TABLE user_workouts (id integer primary key, source_cycle_week integer, "
            "cycle_iteration integer, plan_revision_number integer, plan_materialized boolean)",
            "CREATE INDEX uq_user_workouts_cycle_occurrence ON user_workouts (id)",
            "INSERT INTO user_workout_sets (id) VALUES (1)",
        ),
        "writer": "UPDATE user_workout_sets SET plan_version=1 WHERE id=1",
        "table": "user_workout_sets",
        "column": "plan_version",
        "guard": "cycle plan version lineage",
    },
    {
        "name": "0135-duration",
        "file": "0135_program_duration_unbounded.py",
        "setup": (
            "CREATE TABLE program_templates (id integer primary key, default_duration_weeks integer "
            "CONSTRAINT ck_program_templates_default_duration_weeks CHECK (default_duration_weeks >= 1))",
            "INSERT INTO program_templates VALUES (1, 1)",
        ),
        "writer": "UPDATE program_templates SET default_duration_weeks=25 WHERE id=1",
        "table": "program_templates",
        "column": "default_duration_weeks",
        "predicate": "default_duration_weeks=25",
        "guard": "exceeds 24",
    },
    {
        "name": "0140-start",
        "file": "0140_workout_start_utc.py",
        "setup": (
            "CREATE TABLE user_workouts (id integer primary key, started_at_utc timestamp)",
            "INSERT INTO user_workouts (id) VALUES (1)",
        ),
        "writer": "UPDATE user_workouts SET started_at_utc='2026-01-01' WHERE id=1",
        "table": "user_workouts",
        "column": "started_at_utc",
        "guard": "UTC workout start times",
    },
    {
        "name": "0142-history",
        "file": "0142_workout_history_import.py",
        "setup": (
            "CREATE TABLE imported_workouts (id integer primary key)",
            "CREATE TABLE workout_history_import_drafts (id integer primary key)",
        ),
        "writer": "INSERT INTO imported_workouts (id) VALUES (1)",
        "table": "imported_workouts",
        "column": "id",
        "guard": "imported workout history or drafts",
    },
    {
        "name": "0143-sides",
        "file": "0143_workout_set_sides.py",
        "setup": (
            "CREATE TABLE user_workout_sets (id integer primary key, execution_mode text, first_side text)",
            "CREATE TABLE user_workout_set_sides (id integer primary key)",
            "INSERT INTO user_workout_sets (id) VALUES (1)",
        ),
        "writer": "INSERT INTO user_workout_set_sides (id) VALUES (1)",
        "table": "user_workout_set_sides",
        "column": "id",
        "guard": "side-specific workout facts",
    },
    {
        "name": "0145-provenance",
        "file": "0145_history_provider_provenance.py",
        "setup": (
            "CREATE TABLE imported_workouts (id integer primary key, source_data text)",
            "CREATE TABLE user_workout_sets (id integer primary key, set_kind_known boolean)",
            "INSERT INTO imported_workouts (id) VALUES (1)",
        ),
        "writer": "UPDATE imported_workouts SET source_data='probe' WHERE id=1",
        "table": "imported_workouts",
        "column": "source_data",
        "guard": "imported provider provenance",
    },
    {
        "name": "0146-assignment",
        "file": "0146_assignment_exercise_slots.py",
        "setup": (
            "CREATE TABLE user_workout_exercises (id integer primary key, source_assignment_slot_id text)",
            "CREATE TABLE workout_exercise_notes (id integer primary key, source_assignment_slot_id text)",
            "CREATE TABLE program_revisions (changed_fields text, snapshot text)",
            "INSERT INTO user_workout_exercises (id) VALUES (1)",
        ),
        "writer": "UPDATE user_workout_exercises SET source_assignment_slot_id='probe' WHERE id=1",
        "table": "user_workout_exercises",
        "column": "source_assignment_slot_id",
        "guard": "assignment exercise identities",
    },
]

_BASE_CASES = {item["name"]: item for item in CASES}
CASES.extend(
    [
        {
            **_BASE_CASES["0134-cycle"],
            "name": "0134-cycle-workouts",
            "setup": (
                *_BASE_CASES["0134-cycle"]["setup"],
                "INSERT INTO user_workouts (id, plan_materialized) VALUES (1, TRUE)",
            ),
            "writer": "UPDATE user_workouts SET source_cycle_week=2 WHERE id=1",
            "table": "user_workouts",
            "column": "source_cycle_week",
            "guard": "cycle occurrence lineage",
        },
        {
            **_BASE_CASES["0142-history"],
            "name": "0142-history-draft",
            "writer": "INSERT INTO workout_history_import_drafts (id) VALUES (1)",
            "table": "workout_history_import_drafts",
        },
        {
            **_BASE_CASES["0143-sides"],
            "name": "0143-set-mode",
            "writer": "UPDATE user_workout_sets SET execution_mode='per_side' WHERE id=1",
            "table": "user_workout_sets",
            "column": "execution_mode",
        },
        {
            **_BASE_CASES["0145-provenance"],
            "name": "0145-set-kind",
            "setup": (
                *_BASE_CASES["0145-provenance"]["setup"],
                "INSERT INTO user_workout_sets (id) VALUES (1)",
            ),
            "writer": "UPDATE user_workout_sets SET set_kind_known=TRUE WHERE id=1",
            "table": "user_workout_sets",
            "column": "set_kind_known",
        },
        {
            **_BASE_CASES["0146-assignment"],
            "name": "0146-note-slot",
            "setup": (
                *_BASE_CASES["0146-assignment"]["setup"],
                "INSERT INTO workout_exercise_notes (id) VALUES (1)",
            ),
            "writer": "UPDATE workout_exercise_notes SET source_assignment_slot_id='probe' WHERE id=1",
            "table": "workout_exercise_notes",
        },
        {
            **_BASE_CASES["0146-assignment"],
            "name": "0146-revision-slot",
            "writer": 'INSERT INTO program_revisions (changed_fields) VALUES (\'{"source_assignment_slot_id":"probe"}\')',
            "table": "program_revisions",
            "column": "changed_fields",
        },
    ]
)


@pytest.fixture(params=CASES, ids=lambda item: item["name"])
def case(request):
    return request.param


def _migration(case, connection):
    path = Path(__file__).resolve().parents[1] / "alembic/versions" / case["file"]
    spec = importlib.util.spec_from_file_location("migration_" + uuid4().hex, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(connection))
    return module


def _setup(connection, case):
    for statement in case["setup"]:
        connection.exec_driver_sql(statement)


def _assert_written(connection, case):
    predicate = case.get("predicate", f"{case['column']} IS NOT NULL")
    assert (
        connection.exec_driver_sql(
            f"SELECT count(*) FROM {case['table']} WHERE {predicate}"
        ).scalar_one()
        == 1
    )


def test_sqlite_waits_for_writer_then_refuses_data_loss(case, tmp_path):
    engine = sa.create_engine(
        f"sqlite:///{(tmp_path / 'race.db').as_posix()}", connect_args={"timeout": 0.2}
    )
    try:
        with engine.begin() as connection:
            _setup(connection, case)
        with engine.connect() as writer:
            transaction = writer.begin()
            try:
                assert writer.exec_driver_sql(case["writer"]).rowcount == 1
                with engine.connect() as reader:
                    with pytest.raises(sa.exc.OperationalError, match="locked"):
                        _migration(case, reader).downgrade()
                    reader.rollback()
                transaction.commit()
            finally:
                if transaction.is_active:
                    transaction.rollback()
        with engine.connect() as reader:
            with pytest.raises(RuntimeError, match=case["guard"]):
                _migration(case, reader).downgrade()
            _assert_written(reader, case)
    finally:
        engine.dispose()


def test_sqlite_autocommit_fails_closed(case, tmp_path):
    engine = sa.create_engine(
        f"sqlite:///{(tmp_path / 'autocommit.db').as_posix()}", isolation_level="AUTOCOMMIT"
    )
    try:
        with engine.connect() as connection:
            _setup(connection, case)
            with pytest.raises(RuntimeError, match="requires a transaction"):
                _migration(case, connection).downgrade()
    finally:
        engine.dispose()


def test_sqlite_empty_safe_downgrade_completes(case, tmp_path):
    engine = sa.create_engine(f"sqlite:///{(tmp_path / 'empty.db').as_posix()}")
    try:
        with engine.begin() as connection:
            _setup(connection, case)
        with engine.begin() as connection:
            _migration(case, connection).downgrade()
    finally:
        engine.dispose()


def test_unsupported_dialect_fails_closed(case, tmp_path):
    engine = sa.create_engine(f"sqlite:///{(tmp_path / 'unsupported.db').as_posix()}")
    try:
        with engine.connect() as connection:
            migration = _migration(case, connection)
            migration.op.get_bind = lambda: SimpleNamespace(dialect=SimpleNamespace(name="unknown"))
            with pytest.raises(RuntimeError, match="locking is unsupported"):
                migration.downgrade()
    finally:
        engine.dispose()


@pytest.fixture
def postgres_schema(case):
    if app_engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL")
    schema = "v12_downgrade_" + uuid4().hex
    with app_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        _setup(connection, case)
    try:
        yield schema
    finally:
        with app_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


def test_postgres_waits_for_writer_then_refuses_data_loss(case, postgres_schema):
    schema = postgres_schema
    pids = Queue()
    with app_engine.connect() as writer:
        transaction = writer.begin()
        try:
            writer.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            assert writer.exec_driver_sql(case["writer"]).rowcount == 1

            def downgrade():
                with app_engine.connect() as reader:
                    reader.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                    pids.put(reader.exec_driver_sql("SELECT pg_backend_pid()").scalar_one())
                    try:
                        _migration(case, reader).downgrade()
                    finally:
                        reader.rollback()

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(downgrade)
                pid = pids.get(timeout=5)
                deadline = monotonic() + 2
                wait_type = None
                with app_engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as inspector:
                    while monotonic() < deadline:
                        wait_type = inspector.execute(
                            sa.text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                            {"pid": pid},
                        ).scalar_one_or_none()
                        if wait_type == "Lock":
                            break
                        sleep(0.05)
                assert wait_type == "Lock"
                transaction.commit()
                with pytest.raises(RuntimeError, match=case["guard"]):
                    future.result(timeout=5)
        finally:
            if transaction.is_active:
                transaction.rollback()
    with app_engine.begin() as connection:
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        _assert_written(connection, case)


def test_postgres_empty_safe_downgrade_completes(case, postgres_schema):
    with app_engine.begin() as connection:
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{postgres_schema}"')
        _migration(case, connection).downgrade()


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
def test_postgres_rejects_stale_snapshot(case, postgres_schema, isolation):
    schema = postgres_schema
    with app_engine.connect().execution_options(isolation_level=isolation) as reader:
        reader.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        reader.exec_driver_sql(f"SELECT count(*) FROM {case['table']}").scalar_one()
        with app_engine.begin() as writer:
            writer.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            assert writer.exec_driver_sql(case["writer"]).rowcount == 1
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            _migration(case, reader).downgrade()
        reader.rollback()
    with app_engine.begin() as connection:
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        _assert_written(connection, case)
