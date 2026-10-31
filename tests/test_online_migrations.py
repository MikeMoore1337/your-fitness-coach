import json
from pathlib import Path

import pytest
from scripts.check_online_migrations import (
    OnlineMigrationError,
    changed_migrations_from_manifest,
    validate_added_migration,
    validate_legacy_migration_compatibility,
)


def _migration(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_production_migration_manifest_is_revision_bound(tmp_path: Path) -> None:
    manifest = tmp_path / "deployment-migration-manifest.json"
    active = "a" * 40
    target = "b" * 40
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "active_revision": active,
                "target_revision": target,
                "changes": [{"status": "A", "path": "backend/alembic/versions/0064_expand.py"}],
            }
        ),
        encoding="utf-8",
    )

    assert changed_migrations_from_manifest(active, target, manifest) == [
        ("A", Path("backend/alembic/versions/0064_expand.py"))
    ]
    with pytest.raises(OnlineMigrationError, match="revision range"):
        changed_migrations_from_manifest(active, "c" * 40, manifest)


def test_merged_measurement_migration_uses_exact_legacy_compatibility() -> None:
    assert validate_legacy_migration_compatibility(
        Path("backend/alembic/versions/0118_measurement_eligibility.py")
    )
    assert not validate_legacy_migration_compatibility(
        Path("backend/alembic/versions/0117_progress_weekly_action_constraint.py")
    )


def test_online_migration_accepts_declared_additive_expand(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0064_expand.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "Nullable additive column; metadata-only lock."\n\n'
        "def upgrade():\n"
        '    op.add_column("users", sa.Column("nickname", sa.String(), nullable=True))\n'
        '\ndef downgrade():\n    op.drop_column("users", "nickname")\n',
    )

    validate_added_migration(path)


def test_online_migration_accepts_empty_table_and_its_index(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0065_empty_table.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "Creates one empty table and indexes only that table."\n\n'
        "def upgrade():\n"
        '    op.create_table("events", sa.Column("id", sa.Integer(), primary_key=True), '
        'sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), '
        'sa.CheckConstraint("user_id > 0", name="ck_events_user"))\n'
        '    op.create_index("ix_events_user", "events", ["user_id"])\n',
    )

    validate_added_migration(path)


def test_contextual_reminder_migrations_satisfy_production_online_contract() -> None:
    root = Path(__file__).resolve().parents[1]

    validate_added_migration(
        root / "backend" / "alembic" / "versions" / "0074_contextual_reminder_templates.py"
    )


def test_nutrition_label_migration_satisfies_production_online_contract() -> None:
    root = Path(__file__).resolve().parents[1]

    for name in (
        "0081_nutrition_label_canonical_catalog.py",
        "0082_basis_aware_food_diary.py",
        "0083_nutrition_label_food_backfill.py",
        "0084_nutrition_label_diary_backfill.py",
    ):
        validate_added_migration(root / "backend" / "alembic" / "versions" / name)


@pytest.mark.parametrize(
    "name",
    [
        "0098_program_lifecycle.py",
        "0099_user_program_status_ck.py",
        "0100_program_revision_kind_ck.py",
    ],
)
def test_program_lifecycle_migrations_satisfy_production_online_contract(name: str) -> None:
    root = Path(__file__).resolve().parents[1]

    validate_added_migration(root / "backend" / "alembic" / "versions" / name)


def test_first_touch_attribution_migration_satisfies_production_online_contract() -> None:
    root = Path(__file__).resolve().parents[1]

    validate_added_migration(
        root / "backend" / "alembic" / "versions" / "0085_first_touch_attribution.py"
    )


def test_ai_coach_conversations_migration_satisfies_production_online_contract() -> None:
    root = Path(__file__).resolve().parents[1]

    validate_added_migration(
        root / "backend" / "alembic" / "versions" / "0086_ai_coach_conversations.py"
    )


def test_ai_coach_quota_migration_satisfies_production_online_contract() -> None:
    root = Path(__file__).resolve().parents[1]

    validate_added_migration(
        root / "backend" / "alembic" / "versions" / "0088_ai_coach_durable_quota.py"
    )


def test_coach_crm_migration_satisfies_production_online_contract() -> None:
    root = Path(__file__).resolve().parents[1]

    validate_added_migration(root / "backend" / "alembic" / "versions" / "0092_coach_crm_core.py")


