"""Allow imported facts while retaining the existing planned-workout invariants."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0141_workout_history_nullable"
down_revision: str | None = "0140_workout_start_utc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "workout_history_nullable"
online_rollout_notes = "Relax only the stated plan columns under bounded PostgreSQL locks."


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE user_workouts ADD COLUMN history_imported BOOLEAN, ALTER COLUMN user_program_id DROP NOT NULL, ALTER COLUMN day_number DROP NOT NULL, ALTER COLUMN week_number DROP NOT NULL, ADD CONSTRAINT ck_user_workouts_plan_presence CHECK ((history_imported IS TRUE AND user_program_id IS NULL AND day_number IS NULL AND week_number IS NULL AND status = 'completed') OR (history_imported IS NOT TRUE AND user_program_id IS NOT NULL AND day_number IS NOT NULL AND week_number IS NOT NULL)) NOT VALID"
        )
        op.execute(
            "ALTER TABLE user_workout_exercises ADD COLUMN history_imported BOOLEAN, ALTER COLUMN prescribed_sets DROP NOT NULL, ALTER COLUMN prescribed_reps DROP NOT NULL, ALTER COLUMN rest_seconds DROP NOT NULL, ADD CONSTRAINT ck_user_workout_exercises_plan_presence CHECK ((history_imported IS TRUE AND prescribed_sets IS NULL AND prescribed_reps IS NULL AND rest_seconds IS NULL) OR (history_imported IS NOT TRUE AND prescribed_sets IS NOT NULL AND prescribed_reps IS NOT NULL AND rest_seconds IS NOT NULL)) NOT VALID"
        )
        op.execute("ALTER TABLE user_workouts VALIDATE CONSTRAINT ck_user_workouts_plan_presence")
        op.execute(
            "ALTER TABLE user_workout_exercises VALIDATE CONSTRAINT ck_user_workout_exercises_plan_presence"
        )
    else:
        if (
            bind.execute(sa.text("PRAGMA foreign_keys")).scalar_one()
            and bind.execute(sa.text("SELECT 1 FROM user_workouts LIMIT 1")).first()
        ):
            raise RuntimeError("SQLite migration requires a connection with foreign keys disabled")
        with op.batch_alter_table("user_workouts") as batch:
            batch.add_column(sa.Column("history_imported", sa.Boolean(), nullable=True))
            batch.alter_column("user_program_id", existing_type=sa.Integer(), nullable=True)
            batch.alter_column("day_number", existing_type=sa.Integer(), nullable=True)
            batch.alter_column("week_number", existing_type=sa.Integer(), nullable=True)
            batch.create_check_constraint(
                "ck_user_workouts_plan_presence",
                "(history_imported IS TRUE AND user_program_id IS NULL AND day_number IS NULL AND week_number IS NULL AND status = 'completed') OR (history_imported IS NOT TRUE AND user_program_id IS NOT NULL AND day_number IS NOT NULL AND week_number IS NOT NULL)",
            )
        with op.batch_alter_table("user_workout_exercises") as batch:
            batch.add_column(sa.Column("history_imported", sa.Boolean(), nullable=True))
            batch.alter_column("prescribed_sets", existing_type=sa.Integer(), nullable=True)
            batch.alter_column("prescribed_reps", existing_type=sa.String(32), nullable=True)
            batch.alter_column("rest_seconds", existing_type=sa.Integer(), nullable=True)
            batch.create_check_constraint(
                "ck_user_workout_exercises_plan_presence",
                "(history_imported IS TRUE AND prescribed_sets IS NULL AND prescribed_reps IS NULL AND rest_seconds IS NULL) OR (history_imported IS NOT TRUE AND prescribed_sets IS NOT NULL AND prescribed_reps IS NOT NULL AND rest_seconds IS NOT NULL)",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute("LOCK TABLE user_workouts, user_workout_exercises IN ACCESS EXCLUSIVE MODE")
    elif (
        bind.execute(sa.text("PRAGMA foreign_keys")).scalar_one()
        and bind.execute(sa.text("SELECT 1 FROM user_workouts LIMIT 1")).first()
    ):
        raise RuntimeError("SQLite migration requires a connection with foreign keys disabled")
    if (
        bind.execute(
            sa.text(
                "SELECT 1 FROM user_workouts WHERE user_program_id IS NULL OR day_number IS NULL OR week_number IS NULL LIMIT 1"
            )
        ).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM user_workout_exercises WHERE prescribed_sets IS NULL OR prescribed_reps IS NULL OR rest_seconds IS NULL LIMIT 1"
            )
        ).first()
    ):
        raise RuntimeError("Unsafe downgrade: workouts without program or prescription exist")
    with op.batch_alter_table("user_workout_exercises") as batch:
        batch.drop_constraint("ck_user_workout_exercises_plan_presence", type_="check")
        batch.alter_column("prescribed_sets", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("prescribed_reps", existing_type=sa.String(32), nullable=False)
        batch.alter_column("rest_seconds", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("history_imported")
    with op.batch_alter_table("user_workouts") as batch:
        batch.drop_constraint("ck_user_workouts_plan_presence", type_="check")
        batch.alter_column("user_program_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("day_number", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("week_number", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("history_imported")
