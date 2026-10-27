"""Add an exact identity for community commercial foods.

The identity is additive and nullable so existing private, verified and
external catalog rows remain untouched. New community rows use the identity to
deduplicate no-GTIN submissions without fuzzy merging.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0089_nutrition_catalog_identity"
down_revision: str | None = "0088_ai_coach_durable_quota"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds a nullable identity for new YFC community commercial foods. Existing rows are not "
    "rewritten; PostgreSQL builds the two existing-table indexes concurrently in an autocommit "
    "block, and the application keeps an exact legacy fallback for older community rows."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # PostgreSQL cannot build an index on the populated foods table inside
        # the Alembic transaction without taking a table-wide write lock.
        # The autocommit block is required by CREATE INDEX CONCURRENTLY.
        op.add_column(
            "foods",
            sa.Column("catalog_identity", sa.String(length=512), nullable=True),
            if_not_exists=True,
        )
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_foods_catalog_identity",
                "foods",
                ["catalog_identity"],
                postgresql_concurrently=True,
                if_not_exists=True,
            )
            op.create_index(
                "uq_foods_community_catalog_identity",
                "foods",
                ["catalog_identity"],
                unique=True,
                postgresql_concurrently=True,
                if_not_exists=True,
                postgresql_where=sa.text(
                    "catalog_identity IS NOT NULL AND food_type = 'branded' "
                    "AND source_name = 'yfc_community'"
                ),
            )
    else:
        op.add_column("foods", sa.Column("catalog_identity", sa.String(length=512), nullable=True))
        op.create_index(
            "ix_foods_catalog_identity",
            "foods",
            ["catalog_identity"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "uq_foods_community_catalog_identity",
            "foods",
            ["catalog_identity"],
            unique=True,
            postgresql_concurrently=True,
            if_not_exists=True,
            sqlite_where=sa.text(
                "catalog_identity IS NOT NULL AND food_type = 'branded' "
                "AND source_name = 'yfc_community'"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(
                "uq_foods_community_catalog_identity",
                table_name="foods",
                postgresql_concurrently=True,
                if_exists=True,
            )
            op.drop_index(
                "ix_foods_catalog_identity",
                table_name="foods",
                postgresql_concurrently=True,
                if_exists=True,
            )
    else:
        op.drop_index("uq_foods_community_catalog_identity", table_name="foods", if_exists=True)
        op.drop_index("ix_foods_catalog_identity", table_name="foods", if_exists=True)
    op.drop_column("foods", "catalog_identity")
