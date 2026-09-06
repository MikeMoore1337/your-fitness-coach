"""Store week-specific prescriptions for imported program templates.

Revision ID: 0077_periodized_program_templates
Revises: 0076_program_imports
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0077_periodized_program_templates"
down_revision: str | None = "0076_program_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds a bounded default duration to program templates and normalized week-specific "
    "prescriptions used by deterministic XLSX/CSV imports. Existing templates keep one week."
)


def upgrade() -> None:
    with op.batch_alter_table("program_templates") as batch_op:
        batch_op.add_column(
            sa.Column("default_duration_weeks", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.create_check_constraint(
            "ck_program_templates_default_duration_weeks",
            "default_duration_weeks >= 1 AND default_duration_weeks <= 24",
        )
    op.create_table(
        "program_template_exercise_weeks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "template_exercise_id",
            sa.Integer(),
            sa.ForeignKey("program_template_exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id"),
            nullable=False,
        ),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("prescribed_sets", sa.Integer(), nullable=False),
        sa.Column("prescribed_reps", sa.String(length=32), nullable=False),
        sa.Column("prescribed_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=False, server_default="90"),
        sa.UniqueConstraint(
            "template_exercise_id",
            "week_number",
            name="uq_program_template_exercise_week",
        ),
        sa.CheckConstraint(
            "week_number >= 1 AND week_number <= 24",
            name="ck_program_template_exercise_weeks_number",
        ),
        sa.CheckConstraint(
            "prescribed_sets >= 1 AND prescribed_sets <= 10",
            name="ck_program_template_exercise_weeks_sets",
        ),
        sa.CheckConstraint(
            "prescribed_duration_minutes IS NULL OR prescribed_duration_minutes >= 1",
            name="ck_program_template_exercise_weeks_duration",
        ),
        sa.CheckConstraint(
            "rest_seconds >= 0 AND rest_seconds <= 600",
            name="ck_program_template_exercise_weeks_rest",
        ),
    )
    op.create_index(
        "ix_program_template_exercise_weeks_template_exercise_id",
        "program_template_exercise_weeks",
        ["template_exercise_id"],
    )
    op.create_index(
        "ix_program_template_exercise_weeks_exercise_id",
        "program_template_exercise_weeks",
        ["exercise_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_program_template_exercise_weeks_exercise_id",
        table_name="program_template_exercise_weeks",
    )
    op.drop_index(
        "ix_program_template_exercise_weeks_template_exercise_id",
        table_name="program_template_exercise_weeks",
    )
    op.drop_table("program_template_exercise_weeks")
    with op.batch_alter_table("program_templates") as batch_op:
        batch_op.drop_constraint(
            "ck_program_templates_default_duration_weeks",
            type_="check",
        )
        batch_op.drop_column("default_duration_weeks")
