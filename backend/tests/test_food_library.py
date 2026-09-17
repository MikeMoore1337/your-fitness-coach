from __future__ import annotations

import importlib.util
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, inspect

from fitminiapp_api import main as main_module
from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.db.performance import begin_sql_metrics, current_sql_metrics, reset_sql_metrics
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food import Food, normalize_food_catalog_identity
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_label import NutritionCatalogContribution
from fitminiapp_api.models.user import User
from fitminiapp_api.services.foods import search_foods


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "is_coach": False,
            "is_admin": False,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _food_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Домашний йогурт",
        "brand": "Моя кухня",
        "energy_kcal_per_100g": "88.4",
        "protein_g_per_100g": "3.1",
        "fat_g_per_100g": "1.7",
        "carbs_g_per_100g": "15.0",
        "fiber_g_per_100g": "1.8",
        "standard_serving_amount": "1",
        "standard_serving_unit": "serving",
        "standard_serving_weight_g": "250",
    }
    payload.update(overrides)
    return payload


def _catalog_food(name: str, food_type: str, *, brand: str | None = None) -> Food:
    return Food(
        name=name,
        brand=brand,
        energy_kcal_per_100g=Decimal("100"),
        protein_g_per_100g=Decimal("5"),
        fat_g_per_100g=Decimal("3"),
        carbs_g_per_100g=Decimal("12"),
        food_type=food_type,
        owner_user_id=None,
        provenance="internal",
        source_name="yfc-test",
        trust_level="verified",
        status="active",
    )


def test_personal_food_api_crud_is_private_and_can_feed_diary_without_external_source(
    client,
) -> None:
    owner_headers = _auth(client, 17_001)
    other_headers = _auth(client, 17_002)

    created = client.post(
        "/api/v1/nutrition/foods",
        headers=owner_headers,
        json=_food_payload(barcode="4006381333931"),
    )
    assert created.status_code == 201
    food_id = created.json()["id"]
    assert created.json()["food_type"] == "user"
    assert created.json()["is_favorite"] is False

    assert (
        client.get(f"/api/v1/nutrition/foods/{food_id}", headers=owner_headers).status_code == 200
    )
    assert (
        client.get(f"/api/v1/nutrition/foods/{food_id}", headers=other_headers).status_code == 404
    )
    assert (
        client.patch(
            f"/api/v1/nutrition/foods/{food_id}",
            headers=other_headers,
            json={"name": "Чужое изменение"},
        ).status_code
        == 404
    )

    updated = client.patch(
        f"/api/v1/nutrition/foods/{food_id}",
        headers=owner_headers,
        json={
            "name": "Йогурт домашний",
            "brand": None,
            "standard_serving_amount": None,
            "standard_serving_unit": None,
            "standard_serving_weight_g": None,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Йогурт домашний"
    assert updated.json()["brand"] is None
    assert updated.json()["standard_serving_weight_g"] is None

    duplicate = client.post(
        "/api/v1/nutrition/foods",
        headers=owner_headers,
        json=_food_payload(name="Дубликат", barcode="4006381333931"),
    )
    assert duplicate.status_code == 409
    assert (
        client.post(
            "/api/v1/nutrition/foods",
            headers=other_headers,
            json=_food_payload(name="Такой же штрихкод", barcode="4006381333931"),
        ).status_code
        == 201
    )

    today = timezone_module.today_in_timezone("Europe/Moscow")
    diary_entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=owner_headers,
        json={
            "food_id": food_id,
            "diary_date": today.isoformat(),
            "meal_type": "breakfast",
            "amount": "125",
        },
    )
    assert diary_entry.status_code == 201
    assert diary_entry.json()["food_name"] == "Йогурт домашний"

    assert (
        client.delete(f"/api/v1/nutrition/foods/{food_id}", headers=other_headers).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/nutrition/foods/{food_id}", headers=owner_headers).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/nutrition/foods/{food_id}", headers=owner_headers).status_code == 404
    )


