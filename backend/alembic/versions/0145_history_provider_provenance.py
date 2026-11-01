"""Keep provider provenance without inventing a source timezone."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0145_history_provider_provenance"
down_revision: str | None = "0144_workout_side_metadata_ck"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
    with op.batch_alter_table("imported_workouts") as batch:
        batch.alter_column("source_timezone", existing_type=sa.String(128), nullable=True)
        batch.add_column(sa.Column("source_data", sa.JSON(), nullable=True))
    op.add_column("user_workout_sets", sa.Column("set_kind_known", sa.Boolean(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if (
        bind.execute(
            sa.text(
                "SELECT 1 FROM imported_workouts WHERE source_timezone IS NULL OR source_data IS NOT NULL LIMIT 1"
            )
        ).first()
        or bind.execute(
            sa.text("SELECT 1 FROM user_workout_sets WHERE set_kind_known IS NOT NULL LIMIT 1")
        ).first()
    ):
        raise RuntimeError("Cannot discard imported provider provenance or an unknown timezone")
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
    with op.batch_alter_table("imported_workouts") as batch:
        batch.drop_column("source_data")
        batch.alter_column("source_timezone", existing_type=sa.String(128), nullable=False)
    op.drop_column("user_workout_sets", "set_kind_known")
