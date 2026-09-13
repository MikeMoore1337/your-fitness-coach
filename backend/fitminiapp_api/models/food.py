from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


def normalize_food_search_text(name: str, brand: str | None) -> str:
    normalized = " ".join(" ".join(part for part in (name, brand or "") if part).split())
    return normalized.casefold().replace("ё", "е")


class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_foods_name_not_blank"),
        CheckConstraint(
            "food_type IN ('system', 'branded', 'user')",
            name="ck_foods_food_type",
        ),
        CheckConstraint(
            "provenance IN ('internal', 'external', 'user', 'user_confirmed_package')",
            name="ck_foods_provenance",
        ),
        CheckConstraint(
            "trust_level IN ('verified', 'unverified')",
            name="ck_foods_trust_level",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'disabled')",
            name="ck_foods_status",
        ),
        CheckConstraint(
            "(food_type = 'user' AND owner_user_id IS NOT NULL AND provenance = 'user') "
            "OR (food_type <> 'user' AND owner_user_id IS NULL AND provenance <> 'user')",
            name="ck_foods_owner_scope",
        ),
        CheckConstraint(
            "food_type = 'user' OR (source_name IS NOT NULL AND length(trim(source_name)) > 0)",
            name="ck_foods_catalog_source",
        ),
        CheckConstraint(
            "provenance <> 'external' OR "
            "(source_name IS NOT NULL AND length(trim(source_name)) > 0 "
            "AND external_id IS NOT NULL AND length(trim(external_id)) > 0 "
            "AND source_license IS NOT NULL AND length(trim(source_license)) > 0 "
            "AND source_url IS NOT NULL AND length(trim(source_url)) > 0 "
            "AND source_license_url IS NOT NULL AND length(trim(source_license_url)) > 0)",
            name="ck_foods_external_source",
        ),
        CheckConstraint(
            "barcode IS NULL OR length(barcode) IN (8, 12, 13, 14)",
            name="ck_foods_barcode_length",
        ),
        CheckConstraint(
            "standard_serving_amount IS NULL AND standard_serving_unit IS NULL "
            "AND standard_serving_weight_g IS NULL OR "
            "standard_serving_amount > 0 AND "
            "standard_serving_unit IN ('g', 'ml', 'piece', 'serving') AND "
            "(standard_serving_unit IN ('ml', 'serving') OR standard_serving_weight_g > 0)",
            name="ck_foods_standard_serving_complete",
        ),
        CheckConstraint(
            "standard_serving_unit IS NULL OR standard_serving_unit <> 'g' "
            "OR standard_serving_amount = standard_serving_weight_g",
            name="ck_foods_gram_serving_weight",
        ),
        CheckConstraint(
            "energy_kcal_per_100g IS NULL OR energy_kcal_per_100g BETWEEN 0 AND 1000",
            name="ck_foods_energy_non_negative",
        ),
        CheckConstraint(
            "protein_g_per_100g IS NULL OR protein_g_per_100g BETWEEN 0 AND 100",
            name="ck_foods_protein_range",
        ),
        CheckConstraint(
            "fat_g_per_100g IS NULL OR fat_g_per_100g BETWEEN 0 AND 100",
            name="ck_foods_fat_range",
        ),
        CheckConstraint(
            "carbs_g_per_100g IS NULL OR carbs_g_per_100g BETWEEN 0 AND 100",
            name="ck_foods_carbs_range",
        ),
        CheckConstraint(
            "fiber_g_per_100g IS NULL OR fiber_g_per_100g BETWEEN 0 AND 100",
            name="ck_foods_fiber_range",
        ),
        CheckConstraint(
            "status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
            "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
            "AND carbs_g_per_100g IS NOT NULL) OR canonical_complete = true",
            name="ck_foods_active_nutrients",
        ),
        CheckConstraint(
            "food_type = 'user' OR status <> 'active' OR trust_level = 'verified' "
            "OR catalog_quality = 'community_unverified'",
            name="ck_foods_active_catalog_trust",
        ),
        CheckConstraint(
            "catalog_quality IN ('private', 'verified', 'community_unverified')",
            name="ck_foods_catalog_quality",
        ),
        CheckConstraint(
            "nutrition_basis_kind IN ('per_100_g', 'per_100_ml', 'per_serving')",
            name="ck_foods_nutrition_basis_kind",
        ),
        CheckConstraint(
            "nutrition_basis_unit IN ('g', 'ml', 'serving')",
            name="ck_foods_nutrition_basis_unit",
        ),
        CheckConstraint(
            "(nutrition_basis_kind = 'per_100_g' AND nutrition_basis_unit = 'g' "
            "AND nutrition_basis_amount = 100) OR "
            "(nutrition_basis_kind = 'per_100_ml' AND nutrition_basis_unit = 'ml' "
            "AND nutrition_basis_amount = 100) OR "
            "(nutrition_basis_kind = 'per_serving' AND nutrition_basis_unit = 'serving' "
            "AND nutrition_basis_amount = 1)",
            name="ck_foods_nutrition_basis_shape",
        ),
        Index("ix_foods_owner_status", "owner_user_id", "status"),
        Index("ix_foods_status_type_name", "status", "food_type", "name"),
        Index(
            "ix_foods_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        Index(
            "uq_foods_catalog_barcode",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL AND food_type <> 'user'"),
            sqlite_where=text("barcode IS NOT NULL AND food_type <> 'user'"),
        ),
        Index(
            "uq_foods_user_barcode",
            "owner_user_id",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL AND food_type = 'user'"),
            sqlite_where=text("barcode IS NOT NULL AND food_type = 'user'"),
        ),
        Index(
            "uq_foods_external_source_id",
            "source_name",
            "external_id",
            unique=True,
            postgresql_where=text("provenance = 'external'"),
            sqlite_where=text("provenance = 'external'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(14), nullable=True)
    search_text: Mapped[str] = mapped_column(String(1024), nullable=False, default="")

    energy_kcal_per_100g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    protein_g_per_100g: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    fat_g_per_100g: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    carbs_g_per_100g: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    fiber_g_per_100g: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)

    # The legacy columns above remain the read-compatible 100 g projection.  The
    # canonical JSON keeps source/normalized/derived values and makes 100 ml and
    # serving-only labels first-class without pretending they are per-100-g facts.
    nutrition_basis_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="per_100_g", server_default="per_100_g"
    )
    nutrition_basis_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), nullable=False, default=Decimal("100"), server_default="100"
    )
    nutrition_basis_unit: Mapped[str] = mapped_column(
        String(16), nullable=False, default="g", server_default="g"
    )
    canonical_facts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    nutrition_provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    canonical_complete: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default="true"
    )
    catalog_quality: Mapped[str] = mapped_column(
        String(24), nullable=False, default="verified", server_default="verified"
    )

    standard_serving_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    standard_serving_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    standard_serving_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)

    food_type: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    # The applied food schema keeps the historical 16-character provenance column. The
    # additive canonical_provenance column carries the expanded API/domain values; the
    # legacy column is retained for old constraints and indexes during the online rollout.
    provenance: Mapped[str | None] = mapped_column(
        "canonical_provenance", String(32), nullable=True
    )
    legacy_provenance: Mapped[str] = mapped_column("provenance", String(16), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_license: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_license_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trust_level: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
        onupdate=now_msk_naive,
    )


class FoodFavorite(Base):
    __tablename__ = "food_favorites"
    __table_args__ = (
        Index(
            "ix_food_favorites_user_created",
            "user_id",
            "created_at",
            "food_id",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
    )


@event.listens_for(Food, "before_insert")
@event.listens_for(Food, "before_update")
def _set_food_search_text(_mapper: object, _connection: object, target: Food) -> None:
    target.search_text = normalize_food_search_text(target.name, target.brand)
    if target.provenance is None:
        target.legacy_provenance = target.legacy_provenance or "internal"
    elif target.provenance == "user_confirmed_package":
        target.legacy_provenance = "internal"
    else:
        target.legacy_provenance = target.provenance
