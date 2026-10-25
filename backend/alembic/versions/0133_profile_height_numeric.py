"""Preserve two-decimal anthropometric and workout values at restorable scale."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0133_profile_height_numeric"
down_revision: str | None = "0132_rest_interval_unique_swap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "numeric_precision"
online_rollout_notes = (
    "Bounded PostgreSQL widening for user-entered decimal values. Existing values with more "
    "than two fractional digits fail closed before conversion; profile height downgrade refuses "
    "fractional rows."
)

_UPGRADE_COLUMNS = (
    ("user_profiles", "height_cm", sa.Integer(), sa.Numeric(5, 2)),
    ("user_profiles", "weight_kg", sa.Float(), sa.Numeric(5, 2)),
    ("nutrition_targets", "weight_kg", sa.Float(), sa.Numeric(5, 2)),
    ("nutrition_targets", "height_cm", sa.Float(), sa.Numeric(5, 2)),
    ("body_measurements", "weight_kg", sa.Float(), sa.Numeric(5, 2)),
    ("body_measurements", "chest_cm", sa.Float(), sa.Numeric(6, 2)),
    ("body_measurements", "waist_cm", sa.Float(), sa.Numeric(6, 2)),
    ("body_measurements", "hips_cm", sa.Float(), sa.Numeric(6, 2)),
    ("body_measurements", "biceps_cm", sa.Float(), sa.Numeric(6, 2)),
    ("body_measurements", "thigh_cm", sa.Float(), sa.Numeric(6, 2)),
    ("body_measurement_custom_values", "value", sa.Float(), sa.Numeric(6, 2)),
    ("user_workout_sets", "actual_weight", sa.Float(), sa.Numeric(10, 2)),
    ("user_workout_sets", "distance_km", sa.Float(), sa.Numeric(7, 2)),
)


def _has_excess_precision(bind: sa.Connection, table: str, column: str) -> bool:
    if bind.dialect.name == "postgresql":
        expression = f"{column}::numeric <> round({column}::numeric, 2)"
    else:
        expression = f"{column} <> round({column}, 2)"
    return (
        bind.execute(
            sa.text(
                f"SELECT 1 FROM {table} WHERE {column} IS NOT NULL AND {expression} LIMIT 1"
            )
        ).first()
        is not None
    )


def _ensure_upgrade_safe(bind: sa.Connection) -> None:
    for table, column, _existing_type, _new_type in _UPGRADE_COLUMNS:
        if _has_excess_precision(bind, table, column):
            raise RuntimeError(
                f"Unsafe numeric precision migration: {table}.{column} contains more than "
                "two fractional digits; remediate the data before applying 0133"
            )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_upgrade_safe(bind)
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE user_profiles ALTER COLUMN height_cm TYPE NUMERIC(5,2) "
            "USING height_cm::numeric(5,2)"
        )
        op.execute(
            "ALTER TABLE user_profiles ALTER COLUMN weight_kg TYPE NUMERIC(5,2) "
            "USING weight_kg::numeric(5,2)"
        )
        op.execute(
            "ALTER TABLE nutrition_targets ALTER COLUMN weight_kg TYPE NUMERIC(5,2) "
            "USING weight_kg::numeric(5,2)"
        )
        op.execute(
            "ALTER TABLE nutrition_targets ALTER COLUMN height_cm TYPE NUMERIC(5,2) "
            "USING height_cm::numeric(5,2)"
        )
        op.execute(
            "ALTER TABLE body_measurements ALTER COLUMN weight_kg TYPE NUMERIC(5,2) "
            "USING weight_kg::numeric(5,2)"
        )
        op.execute(
            "ALTER TABLE body_measurements ALTER COLUMN chest_cm TYPE NUMERIC(6,2) "
            "USING chest_cm::numeric(6,2)"
        )
        op.execute(
            "ALTER TABLE body_measurements ALTER COLUMN waist_cm TYPE NUMERIC(6,2) "
            "USING waist_cm::numeric(6,2)"
        )
        op.execute(
            "ALTER TABLE body_measurements ALTER COLUMN hips_cm TYPE NUMERIC(6,2) "
            "USING hips_cm::numeric(6,2)"
        )
        op.execute(
            "ALTER TABLE body_measurements ALTER COLUMN biceps_cm TYPE NUMERIC(6,2) "
            "USING biceps_cm::numeric(6,2)"
        )
        op.execute(
            "ALTER TABLE body_measurements ALTER COLUMN thigh_cm TYPE NUMERIC(6,2) "
            "USING thigh_cm::numeric(6,2)"
        )
        op.execute(
            "ALTER TABLE body_measurement_custom_values ALTER COLUMN value TYPE NUMERIC(6,2) "
            "USING value::numeric(6,2)"
        )
        op.execute(
            "ALTER TABLE user_workout_sets ALTER COLUMN actual_weight TYPE NUMERIC(10,2) "
            "USING actual_weight::numeric(10,2)"
        )
        op.execute(
            "ALTER TABLE user_workout_sets ALTER COLUMN distance_km TYPE NUMERIC(7,2) "
            "USING distance_km::numeric(7,2)"
        )
        return

    for table, column, existing_type, new_type in _UPGRADE_COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=existing_type,
                type_=new_type,
                existing_nullable=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        fractional_query = (
            "SELECT 1 FROM user_profiles "
            "WHERE height_cm IS NOT NULL AND height_cm <> trunc(height_cm) LIMIT 1"
        )
    else:
        fractional_query = (
            "SELECT 1 FROM user_profiles "
            "WHERE height_cm IS NOT NULL AND height_cm <> CAST(height_cm AS INTEGER) LIMIT 1"
        )
    if bind.execute(sa.text(fractional_query)).first() is not None:
        raise RuntimeError(
            "Unsafe downgrade: fractional profile heights exist; preserve 0133 or migrate them first"
        )

    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        for table, column, _existing_type, _new_type in reversed(_UPGRADE_COLUMNS):
            old_type = (
                "INTEGER" if table == "user_profiles" and column == "height_cm" else "DOUBLE PRECISION"
            )
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {old_type} "
                f"USING {column}::{old_type}"
            )
        return

    for table, column, _existing_type, new_type in reversed(_UPGRADE_COLUMNS):
        old_type = sa.Integer() if table == "user_profiles" and column == "height_cm" else sa.Float()
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=new_type,
                type_=old_type,
                existing_nullable=True,
            )
