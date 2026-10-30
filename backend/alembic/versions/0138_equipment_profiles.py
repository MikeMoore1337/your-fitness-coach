"""Store user-owned equipment profiles independently of training preferences."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0138_equipment_profiles"
down_revision: str | None = "0137_merge_activity_cycles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add independent user-owned equipment profile state with empty defaults."


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("equipment_profiles", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "user_profiles", sa.Column("active_equipment_profile_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "user_profiles",
        sa.Column("equipment_profiles_revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "equipment_profiles_revision")
    op.drop_column("user_profiles", "active_equipment_profile_id")
    op.drop_column("user_profiles", "equipment_profiles")
