"""Create short-lived owner-scoped nutrition import drafts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0153_nutrition_import_drafts"
down_revision: str | None = "0152_nutrition_override_day_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Create an empty table without modifying existing nutrition records."


def upgrade() -> None:
    op.create_table(
        "nutrition_import_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("upload_key_hash", sa.String(64), nullable=False),
        sa.Column("upload_fingerprint", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("skipped_rows", sa.JSON(), nullable=False),
        sa.Column("resolutions", sa.JSON(), nullable=False),
        sa.Column("confirm_key_hash", sa.String(64), nullable=True),
        sa.Column("confirm_fingerprint", sa.String(64), nullable=True),
        sa.Column("receipt", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled')",
            name="ck_nutrition_import_draft_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_nutrition_import_draft_revision"),
        sa.UniqueConstraint(
            "owner_user_id", "upload_key_hash", name="uq_nutrition_import_owner_upload"
        ),
        sa.UniqueConstraint(
            "owner_user_id", "confirm_key_hash", name="uq_nutrition_import_owner_confirm"
        ),
    )
    op.create_index(
        "ix_nutrition_import_owner_created",
        "nutrition_import_drafts",
        ["owner_user_id", "created_at"],
    )
    op.create_index("ix_nutrition_import_expiry", "nutrition_import_drafts", ["expires_at"])

    op.create_table(
        "nutrition_import_upload_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_nutrition_import_attempt_owner_time",
        "nutrition_import_upload_attempts",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        "ix_nutrition_import_attempt_expiry", "nutrition_import_upload_attempts", ["created_at"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        if bind.execute(sa.text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: PostgreSQL READ COMMITTED isolation is required")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "LOCK TABLE nutrition_import_drafts, nutrition_import_upload_attempts IN ACCESS EXCLUSIVE MODE"
        )
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE nutrition_import_drafts SET id = id WHERE 0")
        op.execute("UPDATE nutrition_import_upload_attempts SET id = id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError("Unsafe downgrade: import draft locking requires a transaction")
    else:
        raise RuntimeError("Unsafe downgrade: import draft locking is unsupported")
    if (
        bind.execute(sa.text("SELECT 1 FROM nutrition_import_drafts LIMIT 1")).first()
        or bind.execute(sa.text("SELECT 1 FROM nutrition_import_upload_attempts LIMIT 1")).first()
    ):
        raise RuntimeError("Unsafe downgrade: nutrition import drafts exist")
    op.drop_table("nutrition_import_upload_attempts")
    op.drop_table("nutrition_import_drafts")
