"""Add account-private nutrition notes and their separate consent."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0159_nutrition_meal_notes"
down_revision: str | None = "0158_coach_nutrition_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add isolated optional personal records without changing diary history."


def upgrade() -> None:
    op.create_table(
        "nutrition_notes_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("consent_version", sa.String(32), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_nutrition_notes_consent_user"),
        sa.CheckConstraint(
            "status IN ('enabled', 'disabled', 'revoked', 'recovery_hold')",
            name="ck_nutrition_notes_consent_status",
        ),
    )
    op.create_table(
        "nutrition_meal_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(16), nullable=False),
        sa.Column("timezone_at_entry", sa.String(64), nullable=False),
        sa.Column("hunger_before", sa.String(16), nullable=True),
        sa.Column("fullness_after", sa.String(16), nullable=True),
        sa.Column("energy", sa.String(16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "local_date", "meal_type", name="uq_nutrition_meal_note_group"
        ),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snacks')",
            name="ck_nutrition_meal_note_type",
        ),
        sa.CheckConstraint(
            "hunger_before IS NULL OR hunger_before IN ('none', 'low', 'medium', 'high')",
            name="ck_nutrition_meal_note_hunger",
        ),
        sa.CheckConstraint(
            "fullness_after IS NULL OR fullness_after IN ('none', 'low', 'medium', 'high')",
            name="ck_nutrition_meal_note_fullness",
        ),
        sa.CheckConstraint(
            "energy IS NULL OR energy IN ('low', 'normal', 'high')",
            name="ck_nutrition_meal_note_energy",
        ),
        sa.CheckConstraint(
            "note IS NULL OR length(note) <= 500", name="ck_nutrition_meal_note_text_length"
        ),
        sa.CheckConstraint(
            "hunger_before IS NOT NULL OR fullness_after IS NOT NULL OR energy IS NOT NULL OR note IS NOT NULL",
            name="ck_nutrition_meal_note_nonempty",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("nutrition_meal_notes", "nutrition_notes_consents"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("Cannot discard nutrition notes or consent")
    op.drop_table("nutrition_meal_notes")
    op.drop_table("nutrition_notes_consents")
