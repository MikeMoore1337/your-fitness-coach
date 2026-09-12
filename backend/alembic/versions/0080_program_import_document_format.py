"""Add a compatible format discriminator for document imports.

Revision ID: 0080_program_import_doc_format
Revises: 0079_ai_coach_memory
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0080_program_import_doc_format"
down_revision: str | None = "0079_ai_coach_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds a nullable document-format discriminator so TXT/DOCX uploads can coexist with the "
    "original 0076 source_format check; NULL keeps legacy CSV/XLSX rows compatible."
)


def upgrade() -> None:
    op.add_column(
        "program_imports",
        sa.Column("document_format", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("program_imports") as batch_op:
        batch_op.drop_column("document_format")
