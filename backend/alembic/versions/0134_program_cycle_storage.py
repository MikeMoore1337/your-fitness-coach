"""Expand nullable workout plan lineage without rewriting legacy training facts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0134_program_cycle_storage"
down_revision: str | None = "0133_profile_height_numeric"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = (
    "Nullable lineage and materialization marker: legacy NULL means fully materialized. "
    "The opt-in occurrence index is built concurrently and does not constrain legacy rows."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column(
            "user_workout_sets",
            sa.Column("plan_version", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("plan_materialized", sa.Boolean(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("source_cycle_week", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("cycle_iteration", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("plan_revision_number", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        with op.get_context().autocommit_block():
            op.create_index(
                "uq_user_workouts_cycle_occurrence",
                "user_workouts",
                ["user_program_id", "week_number", "day_number"],
                unique=True,
                postgresql_where=sa.text("source_cycle_week IS NOT NULL"),
                postgresql_concurrently=True,
                if_not_exists=True,
            )
            valid = bind.execute(
                sa.text(
                    "SELECT indisvalid AND indisunique FROM pg_index WHERE indexrelid = "
                    "'uq_user_workouts_cycle_occurrence'::regclass"
                )
            ).scalar_one()
            if not valid:
                raise RuntimeError(
                    "Incomplete cycle occurrence index; repair it before retrying migration"
                )
    else:
        op.add_column("user_workout_sets", sa.Column("plan_version", sa.Integer(), nullable=True))
        op.add_column("user_workouts", sa.Column("plan_materialized", sa.Boolean(), nullable=True))
        op.add_column("user_workouts", sa.Column("source_cycle_week", sa.Integer(), nullable=True))
        op.add_column("user_workouts", sa.Column("cycle_iteration", sa.Integer(), nullable=True))
        op.add_column(
            "user_workouts", sa.Column("plan_revision_number", sa.Integer(), nullable=True)
        )
        op.create_index(
            "uq_user_workouts_cycle_occurrence",
            "user_workouts",
            ["user_program_id", "week_number", "day_number"],
            unique=True,
            sqlite_where=sa.text("source_cycle_week IS NOT NULL"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if (
        bind.execute(
            sa.text("SELECT 1 FROM user_workout_sets WHERE plan_version IS NOT NULL LIMIT 1")
        ).first()
        is not None
    ):
        raise RuntimeError("Unsafe downgrade: cycle plan version lineage exists; use forward-fix")
    if (
        bind.execute(
            sa.text(
                "SELECT 1 FROM user_workouts WHERE source_cycle_week IS NOT NULL "
                "OR cycle_iteration IS NOT NULL OR plan_revision_number IS NOT NULL "
                "OR plan_materialized IS FALSE LIMIT 1"
            )
        ).first()
        is not None
    ):
        raise RuntimeError("Unsafe downgrade: cycle occurrence lineage exists; use forward-fix")
    op.drop_index("uq_user_workouts_cycle_occurrence", table_name="user_workouts")
    op.drop_column("user_workouts", "plan_revision_number")
    op.drop_column("user_workouts", "cycle_iteration")
    op.drop_column("user_workouts", "source_cycle_week")
    op.drop_column("user_workouts", "plan_materialized")
    op.drop_column("user_workout_sets", "plan_version")
