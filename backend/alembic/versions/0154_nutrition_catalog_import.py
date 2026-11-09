"""Add import catalogue identities and independent confirmation receipts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0154_nutrition_catalog_import"
down_revision: str | None = "0153_nutrition_import_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = (
    "Build the shared-food uniqueness index concurrently, then add nullable draft fields and "
    "an empty identifier mapping. Replace the legacy active-food constraint after validating "
    "its basis-aware replacement; existing food and diary rows are not rewritten."
)

_INDEX = "uq_foods_community_shared_identity"
_PREDICATE = (
    "catalog_identity IS NOT NULL AND food_type IN ('system', 'branded') "
    "AND source_name = 'yfc_community'"
)
_ACTIVE_LEGACY = (
    "status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
    "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
    "AND carbs_g_per_100g IS NOT NULL)"
)
_ACTIVE_CANONICAL = (
    _ACTIVE_LEGACY + " OR (canonical_complete IS TRUE AND canonical_facts IS NOT NULL "
    "AND nutrition_basis_kind IS NOT NULL "
    "AND nutrition_basis_kind IN ('per_100_g', 'per_100_ml', 'per_serving') "
    "AND (canonical_facts ->> 'source_basis') IS NOT NULL "
    "AND (canonical_facts ->> 'source_basis') IN ('per_100_g', 'per_100_ml', 'per_serving') "
    "AND (canonical_facts -> 'normalized_facts' -> 'energy_kcal' ->> 'basis_ref') IS NOT NULL "
    "AND (canonical_facts -> 'normalized_facts' -> 'energy_kcal' ->> 'basis_ref') = nutrition_basis_kind "
    "AND (canonical_facts -> 'normalized_facts' -> 'energy_kcal' ->> 'value') IS NOT NULL "
    "AND (canonical_facts -> 'normalized_facts' -> 'protein_g' ->> 'value') IS NOT NULL "
    "AND (canonical_facts -> 'normalized_facts' -> 'fat_g' ->> 'value') IS NOT NULL "
    "AND (canonical_facts -> 'normalized_facts' -> 'carbohydrate_g' ->> 'value') IS NOT NULL)"
)
_ACTIVE_COMPAT = _ACTIVE_LEGACY + " OR canonical_complete = true"
_COMMUNITY_COMPLETE = (
    "source_name IS NULL OR source_name <> 'yfc_community' OR " + _ACTIVE_CANONICAL
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            existing = bind.execute(
                sa.text(
                    "SELECT i.indisvalid, i.indisunique, i.indrelid = to_regclass('foods'), "
                    "pg_get_indexdef(i.indexrelid, 1, true) FROM pg_index i "
                    "JOIN pg_class c ON c.oid = i.indexrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = current_schema() AND c.relname = :name"
                ),
                {"name": _INDEX},
            ).one_or_none()
            if existing is not None and (
                existing[0]
                or not existing[1]
                or not existing[2]
                or existing[3] != "catalog_identity"
            ):
                raise RuntimeError(
                    "Existing catalogue index requires manual verification before recovery"
                )
            if existing is not None:
                op.drop_index(_INDEX, table_name="foods", postgresql_concurrently=True)
            op.create_index(
                _INDEX,
                "foods",
                ["catalog_identity"],
                unique=True,
                postgresql_concurrently=True,
                postgresql_where=sa.text(_PREDICATE),
            )
    else:
        op.create_index(
            _INDEX,
            "foods",
            ["catalog_identity"],
            unique=True,
            sqlite_where=sa.text(_PREDICATE),
        )

    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            f"ALTER TABLE foods ADD CONSTRAINT ck_foods_active_nutrients_v2 CHECK ({_ACTIVE_COMPAT}) NOT VALID"
        )
        op.execute("ALTER TABLE foods VALIDATE CONSTRAINT ck_foods_active_nutrients_v2")
        op.drop_constraint("ck_foods_active_nutrients", "foods", type_="check")
        op.execute(
            "ALTER TABLE foods RENAME CONSTRAINT ck_foods_active_nutrients_v2 TO ck_foods_active_nutrients"
        )
        op.execute(
            f"ALTER TABLE foods ADD CONSTRAINT ck_foods_community_nutrients CHECK ({_COMMUNITY_COMPLETE}) NOT VALID"
        )
        op.execute("ALTER TABLE foods VALIDATE CONSTRAINT ck_foods_community_nutrients")
    else:
        with op.batch_alter_table("foods") as batch:
            batch.drop_constraint("ck_foods_active_nutrients", type_="check")
            batch.create_check_constraint("ck_foods_active_nutrients", _ACTIVE_COMPAT)
            batch.create_check_constraint("ck_foods_community_nutrients", _COMMUNITY_COMPLETE)

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
    with op.batch_alter_table("nutrition_import_drafts") as batch:
        batch.add_column(sa.Column("adapter_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("catalog_confirm_key_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("catalog_confirm_fingerprint", sa.String(64), nullable=True))
        batch.add_column(sa.Column("catalog_receipt", sa.JSON(), nullable=True))
        batch.create_unique_constraint(
            "uq_nutrition_import_owner_catalog_confirm",
            ["owner_user_id", "catalog_confirm_key_hash"],
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
        or bind.execute(
            sa.text(
                "SELECT 1 FROM foods WHERE status = 'active' AND (energy_kcal_per_100g IS NULL "
                "OR protein_g_per_100g IS NULL OR fat_g_per_100g IS NULL OR carbs_g_per_100g IS NULL) LIMIT 1"
            )
        ).first()
    ):
        raise RuntimeError("Cannot discard catalogue import identity or receipt data")
    with op.batch_alter_table("nutrition_import_drafts") as batch:
        batch.drop_constraint("uq_nutrition_import_owner_catalog_confirm", type_="unique")
        batch.drop_column("catalog_receipt")
        batch.drop_column("catalog_confirm_fingerprint")
        batch.drop_column("catalog_confirm_key_hash")
        batch.drop_column("adapter_id")
    op.drop_table("nutrition_catalog_identifiers")
    with op.batch_alter_table("foods") as batch:
        batch.drop_constraint("ck_foods_community_nutrients", type_="check")
        batch.drop_constraint("ck_foods_active_nutrients", type_="check")
        batch.create_check_constraint("ck_foods_active_nutrients", _ACTIVE_LEGACY)
    op.drop_index(_INDEX, table_name="foods")
