"""Remove the product week ceiling while retaining a positive-domain CHECK."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0136_program_week_number_unbounded"
down_revision: str | None = "0135_program_duration_unbounded"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "constraint_swap"
online_rollout_notes = (
    "Replace only the declared CHECK under bounded PostgreSQL lock and validation timeouts."
)
online_rollout_constraint_table = "program_template_exercise_weeks"
online_rollout_constraint_name = "ck_program_template_exercise_weeks_number"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE program_template_exercise_weeks DROP CONSTRAINT IF EXISTS ck_program_template_exercise_weeks_number, "
            "ADD CONSTRAINT ck_program_template_exercise_weeks_number CHECK (week_number >= 1) NOT VALID"
        )
        op.execute(
            "ALTER TABLE program_template_exercise_weeks VALIDATE CONSTRAINT ck_program_template_exercise_weeks_number"
        )
    else:
        with op.batch_alter_table("program_template_exercise_weeks") as batch:
            batch.drop_constraint("ck_program_template_exercise_weeks_number", type_="check")
            batch.create_check_constraint(
                "ck_program_template_exercise_weeks_number", "week_number >= 1"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if (
        bind.execute(
            sa.text("SELECT 1 FROM program_template_exercise_weeks WHERE week_number > 24 LIMIT 1")
        ).first()
        is not None
    ):
        raise RuntimeError(
            "Unsafe downgrade: program_template_exercise_weeks.week_number exceeds 24; preserve long programs"
        )
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE program_template_exercise_weeks DROP CONSTRAINT IF EXISTS ck_program_template_exercise_weeks_number, "
            "ADD CONSTRAINT ck_program_template_exercise_weeks_number CHECK (week_number >= 1 AND week_number <= 24) NOT VALID"
        )
        op.execute(
            "ALTER TABLE program_template_exercise_weeks VALIDATE CONSTRAINT ck_program_template_exercise_weeks_number"
        )
    else:
        with op.batch_alter_table("program_template_exercise_weeks") as batch:
            batch.drop_constraint("ck_program_template_exercise_weeks_number", type_="check")
            batch.create_check_constraint(
                "ck_program_template_exercise_weeks_number",
                "week_number >= 1 AND week_number <= 24",
            )
