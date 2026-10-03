"""Add a coarse lifecycle measurement eligibility boundary to accounts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0118_measurement_eligibility"
down_revision: str | None = "0117_weekly_action_constraint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds a nullable bounded non-sensitive account classification without a table rewrite. Existing "
    "NULL rows remain eligible as legacy real_client accounts; new application writes use the "
    "real_client default, while technical/demo/test classifications stay visible to reconciliation."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column(
            "users",
            sa.Column("measurement_eligibility", sa.String(length=16), nullable=True),
            if_not_exists=True,
        )
    else:
        op.add_column(
            "users",
            sa.Column("measurement_eligibility", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("users", "measurement_eligibility")
