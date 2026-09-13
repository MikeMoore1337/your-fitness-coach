"""Add basis-aware food facts and local nutrition-label draft/catalog lifecycle.

Revision ID: 0081_nutrition_label_catalog
Revises: 0080_program_import_doc_format
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0081_nutrition_label_catalog"
down_revision: str | None = "0080_program_import_doc_format"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds nullable canonical basis/provenance columns and creates empty owner-scoped draft and "
    "contribution tables; no populated-table rewrite, constraint change, default, or index on "
    "an existing table is performed during the expand rollout."
)


def upgrade() -> None:
    op.add_column(
        "foods",
        sa.Column("nutrition_basis_kind", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "foods",
        sa.Column("nutrition_basis_amount", sa.Numeric(precision=10, scale=3), nullable=True),
    )
    op.add_column(
        "foods",
        sa.Column("nutrition_basis_unit", sa.String(length=16), nullable=True),
    )
    op.add_column("foods", sa.Column("canonical_facts", sa.JSON(), nullable=True))
    op.add_column("foods", sa.Column("nutrition_provenance", sa.JSON(), nullable=True))
    op.add_column(
        "foods",
        sa.Column("canonical_complete", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "foods",
        sa.Column("catalog_quality", sa.String(length=24), nullable=True),
    )
    op.create_table(
        "nutrition_label_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("canonical_payload", sa.JSON(), nullable=False),
        sa.Column("product_name", sa.String(length=256), nullable=True),
        sa.Column("product_brand", sa.String(length=128), nullable=True),
        sa.Column("product_barcode", sa.String(length=14), nullable=True),
        sa.Column("confirmed_visibility", sa.String(length=24), nullable=True),
        sa.Column(
            "confirmed_food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("ocr_engine", sa.String(length=32), nullable=False),
        sa.Column("ocr_engine_version", sa.String(length=64), nullable=False),
        sa.Column("source_mime", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'cancelled', 'expired')",
            name="ck_nutrition_label_drafts_status",
        ),
        sa.CheckConstraint("revision > 0", name="ck_nutrition_label_drafts_revision"),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id", name="nutrition_label_drafts_user_id_fkey", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="nutrition_label_drafts_pkey"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_nutrition_label_drafts_user_idempotency"
        ),
    )
    op.create_index(
        "ix_nutrition_label_drafts_user_status",
        "nutrition_label_drafts",
        ["user_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_nutrition_label_drafts_expires_at", "nutrition_label_drafts", ["expires_at"]
    )

    op.create_table(
        "nutrition_catalog_contributions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey(
                "foods.id", name="nutrition_catalog_contributions_food_id_fkey", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "contributor_user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                name="nutrition_catalog_contributions_contributor_user_id_fkey",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "visibility",
            sa.String(length=24),
            nullable=False,
            server_default="share_to_yfc_catalog",
        ),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column("canonical_payload", sa.JSON(), nullable=False),
        sa.Column("source_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "state IN ('accepted', 'duplicate', 'conflict')",
            name="ck_nutrition_catalog_contributions_state",
        ),
        sa.CheckConstraint(
            "visibility = 'share_to_yfc_catalog'",
            name="ck_nutrition_catalog_contributions_visibility",
        ),
        sa.PrimaryKeyConstraint("id", name="nutrition_catalog_contributions_pkey"),
        sa.UniqueConstraint(
            "food_id",
            "payload_digest",
            name="uq_nutrition_catalog_contributions_food_digest",
        ),
    )
    op.create_index(
        "ix_nutrition_catalog_contributions_food_created",
        "nutrition_catalog_contributions",
        ["food_id", "created_at"],
    )
    op.create_index(
        "ix_nutrition_catalog_contributions_contributor_created",
        "nutrition_catalog_contributions",
        ["contributor_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_nutrition_catalog_contributions_contributor_created",
        table_name="nutrition_catalog_contributions",
    )
    op.drop_index(
        "ix_nutrition_catalog_contributions_food_created",
        table_name="nutrition_catalog_contributions",
    )
    op.drop_table("nutrition_catalog_contributions")
    op.drop_index("ix_nutrition_label_drafts_expires_at", table_name="nutrition_label_drafts")
    op.drop_index("ix_nutrition_label_drafts_user_status", table_name="nutrition_label_drafts")
    op.drop_table("nutrition_label_drafts")
    op.drop_column("foods", "catalog_quality")
    op.drop_column("foods", "canonical_complete")
    op.drop_column("foods", "nutrition_provenance")
    op.drop_column("foods", "canonical_facts")
    op.drop_column("foods", "nutrition_basis_unit")
    op.drop_column("foods", "nutrition_basis_amount")
    op.drop_column("foods", "nutrition_basis_kind")
