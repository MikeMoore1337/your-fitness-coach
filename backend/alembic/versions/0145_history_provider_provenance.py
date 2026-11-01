"""Add nullable provider metadata without rewriting imported history."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0145_history_provider_provenance"
down_revision: str | None = "0144_workout_side_metadata_ck"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add two nullable columns; preserve existing workout and source timezone values."


def upgrade() -> None:
    op.add_column("imported_workouts", sa.Column("source_data", sa.JSON(), nullable=True))
    op.add_column("user_workout_sets", sa.Column("set_kind_known", sa.Boolean(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
    if (
        bind.execute(
            sa.text("SELECT 1 FROM imported_workouts WHERE source_data IS NOT NULL LIMIT 1")
        ).first()
        or bind.execute(
            sa.text("SELECT 1 FROM user_workout_sets WHERE set_kind_known IS NOT NULL LIMIT 1")
        ).first()
    ):
        raise RuntimeError("Cannot discard imported provider provenance or unknown set kinds")
    op.drop_column("imported_workouts", "source_data")
    op.drop_column("user_workout_sets", "set_kind_known")
