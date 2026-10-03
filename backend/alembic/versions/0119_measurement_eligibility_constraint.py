"""Bound the nullable measurement eligibility values safely online."""

from collections.abc import Sequence

from alembic import op

revision: str = "0119_measurement_eligibility_constraint"
down_revision: str | None = "0118_measurement_eligibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_notes = (
    "Replaces the measurement eligibility CHECK under bounded PostgreSQL lock and statement "
    "timeouts; NULL remains the explicit legacy-account state during the additive rollout."
)
online_rollout_constraint_table = "users"
online_rollout_constraint_name = "ck_users_measurement_eligibility"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_measurement_eligibility, "
            "ADD CONSTRAINT ck_users_measurement_eligibility CHECK (measurement_eligibility "
            "IS NULL OR measurement_eligibility IN ('real_client', 'demo', 'test', 'synthetic', "
            "'load_test', 'technical')) NOT VALID"
        )
        op.execute("ALTER TABLE users VALIDATE CONSTRAINT ck_users_measurement_eligibility")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_measurement_eligibility")