@pytest.mark.parametrize(
    "name",
    [
        "0108_trainer_workspace_reviews.py",
        "0109_coach_task_kind_backfill.py",
        "0110_coach_task_kind_constraint.py",
        "0111_coach_task_source_kind_constraint.py",
    ],
)
def test_trainer_workspace_migrations_satisfy_production_online_contract(name: str) -> None:
    root = Path(__file__).resolve().parents[1]

    validate_added_migration(root / "backend" / "alembic" / "versions" / name)


def test_online_migration_rejects_index_on_existing_table(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0065_existing_index.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "Index would target an existing populated table."\n\n'
        "def upgrade():\n"
        '    op.create_index("ix_users_name", "users", ["name"])\n',
    )

    with pytest.raises(OnlineMigrationError, match="new empty table"):
        validate_added_migration(path)


def test_online_migration_accepts_concurrent_index_on_existing_table(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0065_existing_concurrent_index.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "Concurrent index build avoids a table-wide write lock."\n\n'
        "def upgrade():\n"
        "    bind = op.get_bind()\n"
        '    if bind.dialect.name == "postgresql":\n'
        "        with op.get_context().autocommit_block():\n"
        '            op.create_index("ix_users_name", "users", ["name"], '
        "postgresql_concurrently=True, if_not_exists=True)\n"
        "    else:\n"
        '        op.create_index("ix_users_name", "users", ["name"], '
        "postgresql_concurrently=True, if_not_exists=True)\n",
    )

    validate_added_migration(path)


@pytest.mark.parametrize(
    "kind", ["valid", "write", "other_index", "other_query", "non_pg", "dynamic"]
)
def test_concurrent_index_allows_only_exact_catalog_validation(tmp_path: Path, kind: str) -> None:
    query = "SELECT indisvalid AND indisunique FROM pg_index WHERE indexrelid = 'ix_users_name'::regclass"
    if kind == "write":
        query += "; DELETE FROM users"
    elif kind == "other_index":
        query = query.replace("ix_users_name", "another_index")
    elif kind == "other_query":
        query = "SELECT * FROM users"
    expression = "query" if kind == "dynamic" else repr(query)
    dialect = "sqlite" if kind == "non_pg" else "postgresql"
    path = _migration(
        tmp_path / "0065_index_validation.py",
        'online_rollout_phase = "expand"\nonline_rollout_notes = "Validate the concurrent index."\n'
        "def upgrade():\n"
        "    bind = op.get_bind()\n"
        f'    if bind.dialect.name == "{dialect}":\n'
        "        with op.get_context().autocommit_block():\n"
        '            op.create_index("ix_users_name", "users", ["name"], postgresql_concurrently=True, if_not_exists=True)\n'
        f"            bind.execute(sa.text({expression})).scalar_one()\n",
    )
    if kind != "valid":
        with pytest.raises(OnlineMigrationError, match="SQL execution outside"):
            validate_added_migration(path)
    else:
        validate_added_migration(path)


@pytest.mark.parametrize("operation", ["drop_table", "drop_column", "alter_column"])
def test_online_migration_rejects_destructive_contract_operation(
    tmp_path: Path, operation: str
) -> None:
    path = _migration(
        tmp_path / "0064_contract.py",
        f'online_rollout_phase = "expand"\n'
        f'online_rollout_notes = "reviewed"\n\ndef upgrade():\n    op.{operation}("users")\n',
    )

    with pytest.raises(OnlineMigrationError, match="destructive operations"):
        validate_added_migration(path)


def test_online_backfill_requires_bounded_idempotency_notes(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0064_backfill.py",
        'online_rollout_phase = "backfill"\n\ndef upgrade():\n    op.execute("UPDATE users")\n',
    )

    with pytest.raises(OnlineMigrationError, match="online_rollout_notes"):
        validate_added_migration(path)


def test_online_backfill_rejects_destructive_sql(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0064_backfill.py",
        'online_rollout_phase = "backfill"\n'
        'online_rollout_notes = "bounded by primary key batches"\n\n'
        "online_rollout_batch_size = 1000\n"
        "online_rollout_idempotent = True\n\n"
        'def upgrade():\n    op.execute("DELETE FROM users")\n',
    )

    with pytest.raises(OnlineMigrationError, match="destructive SQL"):
        validate_added_migration(path)


def test_online_backfill_accepts_explicit_bounded_idempotent_update(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0064_backfill.py",
        'online_rollout_phase = "backfill"\n'
        'online_rollout_notes = "bounded deterministic update by primary key window"\n'
        "online_rollout_batch_size = 1000\n"
        "online_rollout_idempotent = True\n\n"
        "def upgrade():\n"
        '    op.execute("UPDATE users SET normalized = TRUE WHERE id >= 1 AND id < 1001")\n',
    )

    validate_added_migration(path)


