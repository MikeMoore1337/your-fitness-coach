"""Expand opt-in rotation without changing calendar indexes or workout facts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0147_session_rotation"
down_revision: str | None = "0146_assignment_exercise_slots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = (
    "Nullable rotation lineage; NULL mode remains calendar. Existing calendar uniqueness is "
    "retained. New partial indexes are built concurrently and checked before rollout. "
    "Enable rotation only after every application instance runs the new code."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column(
            "user_programs",
            sa.Column("schedule_mode", sa.String(16), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_programs",
            sa.Column("rotation_epoch", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_programs",
            sa.Column("rotation_first_day", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_programs",
            sa.Column("rotation_accepted_revision", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("rotation_epoch", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("rotation_source_cycle_week", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("rotation_role", sa.String(16), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("rotation_mutation_id", sa.String(64), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("rotation_request_hash", sa.String(64), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("rotation_transition_id", sa.String(64), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "user_workouts",
            sa.Column("rotation_transition_hash", sa.String(64), nullable=True),
            if_not_exists=True,
        )
        with op.get_context().autocommit_block():
            op.create_index(
                "uq_user_workouts_rotation_mutation",
                "user_workouts",
                ["user_program_id", "rotation_mutation_id"],
                unique=True,
                postgresql_where=sa.text("rotation_mutation_id IS NOT NULL"),
                postgresql_concurrently=True,
                if_not_exists=True,
            )
            valid_mutation = bind.execute(
                sa.text(
                    "SELECT indisvalid AND indisready AND indisunique "
                    "AND indrelid = 'user_workouts'::regclass "
                    "AND indnkeyatts = 2 AND indnatts = 2 "
                    "AND pg_get_indexdef(indexrelid, 1, true) = 'user_program_id' "
                    "AND pg_get_indexdef(indexrelid, 2, true) = 'rotation_mutation_id' "
                    "AND pg_get_expr(indpred, indrelid) = '(rotation_mutation_id IS NOT NULL)' "
                    "FROM pg_index WHERE indexrelid = 'uq_user_workouts_rotation_mutation'::regclass"
                )
            ).scalar_one()
            if not valid_mutation:
                raise RuntimeError("Incomplete rotation mutation index; repair it before retrying")
            op.create_index(
                "uq_user_workouts_rotation_in_progress",
                "user_workouts",
                ["user_program_id"],
                unique=True,
                postgresql_where=sa.text("rotation_epoch IS NOT NULL AND status = 'in_progress'"),
                postgresql_concurrently=True,
                if_not_exists=True,
            )
            valid_active = bind.execute(
                sa.text(
                    "SELECT indisvalid AND indisready AND indisunique "
                    "AND indrelid = 'user_workouts'::regclass "
                    "AND indnkeyatts = 1 AND indnatts = 1 "
                    "AND pg_get_indexdef(indexrelid, 1, true) = 'user_program_id' "
                    "AND pg_get_expr(indpred, indrelid) = "
                    "'((rotation_epoch IS NOT NULL) AND ((status)::text = ''in_progress''::text))' "
                    "FROM pg_index WHERE indexrelid = 'uq_user_workouts_rotation_in_progress'::regclass"
                )
            ).scalar_one()
            if not valid_active:
                raise RuntimeError("Incomplete active rotation index; repair it before retrying")
    else:
        op.add_column("user_programs", sa.Column("schedule_mode", sa.String(16), nullable=True))
        op.add_column("user_programs", sa.Column("rotation_epoch", sa.Integer(), nullable=True))
        op.add_column("user_programs", sa.Column("rotation_first_day", sa.Integer(), nullable=True))
        op.add_column(
            "user_programs", sa.Column("rotation_accepted_revision", sa.Integer(), nullable=True)
        )
        op.add_column("user_workouts", sa.Column("rotation_epoch", sa.Integer(), nullable=True))
        op.add_column(
            "user_workouts", sa.Column("rotation_source_cycle_week", sa.Integer(), nullable=True)
        )
        op.add_column("user_workouts", sa.Column("rotation_role", sa.String(16), nullable=True))
        op.add_column(
            "user_workouts", sa.Column("rotation_mutation_id", sa.String(64), nullable=True)
        )
        op.add_column(
            "user_workouts", sa.Column("rotation_request_hash", sa.String(64), nullable=True)
        )
        op.add_column(
            "user_workouts", sa.Column("rotation_transition_id", sa.String(64), nullable=True)
        )
        op.add_column(
            "user_workouts", sa.Column("rotation_transition_hash", sa.String(64), nullable=True)
        )
        op.create_index(
            "uq_user_workouts_rotation_mutation",
            "user_workouts",
            ["user_program_id", "rotation_mutation_id"],
            unique=True,
            sqlite_where=sa.text("rotation_mutation_id IS NOT NULL"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "uq_user_workouts_rotation_in_progress",
            "user_workouts",
            ["user_program_id"],
            unique=True,
            sqlite_where=sa.text("rotation_epoch IS NOT NULL AND status = 'in_progress'"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if (
        bind.execute(
            sa.text(
                "SELECT 1 FROM user_programs WHERE (schedule_mode IS NOT NULL AND "
                "schedule_mode <> 'calendar') OR rotation_epoch IS NOT NULL "
                "OR rotation_first_day IS NOT NULL OR rotation_accepted_revision IS NOT NULL LIMIT 1"
            )
        ).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM user_workouts WHERE rotation_epoch IS NOT NULL "
                "OR rotation_source_cycle_week IS NOT NULL OR rotation_role IS NOT NULL "
                "OR rotation_mutation_id IS NOT NULL OR rotation_request_hash IS NOT NULL "
                "OR rotation_transition_id IS NOT NULL OR rotation_transition_hash IS NOT NULL LIMIT 1"
            )
        ).first()
    ):
        raise RuntimeError("Unsafe downgrade: session rotation data exists; use a forward fix")
    postgres = bind.dialect.name == "postgresql"
    if postgres:
        with op.get_context().autocommit_block():
            op.drop_index(
                "uq_user_workouts_rotation_mutation",
                table_name="user_workouts",
                postgresql_concurrently=True,
            )
            op.drop_index(
                "uq_user_workouts_rotation_in_progress",
                table_name="user_workouts",
                postgresql_concurrently=True,
            )
    else:
        op.drop_index("uq_user_workouts_rotation_mutation", table_name="user_workouts")
        op.drop_index("uq_user_workouts_rotation_in_progress", table_name="user_workouts")
    for name in (
        "rotation_transition_hash",
        "rotation_transition_id",
        "rotation_request_hash",
        "rotation_mutation_id",
        "rotation_role",
        "rotation_source_cycle_week",
        "rotation_epoch",
    ):
        op.drop_column("user_workouts", name)
    for name in (
        "rotation_accepted_revision",
        "rotation_first_day",
        "rotation_epoch",
        "schedule_mode",
    ):
        op.drop_column("user_programs", name)
