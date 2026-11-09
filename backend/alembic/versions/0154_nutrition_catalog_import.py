"""Add imported catalogue identifiers and nullable confirmation fields."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0154_nutrition_catalog_import"
down_revision: str | None = "0153_nutrition_import_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Create an empty identifier table and add nullable import fields."


def upgrade() -> None:
    op.create_table(
        "nutrition_catalog_identifiers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "food_id", sa.Integer(), sa.ForeignKey("foods.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("identity_source", sa.String(64), nullable=True),
        sa.Column("source_id", sa.String(128), nullable=True),
        sa.CheckConstraint(
            "kind IN ('source', 'alias')", name="ck_nutrition_catalog_identifier_kind"
        ),
        sa.CheckConstraint(
            "(kind = 'source' AND provider IS NOT NULL AND source IS NOT NULL "
            "AND identity_source IS NOT NULL AND source_id IS NOT NULL) OR "
            "(kind = 'alias' AND provider IS NULL AND source IS NULL "
            "AND identity_source IS NULL AND source_id IS NULL)",
            name="ck_nutrition_catalog_identifier_shape",
        ),
        sa.UniqueConstraint("kind", "key_hash", name="uq_nutrition_catalog_identifier_key"),
    )
    op.add_column("nutrition_import_drafts", sa.Column("adapter_id", sa.String(64), nullable=True))
    op.add_column(
        "nutrition_import_drafts",
        sa.Column("catalog_confirm_key_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "nutrition_import_drafts",
        sa.Column("catalog_confirm_fingerprint", sa.String(64), nullable=True),
    )
    op.add_column("nutrition_import_drafts", sa.Column("catalog_receipt", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        if bind.execute(sa.text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: PostgreSQL READ COMMITTED isolation is required")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute(
            "LOCK TABLE foods, nutrition_catalog_identifiers, nutrition_import_drafts IN ACCESS EXCLUSIVE MODE"
        )
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE nutrition_import_drafts SET id = id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError("Unsafe downgrade: catalogue locking requires a transaction")
    else:
        raise RuntimeError("Unsafe downgrade: catalogue locking is unsupported")
    if (
        bind.execute(sa.text("SELECT 1 FROM nutrition_catalog_identifiers LIMIT 1")).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM nutrition_import_drafts WHERE catalog_receipt IS NOT NULL "
                "OR adapter_id IS NOT NULL OR catalog_confirm_key_hash IS NOT NULL "
                "OR catalog_confirm_fingerprint IS NOT NULL LIMIT 1"
            )
        ).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM foods WHERE food_type = 'system' AND source_name = 'yfc_community' LIMIT 1"
            )
        ).first()
    ):
        raise RuntimeError("Cannot discard catalogue import identity or receipt data")
    op.drop_column("nutrition_import_drafts", "catalog_receipt")
    op.drop_column("nutrition_import_drafts", "catalog_confirm_fingerprint")
    op.drop_column("nutrition_import_drafts", "catalog_confirm_key_hash")
    op.drop_column("nutrition_import_drafts", "adapter_id")
    op.drop_table("nutrition_catalog_identifiers")
