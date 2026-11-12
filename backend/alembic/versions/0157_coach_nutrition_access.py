"""Preserve existing nutrition access and allow separate revocation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0157_coach_nutrition_access"
down_revision: str | None = "0156_nutrition_catalog_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add a relationship permission while preserving existing access."


def upgrade() -> None:
    op.add_column(
        "coach_clients",
        sa.Column("nutrition_access", sa.Boolean(), nullable=True, server_default=sa.true()),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT 1 FROM coach_clients WHERE nutrition_access IS NOT TRUE LIMIT 1")
    ).first():
        raise RuntimeError("Cannot discard revoked nutrition access")
    op.drop_column("coach_clients", "nutrition_access")