def test_favorites_recent_order_and_cross_user_isolation(client) -> None:
    owner_headers = _auth(client, 17_010)
    other_headers = _auth(client, 17_011)
    first_id = client.post(
        "/api/v1/nutrition/foods",
        headers=owner_headers,
        json=_food_payload(name="первый йогурт", barcode=None),
    ).json()["id"]
    second_id = client.post(
        "/api/v1/nutrition/foods",
        headers=owner_headers,
        json=_food_payload(name="второй йогурт", barcode=None),
    ).json()["id"]
    foreign_id = client.post(
        "/api/v1/nutrition/foods",
        headers=other_headers,
        json=_food_payload(name="чужой йогурт", barcode=None),
    ).json()["id"]

    assert (
        client.put(
            f"/api/v1/nutrition/foods/{first_id}/favorite", headers=owner_headers
        ).status_code
        == 200
    )
    repeated = client.put(
        f"/api/v1/nutrition/foods/{first_id}/favorite",
        headers=owner_headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["is_favorite"] is True
    assert (
        client.put(
            f"/api/v1/nutrition/foods/{foreign_id}/favorite", headers=owner_headers
        ).status_code
        == 404
    )

    today = timezone_module.today_in_timezone("Europe/Moscow").isoformat()
    entry_ids = []
    for food_id in (first_id, second_id):
        response = client.post(
            "/api/v1/nutrition/diary/entries",
            headers=owner_headers,
            json={
                "food_id": food_id,
                "diary_date": today,
                "meal_type": "snacks",
                "amount": "100",
            },
        )
        assert response.status_code == 201
        entry_ids.append(response.json()["id"])
    client.post(
        "/api/v1/nutrition/diary/entries",
        headers=other_headers,
        json={
            "food_id": foreign_id,
            "diary_date": today,
            "meal_type": "snacks",
            "amount": "100",
        },
    )
    with get_session_context() as db:
        first_entry = db.get(FoodDiaryEntry, entry_ids[0])
        second_entry = db.get(FoodDiaryEntry, entry_ids[1])
        assert first_entry is not None and second_entry is not None
        first_entry.diary_date = date(2026, 8, 18)
        first_entry.logged_at = time(23, 0)
        first_entry.updated_at = datetime(2026, 8, 20, 10, 0)
        second_entry.diary_date = date(2026, 8, 19)
        second_entry.logged_at = time(7, 0)
        second_entry.updated_at = datetime(2026, 8, 1, 11, 0)

    recent = client.get("/api/v1/nutrition/foods/recent", headers=owner_headers)
    assert recent.status_code == 200
    assert [item["id"] for item in recent.json()["items"]] == [second_id, first_id]
    assert foreign_id not in {item["id"] for item in recent.json()["items"]}
    frequent = client.get("/api/v1/nutrition/foods/frequent", headers=owner_headers)
    assert frequent.status_code == 200
    assert [item["id"] for item in frequent.json()["items"]] == [second_id, first_id]
    search = client.get(
        "/api/v1/nutrition/foods/search",
        headers=owner_headers,
        params={"q": "йогурт"},
    ).json()
    assert {item["id"] for item in search["items"]} == {first_id, second_id}

    favorites = client.get("/api/v1/nutrition/foods/favorites", headers=owner_headers)
    assert favorites.status_code == 200
    assert [item["id"] for item in favorites.json()["items"]] == [first_id]
    assert (
        client.delete(
            f"/api/v1/nutrition/foods/{first_id}/favorite",
            headers=owner_headers,
        ).status_code
        == 204
    )
    assert (
        client.get("/api/v1/nutrition/foods/favorites", headers=owner_headers).json()["total"] == 0
    )


def test_commercial_food_reuses_shared_identity_and_keeps_conflicts_private(client) -> None:
    owner_headers = _auth(client, 17_003)
    other_headers = _auth(client, 17_004)
    commercial = _food_payload(
        name="Йогурт клубника",
        brand="YFC Test",
        classification="commercial",
        barcode=None,
    )

    first = client.post("/api/v1/nutrition/foods", headers=owner_headers, json=commercial)
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["food_type"] == "branded"
    assert first_body["catalog_quality"] == "community_unverified"
    assert first_body["catalog_contribution_state"] == "accepted"
    assert first_body["catalog_contribution_outcome"] == "created"

    duplicate = client.post("/api/v1/nutrition/foods", headers=other_headers, json=commercial)
    assert duplicate.status_code == 201, duplicate.text
    duplicate_body = duplicate.json()
    assert duplicate_body["id"] == first_body["id"]
    assert duplicate_body["catalog_contribution_state"] == "duplicate"
    assert duplicate_body["catalog_contribution_outcome"] == "duplicate"

    gtin_bridge = client.post(
        "/api/v1/nutrition/foods",
        headers=other_headers,
        json={**commercial, "barcode": "4006381333931"},
    )
    assert gtin_bridge.status_code == 201, gtin_bridge.text
    assert gtin_bridge.json()["id"] == first_body["id"]
    assert gtin_bridge.json()["catalog_contribution_outcome"] == "reused"
    assert gtin_bridge.json()["barcode"] == "4006381333931"

    variant = client.post(
        "/api/v1/nutrition/foods",
        headers=other_headers,
        json={**commercial, "name": "Йогурт ваниль"},
    )
    assert variant.status_code == 201, variant.text
    assert variant.json()["id"] != first_body["id"]
    assert variant.json()["catalog_contribution_outcome"] == "created"

    visible = client.get(
        "/api/v1/nutrition/foods/search",
        headers=other_headers,
        params={"q": "йогурт клубника"},
    )
    assert visible.status_code == 200
    assert visible.json()["items"][0]["id"] == first_body["id"]

    conflict = client.post(
        "/api/v1/nutrition/foods",
        headers=other_headers,
        json={**commercial, "energy_kcal_per_100g": "99"},
    )
    assert conflict.status_code == 201, conflict.text
    conflict_body = conflict.json()
    assert conflict_body["id"] != first_body["id"]
    assert conflict_body["food_type"] == "user"
    assert conflict_body["catalog_quality"] == "private"
    assert conflict_body["catalog_contribution_state"] == "conflict"
    assert conflict_body["catalog_contribution_outcome"] == "conflict"
    assert (
        client.get(
            f"/api/v1/nutrition/foods/{conflict_body['id']}", headers=owner_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/nutrition/foods/{conflict_body['id']}", headers=other_headers
        ).status_code
        == 200
    )

    with get_session_context() as db:
        shared = db.get(Food, first_body["id"])
        assert shared is not None
        assert shared.energy_kcal_per_100g == Decimal("88.40")
        contribution_states = [
            row.state
            for row in db.query(NutritionCatalogContribution)
            .order_by(NutritionCatalogContribution.id)
            .all()
        ]
        assert contribution_states == ["accepted", "accepted", "accepted", "conflict"]

    personal = client.post(
        "/api/v1/nutrition/foods",
        headers=owner_headers,
        json=_food_payload(name="Моя каша", classification="personal", barcode=None),
    )
    assert personal.status_code == 201, personal.text
    personal_id = personal.json()["id"]
    assert personal.json()["food_type"] == "user"
    assert personal.json()["catalog_quality"] == "private"
    assert personal_id in {
        item["id"]
        for item in client.get("/api/v1/nutrition/foods/mine", headers=owner_headers).json()[
            "items"
        ]
    }
    assert personal_id not in {
        item["id"]
        for item in client.get("/api/v1/nutrition/foods/mine", headers=other_headers).json()[
            "items"
        ]
    }

    gtin_payload = _food_payload(
        name="Молочный напиток",
        brand="GTIN Test",
        classification="commercial",
        barcode="4006381333931",
    )
    gtin_first = client.post("/api/v1/nutrition/foods", headers=owner_headers, json=gtin_payload)
    assert gtin_first.status_code == 201, gtin_first.text
    gtin_second = client.post(
        "/api/v1/nutrition/foods",
        headers=other_headers,
        json={**gtin_payload, "name": "Другое название"},
    )
    assert gtin_second.status_code == 201, gtin_second.text
    assert gtin_second.json()["id"] == gtin_first.json()["id"]


def test_catalog_identity_does_not_collide_on_user_separators() -> None:
    first = normalize_food_catalog_identity(
        "Продукт|Ваниль",
        "Бренд",
        "per_100_g",
        Decimal("100"),
        "g",
    )
    second = normalize_food_catalog_identity(
        "Ваниль",
        "Бренд|Продукт",
        "per_100_g",
        Decimal("100"),
        "g",
    )
    assert first != second


def test_local_search_ranking_normalization_pagination_and_query_bound(client) -> None:
    headers = _auth(client, 17_020)
    recent_id = client.post(
        "/api/v1/nutrition/foods",
        headers=headers,
        json=_food_payload(name="недавний йогурт", barcode=None),
    ).json()["id"]
    own_id = client.post(
        "/api/v1/nutrition/foods",
        headers=headers,
        json=_food_payload(name="йогурт", barcode=None),
    ).json()["id"]
    with get_session_context() as db:
        favorite = _catalog_food("избранный йогурт", "branded", brand="Локальная марка")
        system = _catalog_food("йогурт", "system")
        branded = _catalog_food("брендовый йогурт", "branded")
        db.add_all([favorite, system, branded])
        db.flush()
        favorite_id, system_id, branded_id = favorite.id, system.id, branded.id

    assert (
        client.put(f"/api/v1/nutrition/foods/{favorite_id}/favorite", headers=headers).status_code
        == 200
    )
    today = timezone_module.today_in_timezone("Europe/Moscow").isoformat()
    assert (
        client.post(
            "/api/v1/nutrition/diary/entries",
            headers=headers,
            json={
                "food_id": recent_id,
                "diary_date": today,
                "meal_type": "lunch",
                "amount": "100",
            },
        ).status_code
        == 201
    )

    response = client.get(
        "/api/v1/nutrition/foods/search",
        headers=headers,
        params={"q": "  ЙОГУРТ  ", "limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 5
    assert [item["id"] for item in response.json()["items"]] == [
        own_id,
        recent_id,
        favorite_id,
        system_id,
        branded_id,
    ]
    page = client.get(
        "/api/v1/nutrition/foods/search",
        headers=headers,
        params={"q": "йогурт", "limit": 2, "offset": 2},
    ).json()
    assert page["total"] == 5
    assert [item["id"] for item in page["items"]] == [favorite_id, system_id]
    assert (
        client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "я"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "йогурт", "limit": 51},
        ).status_code
        == 422
    )

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 17_020).one()
        token = begin_sql_metrics()
        try:
            direct = search_foods(db, user, "йогурт", limit=20, offset=0)
            metrics = current_sql_metrics()
        finally:
            reset_sql_metrics(token)
    assert direct.total == 5
    assert metrics.query_count == 2