def test_online_backfill_rejects_unbounded_update(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0064_backfill.py",
        'online_rollout_phase = "backfill"\n'
        'online_rollout_notes = "claimed bounded update"\n'
        "online_rollout_batch_size = 1000\n"
        "online_rollout_idempotent = True\n\n"
        'def upgrade():\n    op.execute("UPDATE users SET normalized = TRUE")\n',
    )

    with pytest.raises(OnlineMigrationError, match="bounded UPDATE"):
        validate_added_migration(path)


@pytest.mark.parametrize("method", ["execute", "exec_driver_sql"])
def test_online_migration_rejects_sql_execution_outside_op_contract(
    tmp_path: Path, method: str
) -> None:
    path = _migration(
        tmp_path / "0064_raw_connection.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "reviewed"\n\n'
        "def upgrade():\n"
        "    connection = context.get_bind()\n"
        f'    connection.{method}(sa.text("DROP TABLE users"))\n',
    )

    with pytest.raises(OnlineMigrationError, match=r"outside the verified op\.execute"):
        validate_added_migration(path)


def test_online_migration_rejects_destructive_top_level_helper(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0064_helper.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "reviewed"\n\n'
        'def destroy():\n    op.drop_table("users")\n\n'
        "def upgrade():\n    destroy()\n",
    )

    with pytest.raises(OnlineMigrationError, match="outside the 'expand' online allowlist"):
        validate_added_migration(path)


@pytest.mark.parametrize(
    "operation",
    [
        'op.create_index("ix_users_email", "users", ["email"])',
        'op.create_unique_constraint("uq_users_email", "users", ["email"])',
        'op.create_foreign_key("fk_users_team", "users", "teams", ["team_id"], ["id"])',
    ],
)
def test_online_expand_rejects_lock_prone_operations(tmp_path: Path, operation: str) -> None:
    path = _migration(
        tmp_path / "0064_locking.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "reviewed"\n\n'
        f"def upgrade():\n    {operation}\n",
    )

    with pytest.raises(OnlineMigrationError, match="lock-prone operations"):
        validate_added_migration(path)


@pytest.mark.parametrize(
    "column",
    [
        'sa.Column("nickname", sa.String(), nullable=False)',
        'sa.Column("nickname", sa.String(), nullable=True, server_default="")',
        'sa.Column("nickname", sa.String(), nullable=True, server_default=sa.text("TRUE"))',
        'sa.Column("nickname", sa.String(), nullable=True, unique=True)',
        'sa.Column("nickname", sa.String(), nullable=True, index=True)',
    ],
)
def test_online_expand_rejects_rewrite_or_constraint_add_column(
    tmp_path: Path, column: str
) -> None:
    path = _migration(
        tmp_path / "0064_unsafe_column.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "reviewed"\n\n'
        f'def upgrade():\n    op.add_column("users", {column})\n',
    )

    with pytest.raises(OnlineMigrationError, match="add_column"):
        validate_added_migration(path)


def test_online_expand_accepts_only_constant_false_server_default(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0064_safe_default.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "constant false compatibility default"\n\n'
        "def upgrade():\n"
        '    op.add_column("users", sa.Column("enabled", sa.Boolean(), nullable=True, '
        'server_default=sa.text("FALSE")))\n',
    )

    validate_added_migration(path)


def test_online_expand_rejects_positional_foreign_key_in_add_column(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0064_foreign_key.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "reviewed"\n\n'
        "def upgrade():\n"
        '    op.add_column("users", sa.Column("team_id", sa.Integer(), '
        'sa.ForeignKey("teams.id"), nullable=True))\n',
    )

    with pytest.raises(OnlineMigrationError, match="positional constraints"):
        validate_added_migration(path)


def test_online_expand_rejects_two_argument_foreign_key_column(tmp_path: Path) -> None:
    path = _migration(
        tmp_path / "0064_foreign_key_only.py",
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "reviewed"\n\n'
        "def upgrade():\n"
        '    op.add_column("users", sa.Column("team_id", '
        'sa.ForeignKey("teams.id"), nullable=True))\n',
    )

    with pytest.raises(OnlineMigrationError, match="allowlisted static SQLAlchemy scalar type"):
        validate_added_migration(path)


