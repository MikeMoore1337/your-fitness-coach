"""Add short-lived owner-scoped photo meal drafts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0104_photo_meal_drafts"
down_revision: str | None = "0103_nutrition_partial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = (
    "Creates an empty owner-scoped draft table. Source photo bytes are never stored and no "
    "existing diary rows are rewritten."
)


def upgrade() -> None:
    op.create_table(
        "photo_meal_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("canonical_payload", sa.JSON(), nullable=False),
        sa.Column("source_mime", sa.String(length=64), nullable=False),
        sa.Column(
            "confirmed_entry_id",
            sa.Integer(),
            sa.ForeignKey("food_diary_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'cancelled', 'expired')",
            name="ck_photo_meal_drafts_status",
        ),
        sa.CheckConstraint("revision > 0", name="ck_photo_meal_drafts_revision"),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="photo_meal_drafts_user_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="photo_meal_drafts_pkey"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_photo_meal_drafts_user_idempotency"
        ),
    )
    op.create_index(
        "ix_photo_meal_drafts_user_status",
        "photo_meal_drafts",
        ["user_id", "status", "expires_at"],
    )
    op.create_index("ix_photo_meal_drafts_expires_at", "photo_meal_drafts", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_photo_meal_drafts_expires_at", table_name="photo_meal_drafts")
    op.drop_index("ix_photo_meal_drafts_user_status", table_name="photo_meal_drafts")
    op.drop_table("photo_meal_drafts")
