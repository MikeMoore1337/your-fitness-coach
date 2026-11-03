"""Store user-owned equipment profiles independently of training preferences."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0138_equipment_profiles"
down_revision: str | None = "0137_merge_activity_cycles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add nullable user-owned equipment profile state without rewriting rows."


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("equipment_profiles", sa.JSON(), nullable=True),
    )
    op.add_column(
        "user_profiles", sa.Column("active_equipment_profile_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "user_profiles",
        sa.Column("equipment_profiles_revision", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Unsafe downgrade: equipment profile protection requires PostgreSQL")
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute("LOCK TABLE user_profiles IN ACCESS EXCLUSIVE MODE")
    if bind.execute(
        sa.text(
            "SELECT 1 FROM user_profiles WHERE equipment_profiles IS NOT NULL "
            "OR active_equipment_profile_id IS NOT NULL "
            "OR equipment_profiles_revision IS NOT NULL LIMIT 1"
        )
    ).first():
        raise RuntimeError("Unsafe downgrade: equipment profile data exists; use forward-fix")
    op.drop_column("user_profiles", "equipment_profiles_revision")
    op.drop_column("user_profiles", "active_equipment_profile_id")
    op.drop_column("user_profiles", "equipment_profiles")