def test_online_constraint_swap_accepts_bounded_not_valid_check_replacement(
    tmp_path: Path,
) -> None:
    path = _migration(
        tmp_path / "0096_constraint_swap.py",
        'online_rollout_phase = "constraint_swap"\n'
        'online_rollout_notes = "bounded CHECK replacement"\n'
        'online_rollout_constraint_table = "foods"\n'
        'online_rollout_constraint_name = "ck_foods_active_catalog_trust"\n'
        "online_rollout_lock_timeout_seconds = 3\n"
        "online_rollout_statement_timeout_seconds = 30\n\n"
        "def upgrade():\n"
        "    bind = op.get_bind()\n"
        '    if bind.dialect.name == "postgresql":\n'
        "        op.execute(\"SET LOCAL lock_timeout = '3s'\")\n"
        "        op.execute(\"SET LOCAL statement_timeout = '30s'\")\n"
        '        op.execute("ALTER TABLE foods DROP CONSTRAINT IF EXISTS '
        "ck_foods_active_catalog_trust, ADD CONSTRAINT "
        "ck_foods_active_catalog_trust CHECK (food_type = 'user' OR "
        "catalog_quality = 'community_unverified') NOT VALID\")\n"
        '        op.execute("ALTER TABLE foods VALIDATE CONSTRAINT '
        'ck_foods_active_catalog_trust")\n',
    )

    validate_added_migration(path)


def test_online_constraint_swap_rejects_unbounded_validating_replacement(
    tmp_path: Path,
) -> None:
    path = _migration(
        tmp_path / "0096_constraint_swap.py",
        'online_rollout_phase = "constraint_swap"\n'
        'online_rollout_notes = "unsafe CHECK replacement"\n'
        'online_rollout_constraint_table = "foods"\n'
        'online_rollout_constraint_name = "ck_foods_active_catalog_trust"\n'
        "online_rollout_lock_timeout_seconds = 3\n"
        "online_rollout_statement_timeout_seconds = 30\n\n"
        "def upgrade():\n"
        "    bind = op.get_bind()\n"
        '    if bind.dialect.name == "postgresql":\n'
        "        op.execute(\"SET LOCAL lock_timeout = '3s'\")\n"
        "        op.execute(\"SET LOCAL statement_timeout = '30s'\")\n"
        '        op.execute("ALTER TABLE foods DROP CONSTRAINT IF EXISTS '
        "ck_foods_active_catalog_trust, ADD CONSTRAINT "
        "ck_foods_active_catalog_trust CHECK (food_type = 'user')\")\n"
        '        op.execute("ALTER TABLE foods VALIDATE CONSTRAINT '
        'ck_foods_active_catalog_trust")\n',
    )

    with pytest.raises(OnlineMigrationError, match="NOT VALID"):
        validate_added_migration(path)


def test_side_metadata_migrations_allow_only_read_only_sqlite_foreign_key_guard(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1] / "backend" / "alembic" / "versions"
    validate_added_migration(root / "0143_workout_set_sides.py")
    source = (root / "0144_workout_side_metadata_ck.py").read_text(encoding="utf-8")
    validate_added_migration(_migration(tmp_path / "0144_safe.py", source))
    for unsafe in (
        source.replace(".getconfig(", ".setconfig("),
        source.replace("SQLITE_DBCONFIG_ENABLE_FKEY", "SQLITE_DBCONFIG_ENABLE_TRIGGER"),
        source.replace(
            'raise RuntimeError("SQLite migration requires a connection with foreign keys disabled")',
            "pass",
        ),
    ):
        with pytest.raises(
            OnlineMigrationError, match="outside the 'constraint_swap' online allowlist"
        ):
            validate_added_migration(_migration(tmp_path / "0144_unsafe.py", unsafe))


def test_rest_interval_migrations_use_strict_online_contract() -> None:
    root = Path(__file__).resolve().parents[1] / "backend" / "alembic" / "versions"
    validate_added_migration(root / "0131_rest_interval_expand.py")
    validate_added_migration(root / "0132_rest_interval_unique_swap.py")


@pytest.mark.parametrize(
    "old,new",
    [
        ("SET LOCAL lock_timeout = '3s'", "SET LOCAL lock_timeout = '30s'"),
        (
            "DROP CONSTRAINT uq_workout_rest_source_set",
            "DROP CONSTRAINT uq_workout_rest_running_workout",
        ),
        ('type_="unique"', 'type_="foreignkey"'),
        (
            'op.batch_alter_table("workout_rest_sessions")',
            'op.batch_alter_table("users")',
        ),
    ],
)
def test_rest_unique_swap_rejects_modified_scope(tmp_path: Path, old: str, new: str) -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "alembic"
        / "versions"
        / "0132_rest_interval_unique_swap.py"
    )
    source = path.read_text(encoding="utf-8")
    assert old in source
    candidate = _migration(tmp_path / path.name, source.replace(old, new, 1))
    with pytest.raises(OnlineMigrationError, match="rest unique"):
        validate_added_migration(candidate)


