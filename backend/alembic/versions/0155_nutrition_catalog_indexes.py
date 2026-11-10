"""Build and verify catalogue uniqueness indexes without blocking writes."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0155_nutrition_catalog_indexes"
down_revision: str | None = "0154_nutrition_catalog_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Build and verify both unique indexes concurrently before catalogue writes."


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                "uq_foods_community_shared_identity",
                "foods",
                ["catalog_identity"],
                unique=True,
                postgresql_where=sa.text(
                    "catalog_identity IS NOT NULL AND food_type IN ('system', 'branded') "
                    "AND source_name = 'yfc_community'"
                ),
                postgresql_concurrently=True,
                if_not_exists=True,
            )
            valid_food = bind.execute(
                sa.text(
                    "SELECT indisvalid AND indisready AND indisunique "
                    "AND indrelid = 'foods'::regclass "
                    "AND indnkeyatts = 1 AND indnatts = 1 "
                    "AND pg_get_indexdef(indexrelid, 1, true) = 'catalog_identity' "
                    "AND pg_get_expr(indpred, indrelid) = "
                    "'((catalog_identity IS NOT NULL) AND ((food_type)::text = ANY "
                    "((ARRAY[''system''::character varying, ''branded''::character varying])::text[])) "
                    "AND ((source_name)::text = ''yfc_community''::text))' "
                    "FROM pg_index WHERE indexrelid = 'uq_foods_community_shared_identity'::regclass"
                )
            ).scalar_one()
            if not valid_food:
                raise RuntimeError(
                    "Catalogue identity index requires manual verification before recovery"
                )
            op.create_index(
                "uq_nutrition_import_owner_catalog_confirm",
                "nutrition_import_drafts",
                ["owner_user_id", "catalog_confirm_key_hash"],
                unique=True,
                postgresql_concurrently=True,
                if_not_exists=True,
            )
            valid_confirm = bind.execute(
                sa.text(
                    "SELECT indisvalid AND indisready AND indisunique "
                    "AND indrelid = 'nutrition_import_drafts'::regclass "
                    "AND indnkeyatts = 2 AND indnatts = 2 "
                    "AND pg_get_indexdef(indexrelid, 1, true) = 'owner_user_id' "
                    "AND pg_get_indexdef(indexrelid, 2, true) = 'catalog_confirm_key_hash' "
                    "AND indpred IS NULL "
                    "FROM pg_index WHERE indexrelid = 'uq_nutrition_import_owner_catalog_confirm'::regclass"
                )
            ).scalar_one()
            if not valid_confirm:
                raise RuntimeError(
                    "Catalogue confirmation index requires manual verification before recovery"
                )
    else:
        op.create_index(
            "uq_foods_community_shared_identity",
            "foods",
            ["catalog_identity"],
            unique=True,
            sqlite_where=sa.text(
                "catalog_identity IS NOT NULL AND food_type IN ('system', 'branded') "
                "AND source_name = 'yfc_community'"
            ),
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "uq_nutrition_import_owner_catalog_confirm",
            "nutrition_import_drafts",
            ["owner_user_id", "catalog_confirm_key_hash"],
            unique=True,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


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
                "SELECT 1 FROM nutrition_import_drafts WHERE catalog_receipt IS NOT NULL OR adapter_id IS NOT NULL LIMIT 1"
            )
        ).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM foods WHERE food_type = 'system' AND source_name = 'yfc_community' LIMIT 1"
            )
        ).first()
    ):
        raise RuntimeError("Cannot remove catalogue uniqueness while imported data exists")
    op.drop_index("uq_nutrition_import_owner_catalog_confirm", table_name="nutrition_import_drafts")
    op.drop_index("uq_foods_community_shared_identity", table_name="foods")