def test_local_search_normalizes_yo_and_recovers_one_simple_typo(client) -> None:
    headers = _auth(client, 17_021)
    yo_id = client.post(
        "/api/v1/nutrition/foods",
        headers=headers,
        json=_food_payload(name="Тёртый сыр", barcode=None),
    ).json()["id"]
    typo_id = client.post(
        "/api/v1/nutrition/foods",
        headers=headers,
        json=_food_payload(name="Гречневая каша", barcode=None),
    ).json()["id"]

    yo_search = client.get(
        "/api/v1/nutrition/foods/search",
        headers=headers,
        params={"q": "  ТЕРТЫЙ  "},
    )
    assert yo_search.status_code == 200
    assert yo_id in {item["id"] for item in yo_search.json()["items"]}

    typo_search = client.get(
        "/api/v1/nutrition/foods/search",
        headers=headers,
        params={"q": "гречнева"},
    )
    assert typo_search.status_code == 200
    assert [item["id"] for item in typo_search.json()["items"]] == [typo_id]


def test_food_library_migration_upgrades_from_diary_head(tmp_path: Path) -> None:
    migration_path = (
        Path(main_module.__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0036_food_library_search.py"
    )
    spec = importlib.util.spec_from_file_location("food_library_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "0035_food_diary"

    engine = create_engine(f"sqlite:///{(tmp_path / 'food-library-migration.db').as_posix()}")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "foods",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(256), nullable=False),
        Column("brand", String(128), nullable=True),
        Column("status", String(16), nullable=False),
        Column("food_type", String(16), nullable=False),
    )
    Table(
        "food_diary_entries",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, nullable=False),
        Column("food_id", Integer, nullable=True),
        Column("updated_at", DateTime, nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            metadata.tables["foods"].insert(),
            {
                "id": 1,
                "name": "Oat YOGURT",
                "brand": "Brand",
                "status": "active",
                "food_type": "system",
            },
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        schema = inspect(connection)
        assert "food_favorites" in schema.get_table_names()
        assert "search_text" in {column["name"] for column in schema.get_columns("foods")}
        assert {index["name"] for index in schema.get_indexes("food_favorites")} == {
            "ix_food_favorites_user_created"
        }
        assert "ix_food_diary_entries_user_food_updated" in {
            index["name"] for index in schema.get_indexes("food_diary_entries")
        }
        assert "ix_foods_status_type_name" in {
            index["name"] for index in schema.get_indexes("foods")
        }
        upgraded_foods = Table("foods", MetaData(), autoload_with=connection)
        assert (
            connection.execute(
                upgraded_foods.select().with_only_columns(upgraded_foods.c.search_text)
            ).scalar_one()
            == "oat yogurt brand"
        )
        migration.downgrade()
        assert "food_favorites" not in inspect(connection).get_table_names()
        assert "search_text" not in {
            column["name"] for column in inspect(connection).get_columns("foods")
        }

    engine.dispose()


def test_catalog_identity_migration_is_additive_and_reversible(tmp_path: Path) -> None:
    migration_path = (
        Path(main_module.__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0089_nutrition_catalog_identity.py"
    )
    spec = importlib.util.spec_from_file_location("catalog_identity_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "0088_ai_coach_durable_quota"

    engine = create_engine(f"sqlite:///{(tmp_path / 'catalog-identity.db').as_posix()}")
    metadata = MetaData()
    Table(
        "foods",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("food_type", String(16), nullable=False),
        Column("source_name", String(64), nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        schema = inspect(connection)
        assert "catalog_identity" in {column["name"] for column in schema.get_columns("foods")}
        assert {index["name"] for index in schema.get_indexes("foods")} == {
            "ix_foods_catalog_identity",
            "uq_foods_community_catalog_identity",
        }
        migration.downgrade()
        schema = inspect(connection)
        assert "catalog_identity" not in {column["name"] for column in schema.get_columns("foods")}
        assert not schema.get_indexes("foods")

    engine.dispose()
