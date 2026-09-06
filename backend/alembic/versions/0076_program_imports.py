"""Add short-lived normalized program import drafts.

Revision ID: 0076_program_imports
Revises: 0075_web_push_delivery
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0076_program_imports"
down_revision: str | None = "0075_web_push_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds owner-scoped short-lived normalized drafts for the versioned deterministic XLSX/CSV "
    "program import. Source files are not persisted; canonical program tables are unchanged "
    "until explicit confirm."
)


def upgrade() -> None:
    op.create_table(
        "program_imports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_format", sa.String(length=8), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("draft_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cell_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocking_issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "confirmed_template_id",
            sa.Integer(),
            sa.ForeignKey("program_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'expired')",
            name="ck_program_imports_status",
        ),
        sa.CheckConstraint(
            "source_format IN ('csv', 'xlsx')",
            name="ck_program_imports_format",
        ),
    )
    op.create_index(
        "ix_program_imports_owner_status_expiry",
        "program_imports",
        ["owner_user_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_program_imports_hash_status",
        "program_imports",
        ["owner_user_id", "source_sha256", "status"],
    )
    op.create_index(
        "uq_program_imports_pending_hash",
        "program_imports",
        ["owner_user_id", "source_sha256"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_program_imports_expires_at", "program_imports", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_program_imports_expires_at", table_name="program_imports")
    op.drop_index("uq_program_imports_pending_hash", table_name="program_imports")
    op.drop_index("ix_program_imports_hash_status", table_name="program_imports")
    op.drop_index("ix_program_imports_owner_status_expiry", table_name="program_imports")
    op.drop_table("program_imports")
