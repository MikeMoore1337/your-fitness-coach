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
    "Adds a bounded non-sensitive account classification with a real_client default. Existing "
    "accounts remain eligible; technical/demo/test classifications are excluded from lifecycle "
    "aggregates and remain visible to reconciliation without storing product payloads."
)

_ELIGIBILITY_CHECK = (
    "measurement_eligibility IN "
    "('real_client', 'demo', 'test', 'synthetic', 'load_test', 'technical')"
)


def upgrade() -> None:
    bind = op.get_bind()
    column = sa.Column(
        "measurement_eligibility",
        sa.String(length=16),
        nullable=False,
        server_default="real_client",
    )
    if bind.dialect.name == "postgresql":
        op.add_column("users", column, if_not_exists=True)
        op.execute(
            "ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_measurement_eligibility, "
            f"ADD CONSTRAINT ck_users_measurement_eligibility CHECK ({_ELIGIBILITY_CHECK}) NOT VALID"
        )
        op.execute("ALTER TABLE users VALIDATE CONSTRAINT ck_users_measurement_eligibility")
    else:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(column)
            batch_op.create_check_constraint(
                "ck_users_measurement_eligibility",
                _ELIGIBILITY_CHECK,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_measurement_eligibility")
    else:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_constraint("ck_users_measurement_eligibility", type_="check")
            batch_op.drop_column("measurement_eligibility")
        return
    op.drop_column("users", "measurement_eligibility")