def test_rest_unique_swap_rejects_undeclared_migration_name(tmp_path: Path) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "alembic"
        / "versions"
        / "0132_rest_interval_unique_swap.py"
    ).read_text(encoding="utf-8")
    with pytest.raises(OnlineMigrationError, match="unapproved"):
        validate_added_migration(_migration(tmp_path / "9999_unrelated_unique_swap.py", source))


def test_cycle_storage_migrations_use_declared_online_operations():
    import runpy
    from pathlib import Path

    checker = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts" / "check_online_migrations.py")
    )
    for filename in (
        "0134_program_cycle_storage.py",
        "0135_program_duration_unbounded.py",
        "0136_program_week_unbounded.py",
    ):
        checker["validate_added_migration"](
            Path(__file__).resolve().parents[1] / "backend" / "alembic" / "versions" / filename
        )


@pytest.mark.parametrize(
    "old,new",
    [
        (
            'batch_alter_table("program_template_exercise_weeks")',
            'batch_alter_table("user_workouts")',
        ),
        (
            'batch.drop_constraint("ck_program_template_exercise_weeks_number", type_="check")',
            'batch.drop_constraint("other", type_="check")',
        ),
        (
            'batch.drop_constraint("ck_program_template_exercise_weeks_number", type_="check")',
            'batch.drop_constraint("ck_program_template_exercise_weeks_number", type_="unique")',
        ),
        ('"week_number >= 1"', '"week_number >= 0"'),
        (
            'batch.drop_constraint("ck_program_template_exercise_weeks_number", type_="check")',
            'batch.drop_column("week_number")',
        ),
    ],
)
def test_sqlite_check_swap_rejects_undeclared_or_mismatching_operations(tmp_path, old, new):
    import runpy
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    checker = runpy.run_path(str(root / "scripts" / "check_online_migrations.py"))
    source = (
        root / "backend" / "alembic" / "versions" / "0136_program_week_unbounded.py"
    ).read_text(encoding="utf-8")
    assert old in source
    invalid = tmp_path / "invalid.py"
    invalid.write_text(source.replace(old, new), encoding="utf-8")
    with pytest.raises(checker["OnlineMigrationError"]):
        checker["validate_added_migration"](invalid)


def test_workout_history_nullable_migration_has_exact_bounded_scope():
    path = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "alembic"
        / "versions"
        / "0141_workout_history_nullable.py"
    )
    validate_added_migration(path)


@pytest.mark.parametrize(
    "old,new",
    [
        ("SET LOCAL lock_timeout = '3s'", "SET LOCAL lock_timeout = '30s'"),
        ("user_program_id DROP NOT NULL", "user_program_id DROP DEFAULT"),
        ("AND status = 'completed'", "AND status = 'planned'"),
        (
            "VALIDATE CONSTRAINT ck_user_workouts_plan_presence",
            "DROP CONSTRAINT ck_user_workouts_plan_presence",
        ),
        ('batch.alter_column("rest_seconds"', 'batch.alter_column("exercise_id"'),
        ("nullable=True)", "nullable=False)"),
        ("import sqlalchemy as sa", "import sqlite3 as sa"),
        ("def downgrade() -> None:", 'def downgrade(value=print("bad")) -> None:'),
    ],
)
def test_workout_history_nullable_rejects_scope_changes(tmp_path: Path, old: str, new: str):
    source_path = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "alembic"
        / "versions"
        / "0141_workout_history_nullable.py"
    )
    source = source_path.read_text(encoding="utf-8")
    assert old in source
    with pytest.raises(OnlineMigrationError, match="workout history nullable"):
        validate_added_migration(
            _migration(tmp_path / source_path.name, source.replace(old, new, 1))
        )


def test_workout_history_nullable_rejects_other_revision(tmp_path: Path):
    source_path = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "alembic"
        / "versions"
        / "0141_workout_history_nullable.py"
    )
    with pytest.raises(OnlineMigrationError, match="unapproved"):
        validate_added_migration(
            _migration(tmp_path / "9999_other.py", source_path.read_text(encoding="utf-8"))
        )
