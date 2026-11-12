"""Store coach proposals and their client decisions."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0158_coach_nutrition_proposals"
down_revision: str | None = "0157_coach_nutrition_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add isolated proposal records without changing existing nutrition history."


def upgrade() -> None:
    op.create_table(
        "coach_nutrition_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "relationship_id",
            sa.Integer(),
            sa.ForeignKey("coach_clients.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "coach_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "client_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("create_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decision_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_coach_nutrition_proposal_status",
        ),
        sa.CheckConstraint(
            "version > 0 AND plan_revision >= 0", name="ck_coach_nutrition_proposal_versions"
        ),
        sa.UniqueConstraint(
            "coach_user_id", "create_key", name="uq_coach_nutrition_proposal_create"
        ),
        sa.UniqueConstraint(
            "relationship_id", "version", name="uq_coach_nutrition_proposal_version"
        ),
    )
    op.create_index(
        "ix_coach_nutrition_proposal_client", "coach_nutrition_proposals", ["client_user_id", "id"]
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM coach_nutrition_proposals LIMIT 1")).first():
        raise RuntimeError("Cannot discard coach nutrition proposals")
    op.drop_index("ix_coach_nutrition_proposal_client", table_name="coach_nutrition_proposals")
    op.drop_table("coach_nutrition_proposals")
