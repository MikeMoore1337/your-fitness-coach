import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_access_migration_preserves_existing_links_and_revocation(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0157_coach_nutrition_access.py"
    spec = importlib.util.spec_from_file_location("coach_nutrition_access_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{(tmp_path / 'access.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE coach_clients (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO coach_clients (id) VALUES (1)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert connection.execute(text("SELECT nutrition_access FROM coach_clients")).scalar() == 1
        connection.execute(text("UPDATE coach_clients SET nutrition_access = false"))
        with pytest.raises(RuntimeError, match="Cannot discard revoked nutrition access"):
            migration.downgrade()
        connection.execute(text("UPDATE coach_clients SET nutrition_access = NULL"))
        with pytest.raises(RuntimeError, match="Cannot discard revoked nutrition access"):
            migration.downgrade()
        connection.execute(text("UPDATE coach_clients SET nutrition_access = true"))
        migration.downgrade()
        assert connection.execute(text("SELECT id FROM coach_clients")).scalar() == 1
    engine.dispose()
