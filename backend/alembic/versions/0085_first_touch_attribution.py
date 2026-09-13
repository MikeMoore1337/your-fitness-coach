"""Store one immutable, allowlisted first-touch attribution record per account."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0085_first_touch_attribution"
down_revision: str | None = "0084_nutrition_diary_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "first_touch_attributions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("first_touch_source", sa.String(length=16), nullable=False),
        sa.Column("first_touch_medium", sa.String(length=64), nullable=False),
        sa.Column("first_touch_campaign", sa.String(length=128), nullable=True),
        sa.Column("first_landing_path", sa.String(length=256), nullable=False),
        sa.Column("first_referrer", sa.String(length=512), nullable=True),
        sa.Column("first_touch_at", sa.DateTime(), nullable=False),
        sa.Column("utm_source", sa.String(length=128), nullable=True),
        sa.Column("utm_medium", sa.String(length=128), nullable=True),
        sa.Column("utm_campaign", sa.String(length=128), nullable=True),
        sa.Column("utm_content", sa.String(length=128), nullable=True),
        sa.Column("utm_term", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "first_touch_source IN ('google', 'yandex', 'telegram', 'direct', 'referral', 'utm')",
            name="ck_first_touch_attributions_source",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_first_touch_attributions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_first_touch_attributions"),
    )


def downgrade() -> None:
    op.drop_table("first_touch_attributions")
