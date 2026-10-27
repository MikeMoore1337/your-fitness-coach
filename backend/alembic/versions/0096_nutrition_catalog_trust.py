"""Align the active community catalog trust constraint with the food model."""

from collections.abc import Sequence

from alembic import op

revision: str = "0096_nutrition_catalog_trust"
down_revision: str | None = "0095_program_provenance_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_notes = (
    "Replaces one legacy CHECK constraint on foods under a 3-second lock timeout. "
    "The replacement is added NOT VALID so the ACCESS EXCLUSIVE lock does not scan rows; "
    "validation then uses PostgreSQL VALIDATE CONSTRAINT under a bounded 30-second statement timeout."
)
online_rollout_constraint_table = "foods"
online_rollout_constraint_name = "ck_foods_active_catalog_trust"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            """ALTER TABLE foods
            DROP CONSTRAINT IF EXISTS ck_foods_active_catalog_trust,
            ADD CONSTRAINT ck_foods_active_catalog_trust
            CHECK (
                food_type = 'user'
                OR status <> 'active'
                OR trust_level = 'verified'
                OR catalog_quality = 'community_unverified'
            ) NOT VALID"""
        )
        op.execute(
            "ALTER TABLE foods VALIDATE CONSTRAINT ck_foods_active_catalog_trust"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            """ALTER TABLE foods
            DROP CONSTRAINT IF EXISTS ck_foods_active_catalog_trust,
            ADD CONSTRAINT ck_foods_active_catalog_trust
            CHECK (
                food_type = 'user'
                OR status <> 'active'
                OR trust_level = 'verified'
            ) NOT VALID"""
        )
        op.execute(
            "ALTER TABLE foods VALIDATE CONSTRAINT ck_foods_active_catalog_trust"
        )
