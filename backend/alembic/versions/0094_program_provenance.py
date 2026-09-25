"""Add nullable provenance and product metadata to program templates."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0094_program_provenance"
down_revision: str | None = "0093_advanced_prescriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds three nullable scalar provenance/metadata columns using direct ADD COLUMN operations. "
    "No rows are scanned or backfilled, no table is rewritten, and no constraint, index, or "
    "default is added. Each addition takes only the brief PostgreSQL catalog lock and no "
    "row-data work. The previous application revision ignores these nullable columns."
)


def upgrade() -> None:
    op.add_column(
        "program_templates",
        sa.Column("provenance_type", sa.String(length=24), nullable=True),
    )
    op.add_column("program_templates", sa.Column("provenance", sa.JSON(), nullable=True))
    op.add_column("program_templates", sa.Column("program_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("program_templates", "program_metadata")
    op.drop_column("program_templates", "provenance")
    op.drop_column("program_templates", "provenance_type")
