"""Add owner-revocable immutable public share snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0107_public_shares"
down_revision: str | None = "0106_macro_aware_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Creates empty owner-scoped public snapshot and recipient provenance tables. Public shares are "
    "noindex, immutable snapshots; no existing private program or progress rows are rewritten."
)


def upgrade() -> None:
    op.create_table(
        "public_shares",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("share_id", sa.String(length=64), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("share_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("public_snapshot", sa.JSON(), nullable=False),
        sa.Column("private_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "share_type IN ('progress', 'program')",
            name="ck_public_shares_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_public_shares_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_public_shares_share_id", "public_shares", ["share_id"], unique=True)
    op.create_index(
        "ix_public_shares_owner_created",
        "public_shares",
        ["owner_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_public_shares_owner_status",
        "public_shares",
        ["owner_user_id", "status"],
        unique=False,
    )
    op.create_table(
        "public_share_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "public_share_id",
            sa.Integer(),
            sa.ForeignKey("public_shares.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recipient_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("program_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_program_id",
            sa.Integer(),
            sa.ForeignKey("user_programs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "public_share_id",
            "recipient_user_id",
            name="uq_public_share_imports_share_recipient",
        ),
    )
    op.create_index(
        "ix_public_share_imports_public_share_id",
        "public_share_imports",
        ["public_share_id"],
        unique=False,
    )
    op.create_index(
        "ix_public_share_imports_recipient_user_id",
        "public_share_imports",
        ["recipient_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_public_share_imports_recipient_created",
        "public_share_imports",
        ["recipient_user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_public_share_imports_recipient_created", table_name="public_share_imports")
    op.drop_index("ix_public_share_imports_recipient_user_id", table_name="public_share_imports")
    op.drop_index("ix_public_share_imports_public_share_id", table_name="public_share_imports")
    op.drop_table("public_share_imports")
    op.drop_index("ix_public_shares_owner_status", table_name="public_shares")
    op.drop_index("ix_public_shares_owner_created", table_name="public_shares")
    op.drop_index("ix_public_shares_share_id", table_name="public_shares")
    op.drop_table("public_shares")
