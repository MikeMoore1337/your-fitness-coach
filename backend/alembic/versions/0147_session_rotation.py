"""Add opt-in session rotation without rewriting existing workout facts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0147_session_rotation"
down_revision: str | None = "0146_assignment_exercise_slots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = (
    "Add opt-in rotation lineage and replace the calendar-only occurrence index. "
    "Enable rotation only after every application instance runs the new code."
)


def _index(name: str, columns: list[str], predicate: str, *, unique: bool = False) -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    op.create_index(
        name,
        "user_workouts",
        columns,
        unique=unique,
        postgresql_where=sa.text(predicate),
        sqlite_where=sa.text(predicate),
        postgresql_concurrently=postgres,
        if_not_exists=postgres,
    )
    if postgres:
        definition = (
            op.get_bind()
            .execute(
                sa.text(
                    "SELECT indisvalid AND indisready AND indisunique = :unique "
                    "AND indrelid = to_regclass('user_workouts') AS valid, "
                    "ARRAY(SELECT a.attname::text FROM unnest(i.indkey) WITH ORDINALITY AS k(num, pos) "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.num "
                    "ORDER BY k.pos) AS columns, pg_get_expr(indpred, indrelid) AS predicate "
                    "FROM pg_index i WHERE indexrelid = to_regclass(:name)"
                ),
                {"name": name, "unique": unique},
            )
            .mappings()
            .one_or_none()
        )

        def normalized(value: str) -> str:
            return (
                value.lower()
                .replace("::character varying", "")
                .replace("::text", "")
                .replace('"', "")
                .replace("(", "")
                .replace(")", "")
                .replace(" ", "")
            )

        if (
            not definition
            or not definition["valid"]
            or definition["columns"] != columns
            or not definition["predicate"]
            or normalized(definition["predicate"]) != normalized(predicate)
        ):
            raise RuntimeError(f"Incomplete rotation index {name}; repair it before retrying")


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    optional = {"if_not_exists": True} if postgres else {}
    op.add_column(
        "user_programs",
        sa.Column("schedule_mode", sa.String(16), nullable=False, server_default="calendar"),
        **optional,
    )
    for name in ("rotation_epoch", "rotation_first_day", "rotation_accepted_revision"):
        op.add_column("user_programs", sa.Column(name, sa.Integer(), nullable=True), **optional)
    op.add_column(
        "user_workouts", sa.Column("rotation_epoch", sa.Integer(), nullable=True), **optional
    )
    op.add_column(
        "user_workouts", sa.Column("rotation_role", sa.String(16), nullable=True), **optional
    )
    for name in (
        "rotation_mutation_id",
        "rotation_request_hash",
        "rotation_transition_id",
        "rotation_transition_hash",
    ):
        op.add_column("user_workouts", sa.Column(name, sa.String(64), nullable=True), **optional)

    def replace_indexes() -> None:
        _index(
            "uq_user_workouts_cycle_occurrence_calendar",
            ["user_program_id", "week_number", "day_number"],
            "source_cycle_week IS NOT NULL AND rotation_epoch IS NULL",
            unique=True,
        )
        _index(
            "uq_user_workouts_rotation_mutation",
            ["user_program_id", "rotation_mutation_id"],
            "rotation_mutation_id IS NOT NULL",
            unique=True,
        )
        _index(
            "uq_user_workouts_rotation_in_progress",
            ["user_program_id"],
            "rotation_epoch IS NOT NULL AND status = 'in_progress'",
            unique=True,
        )
        _index(
            "ix_user_workouts_rotation_epoch",
            ["user_program_id", "rotation_epoch", "id"],
            "rotation_epoch IS NOT NULL",
        )
        op.drop_index(
            "uq_user_workouts_cycle_occurrence",
            table_name="user_workouts",
            postgresql_concurrently=postgres,
            if_exists=postgres,
        )

    if postgres:
        with op.get_context().autocommit_block():
            replace_indexes()
    else:
        replace_indexes()


def downgrade() -> None:
    bind = op.get_bind()
    if (
        bind.execute(
            sa.text(
                "SELECT 1 FROM user_programs WHERE schedule_mode <> 'calendar' "
                "OR rotation_epoch IS NOT NULL OR rotation_first_day IS NOT NULL "
                "OR rotation_accepted_revision IS NOT NULL LIMIT 1"
            )
        ).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM user_workouts WHERE rotation_epoch IS NOT NULL "
                "OR rotation_role IS NOT NULL OR rotation_mutation_id IS NOT NULL "
                "OR rotation_request_hash IS NOT NULL OR rotation_transition_id IS NOT NULL "
                "OR rotation_transition_hash IS NOT NULL LIMIT 1"
            )
        ).first()
    ):
        raise RuntimeError("Unsafe downgrade: session rotation data exists; use a forward fix")
    postgres = bind.dialect.name == "postgresql"

    def restore_indexes() -> None:
        _index(
            "uq_user_workouts_cycle_occurrence",
            ["user_program_id", "week_number", "day_number"],
            "source_cycle_week IS NOT NULL",
            unique=True,
        )
        for name in (
            "uq_user_workouts_cycle_occurrence_calendar",
            "uq_user_workouts_rotation_mutation",
            "uq_user_workouts_rotation_in_progress",
            "ix_user_workouts_rotation_epoch",
        ):
            op.drop_index(name, table_name="user_workouts", postgresql_concurrently=postgres)

    if postgres:
        with op.get_context().autocommit_block():
            restore_indexes()
    else:
        restore_indexes()
    for name in (
        "rotation_transition_hash",
        "rotation_transition_id",
        "rotation_request_hash",
        "rotation_mutation_id",
        "rotation_role",
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
