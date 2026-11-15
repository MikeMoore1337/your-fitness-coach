import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from fitminiapp_api.db.session import engine


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL")
def test_migration_preserves_diary_history_and_refuses_to_drop_notes():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0159_nutrition_meal_notes.py"
    spec = importlib.util.spec_from_file_location("notes_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    schema = f"notes_test_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE food_diary_entries (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO users VALUES (1)"))
            connection.execute(text("INSERT INTO food_diary_entries VALUES (42)"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            connection.execute(
                text(
                    "INSERT INTO nutrition_meal_notes "
                    "(user_id, local_date, meal_type, timezone_at_entry, hunger_before, created_at, updated_at) "
                    "VALUES (1, '2026-01-01', 'breakfast', 'Europe/Moscow', 'none', now(), now())"
                )
            )
            with pytest.raises(RuntimeError, match="Cannot discard"):
                migration.downgrade()
            connection.execute(text("DELETE FROM nutrition_meal_notes"))
            migration.downgrade()
            assert connection.execute(text("SELECT id FROM food_diary_entries")).scalar_one() == 42
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
