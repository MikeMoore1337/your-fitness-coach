import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from time import perf_counter

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from test_training_analytics import _auth, _user_id

from fitminiapp_api.api.v1 import nutrition_imports
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_label import (
    NutritionCatalogContribution,
    NutritionCatalogIdentifier,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import NutritionImportV1
from fitminiapp_api.services.accounts import delete_user_cascade
from fitminiapp_api.services.foods import FoodError, calculate_food_amount, search_foods
from fitminiapp_api.services.jwt import decode_token
from fitminiapp_api.services.nutrition_catalog_import import (
    catalog_import_preview,
    confirm_catalog_alias,
    confirm_catalog_import,
    list_catalog_conflicts,
    prepare_catalog_food,
)
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    create_nutrition_import_draft,
)
from fitminiapp_api.services.nutrition_import_runner import ADAPTERS, NutritionImportAdapter
from fitminiapp_api.services.token_service import revoke_refresh_token_family

FIXTURE = Path(__file__).parent / "fixtures" / "nutrition_import" / "neutral-golden.json"


def test_catalog_preparation_requires_trusted_rights_complete_facts_and_known_serving():
    document = NutritionImportV1.model_validate_json(FIXTURE.read_bytes())
    row = document.rows[0].model_dump(mode="json")
    row["nutrition"]["facts"]["fat_g"] = {"value": "1.2", "unit": "g", "evidence": "read"}
    row["nutrition"]["facts"]["carbohydrate_g"] = {"value": "2.3", "unit": "g", "evidence": "read"}
    row_type = type(document.rows[0])
    allowed = frozenset({"owner_reported"})

    def prepare(value, rights=allowed):
        return prepare_catalog_food(
            row_type.model_validate(value),
            document.source,
            allowed_publication_rights=rights,
            allowed_food_kinds=frozenset({"standard_food", "branded_food"}),
        )

    candidate = prepare(row)
    assert candidate.outcome == "publish"
    assert candidate.food.kind == "standard_food"
    assert candidate.food.canonical.normalized_facts.protein_g.value == 0
    assert candidate.food.provenance["publication_rights"] == "owner_reported"
    assert "diary_date" not in str(candidate.food.provenance)
    assert prepare(row, frozenset()).reason == "publication_rights_unconfirmed"

    branded = deepcopy(row)
    branded["food"] = {
        "name": "Йогурт",
        "brand": "Бренд",
        "variant": "Ваниль",
        "kind": "branded_food",
    }
    first = prepare(branded)
    branded["food"]["variant"] = "Клубника"
    second = prepare(branded)
    assert first.outcome == second.outcome == "publish"
    assert first.food.identity != second.food.identity

    serving = deepcopy(row)
    serving["nutrition"]["basis"] = "per_serving"
    assert prepare(serving).reason == "serving_measure_unknown"
    serving["serving_measure"] = {"amount": "125", "unit": "g"}
    serving_candidate = prepare(serving)
    assert serving_candidate.outcome == "publish"
    serving_food = Food(canonical_facts=serving_candidate.food.canonical.model_dump(mode="json"))
    assert calculate_food_amount(serving_food, Decimal("250"), "g").energy_kcal == Decimal("24.60")
    assert calculate_food_amount(serving_food, Decimal("2"), "serving").energy_kcal == Decimal(
        "24.60"
    )
    with pytest.raises(FoodError, match="grams and millilitres"):
        calculate_food_amount(serving_food, Decimal("250"), "ml")
    serving["serving_measure"]["unit"] = "ml"
    ml_candidate = prepare(serving)
    ml_food = Food(canonical_facts=ml_candidate.food.canonical.model_dump(mode="json"))
    assert calculate_food_amount(ml_food, Decimal("250"), "ml").energy_kcal == Decimal("24.60")
    serving["nutrition"]["basis"] = "per_100_ml"
    assert prepare(serving).outcome == "publish"
    serving["nutrition"]["facts"]["protein_g"]["value"] = "120"
    serving["nutrition"]["facts"]["energy_kcal"]["value"] = "500"
    assert prepare(serving).outcome == "publish"
    serving["nutrition"]["basis"] = "per_serving"
    assert prepare(serving).outcome == "publish"

    incomplete = deepcopy(row)
    incomplete["nutrition"]["facts"]["fat_g"] = None
    assert prepare(incomplete).reason == "incomplete_nutrition"
    recipe = deepcopy(row)
    recipe["food"]["kind"] = "personal_recipe"
    assert prepare(recipe).outcome == "private_only"
    unsafe = deepcopy(row)
    unsafe["food"]["name"] = "https://example.test/private"
    assert prepare(unsafe).reason == "unsafe_product_text"


def test_catalog_publish_search_reuse_conflict_and_diary_isolation(client, monkeypatch):
    _auth(client, 983001)
    _auth(client, 983002)
    _auth(client, 983003)
    adapter = NutritionImportAdapter(
        "fatsecret",
        "synthetic-v1",
        "synthetic-v1",
        ",",
        FIXTURE,
        catalog_source="diary_export",
        catalog_publication_rights=frozenset({"owner_reported"}),
        catalog_food_kinds=frozenset({"standard_food", "branded_food"}),
        catalog_source_versions=frozenset({None}),
    )
    monkeypatch.setitem(ADAPTERS, "synthetic-catalog", adapter)
    document = NutritionImportV1.model_validate_json(FIXTURE.read_bytes()).model_dump(mode="json")
    document["rows"] = [document["rows"][0]]
    facts = document["rows"][0]["nutrition"]["facts"]
    facts["fat_g"] = {"value": "1.2", "unit": "g", "evidence": "read"}
    facts["carbohydrate_g"] = {"value": "2.3", "unit": "g", "evidence": "read"}

    def create(db, user, key, data=document):
        return create_nutrition_import_draft(
            db,
            user,
            document=NutritionImportV1.model_validate(data),
            source=b"name,amount\nsynthetic,100\n",
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="synthetic-v1",
            upload_key=key,
            adapter_id="synthetic-catalog",
        )

    def confirm(db, user, draft, preview, key):
        return confirm_catalog_import(
            db,
            user,
            draft.id,
            revision=preview["revision"],
            preview_signature=preview["preview_signature"],
            confirm_key=key,
            row_indexes=[0],
            confirmed=True,
        )

    with get_session_context() as db:
        first_user = db.get(User, _user_id(983001))
        second_user = db.get(User, _user_id(983002))
        third_user = db.get(User, _user_id(983003))
        draft = create(db, first_user, "catalog-upload-a")
        preview = catalog_import_preview(db, first_user, draft.id)
        assert preview["rows"][0]["outcome"] == "publish"
        assert db.query(Food).filter_by(name="Тестовый продукт Альфа").count() == 0
        receipt = confirm(db, first_user, draft, preview, "catalog-confirm-a")
        assert confirm(db, first_user, draft, preview, "catalog-confirm-a") == receipt
        food_id = receipt["rows"][0]["food_id"]
        food = db.get(Food, food_id)
        assert food.food_type == "system"
        assert food.catalog_quality == "community_unverified"
        assert db.query(FoodDiaryEntry).filter_by(user_id=first_user.id).count() == 0
        visible = search_foods(db, second_user, "продукт альфа", limit=20, offset=0)
        assert any(item.id == food_id for item in visible.items)
        assert "2024-03-02" not in str(visible.model_dump(mode="json"))
        second = create(db, second_user, "catalog-upload-b")
        second_preview = catalog_import_preview(db, second_user, second.id)
        assert second_preview["rows"][0]["outcome"] == "reuse"
        assert (
            confirm(db, second_user, second, second_preview, "catalog-confirm-b")["rows"][0][
                "food_id"
            ]
            == food_id
        )
        assert db.query(Food).filter_by(name="Тестовый продукт Альфа").count() == 1
        assert db.query(NutritionCatalogContribution).filter_by(food_id=food_id).count() == 1
        similar_document = deepcopy(document)
        similar_document["rows"][0]["food"]["name"] = "Тестовый продукт Альфа новая версия"
        similar = create(db, third_user, "catalog-upload-similar", similar_document)
        similar_preview = catalog_import_preview(db, third_user, similar.id)
        assert similar_preview["rows"][0]["outcome"] == "publish"
        if engine.dialect.name == "postgresql":
            assert food_id in {
                candidate["food_id"] for candidate in similar_preview["rows"][0]["suggestions"]
            }
        conflict_document = deepcopy(document)
        conflict_document["rows"][0]["nutrition"]["facts"]["fat_g"]["value"] = "9.9"
        conflicting = create(db, second_user, "catalog-upload-conflict", conflict_document)
        conflict_preview = catalog_import_preview(db, second_user, conflicting.id)
        assert conflict_preview["rows"][0]["outcome"] == "conflict"
        confirm(db, second_user, conflicting, conflict_preview, "catalog-confirm-conflict")
        assert (
            db.query(NutritionCatalogContribution)
            .filter_by(food_id=food_id, state="conflict")
            .count()
            == 1
        )
        assert food.fat_g_per_100g == Decimal("1.2")
        db.rollback()


@pytest.mark.parametrize("collision", ["identity", "gtin", "source"])
def test_postgresql_concurrent_publications_create_one_canonical_food(
    client, monkeypatch, collision
):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction and uniqueness behavior")
    user_ids = (983101, 983102)
    for user_id in user_ids:
        _auth(client, user_id)
    monkeypatch.setitem(
        ADAPTERS,
        "synthetic-catalog",
        NutritionImportAdapter(
            "fatsecret",
            "synthetic-v1",
            "synthetic-v1",
            ",",
            FIXTURE,
            catalog_source="diary_export",
            catalog_publication_rights=frozenset({"owner_reported"}),
            catalog_food_kinds=frozenset({"standard_food", "branded_food"}),
            catalog_source_versions=frozenset({None}),
            catalog_identity_sources=frozenset({"trusted-goods-v1"}),
        ),
    )
    document = NutritionImportV1.model_validate_json(FIXTURE.read_bytes()).model_dump(mode="json")
    document["rows"] = [document["rows"][0]]
    facts = document["rows"][0]["nutrition"]["facts"]
    facts["fat_g"] = {"value": "1.2", "unit": "g", "evidence": "read"}
    facts["carbohydrate_g"] = {"value": "2.3", "unit": "g", "evidence": "read"}
    drafts = []
    with get_session_context() as db:
        for index, user_id in enumerate(user_ids):
            user = db.get(User, _user_id(user_id))
            data = deepcopy(document)
            food = data["rows"][0]["food"]
            if collision != "identity":
                food["name"] = f"Тестовый продукт Вариант {index}"
            if collision == "gtin":
                food["gtin"] = "4006381333931"
            elif collision == "source":
                food["identity_source"] = "trusted-goods-v1"
                food["source_id"] = "concurrent-product-1"
            draft = create_nutrition_import_draft(
                db,
                user,
                document=NutritionImportV1.model_validate(data),
                source=b"name,amount\nsynthetic,100\n",
                filename="synthetic.csv",
                content_type="text/csv",
                delimiter=",",
                parser_version="synthetic-v1",
                upload_key=f"upload-concurrent-{user_id}",
                adapter_id="synthetic-catalog",
            )
            drafts.append((user_id, draft.id, catalog_import_preview(db, user, draft.id)))
    barrier = Barrier(2)

    def submit(item):
        user_id, draft_id, preview = item
        with get_session_context() as db:
            user = db.get(User, _user_id(user_id))
            barrier.wait(timeout=10)
            try:
                result = confirm_catalog_import(
                    db,
                    user,
                    draft_id,
                    revision=preview["revision"],
                    preview_signature=preview["preview_signature"],
                    confirm_key=f"confirm-concurrent-{user_id}",
                    row_indexes=[0],
                    confirmed=True,
                )
                db.commit()
                return "ok", result["rows"][0]["food_id"]
            except IntegrityError, NutritionDraftError:
                db.rollback()
                return "refresh", None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, drafts))
    assert sum(status == "ok" for status, _ in outcomes) == 1
    with get_session_context() as db:
        foods = db.query(Food).filter(Food.name.like("Тестовый продукт%")).all()
        assert len(foods) == 1
        assert foods[0].catalog_quality == "community_unverified"
        assert db.query(NutritionCatalogContribution).filter_by(food_id=foods[0].id).count() == 1
        if collision == "gtin":
            assert db.query(Food).filter_by(barcode="4006381333931").count() == 1
        if collision == "source":
            identifiers = (
                db.query(NutritionCatalogIdentifier)
                .filter_by(kind="source", source_id="concurrent-product-1")
                .all()
            )
            assert [identifier.food_id for identifier in identifiers] == [foods[0].id]
        assert (
            db.query(FoodDiaryEntry)
            .filter(FoodDiaryEntry.user_id.in_([_user_id(user_id) for user_id in user_ids]))
            .count()
            == 0
        )


def test_catalog_api_requires_owner_consent_and_preserves_public_food_after_deletion(
    client, monkeypatch
):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL import limits")
    owner_headers = _auth(client, 983201)
    other_headers = _auth(client, 983202)
    document = NutritionImportV1.model_validate_json(FIXTURE.read_bytes()).model_dump(mode="json")
    document["rows"] = [document["rows"][0]]
    facts = document["rows"][0]["nutrition"]["facts"]
    facts["fat_g"] = {"value": "1.2", "unit": "g", "evidence": "read"}
    facts["carbohydrate_g"] = {"value": "2.3", "unit": "g", "evidence": "read"}
    monkeypatch.setitem(
        ADAPTERS,
        "synthetic-catalog",
        NutritionImportAdapter(
            "fatsecret",
            "synthetic-v1",
            "synthetic-v1",
            ",",
            FIXTURE,
            catalog_source="diary_export",
            catalog_publication_rights=frozenset({"owner_reported"}),
            catalog_food_kinds=frozenset({"standard_food", "branded_food"}),
            catalog_source_versions=frozenset({None}),
        ),
    )
    monkeypatch.setattr(
        nutrition_imports,
        "run_nutrition_import_adapter",
        lambda *args, **kwargs: NutritionImportV1.model_validate(document),
    )
    root = "/api/v1/nutrition/imports"
    upload = client.post(
        root,
        headers={**owner_headers, "Idempotency-Key": "api-catalog-upload"},
        data={"adapter_id": "synthetic-catalog"},
        files={"file": ("synthetic.csv", b"name,amount\nsynthetic,100\n", "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    draft_id = upload.json()["id"]
    assert client.get(f"{root}/{draft_id}/catalog", headers=other_headers).status_code == 404
    assert client.get(f"{root}/catalog/conflicts", headers=other_headers).status_code == 403
    assert (
        client.post(
            f"{root}/catalog/conflicts/1/confirm-alias",
            headers=other_headers,
            json={"preview_signature": "a" * 64},
        ).status_code
        == 403
    )
    preview_response = client.get(f"{root}/{draft_id}/catalog", headers=owner_headers)
    assert preview_response.headers["cache-control"] == "no-store, private"
    preview = preview_response.json()
    assert preview["rows"][0]["outcome"] == "publish"
    assert preview["rows"][0]["product"]["provenance"]["publication_rights"] == "owner_reported"
    assert preview["rows"][0]["product"]["provenance"]["trust"] == "community_unverified"
    assert "2024-03-02" not in str(preview["rows"][0]["product"])
    confirmation = {
        "revision": preview["revision"],
        "preview_signature": preview["preview_signature"],
        "confirm_key": "api-catalog-confirm",
        "row_indexes": [0],
        "confirmed": True,
    }
    endpoint = f"{root}/{draft_id}/catalog/confirm"
    assert client.post(endpoint, headers=other_headers, json=confirmation).status_code == 404
    assert (
        client.post(
            endpoint, headers=owner_headers, json={**confirmation, "confirmed": 1}
        ).status_code
        == 422
    )
    response = client.post(endpoint, headers=owner_headers, json=confirmation)
    assert response.status_code == 200, response.text
    assert client.post(endpoint, headers=owner_headers, json=confirmation).json() == response.json()
    food_id = response.json()["rows"][0]["food_id"]
    search = client.get(
        "/api/v1/nutrition/foods/search",
        headers=other_headers,
        params={"q": "продукт альфа"},
    )
    assert search.status_code == 200
    found = next(item for item in search.json()["items"] if item["id"] == food_id)
    assert found["catalog_quality"] == "community_unverified"
    assert found["trust_level"] == "unverified"
    assert "2024-03-02" not in search.text
    assert "983201" not in search.text
    family_id = decode_token(
        owner_headers["Authorization"].removeprefix("Bearer "), expected_type="access"
    )["sid"]
    with get_session_context() as db:
        revoke_refresh_token_family(db, _user_id(983201), family_id)
    assert client.post(endpoint, headers=owner_headers, json=confirmation).status_code == 401
    with get_session_context() as db:
        owner = db.get(User, _user_id(983201))
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner.id).count() == 0
        delete_user_cascade(db, owner)
        db.flush()
        assert db.get(Food, food_id) is not None
        assert all(
            item.contributor_user_id is None
            for item in db.query(NutritionCatalogContribution).filter_by(food_id=food_id)
        )


def test_catalog_preview_batches_database_reads_for_many_rows(client, monkeypatch):
    _auth(client, 983301)
    monkeypatch.setitem(
        ADAPTERS,
        "synthetic-catalog",
        NutritionImportAdapter(
            "fatsecret",
            "synthetic-v1",
            "synthetic-v1",
            ",",
            FIXTURE,
            catalog_source="diary_export",
            catalog_publication_rights=frozenset({"owner_reported"}),
            catalog_food_kinds=frozenset({"standard_food", "branded_food"}),
            catalog_source_versions=frozenset({None}),
        ),
    )
    document = NutritionImportV1.model_validate_json(FIXTURE.read_bytes()).model_dump(mode="json")
    row = document["rows"][0]
    row["nutrition"]["facts"]["fat_g"] = {"value": "1.2", "unit": "g", "evidence": "read"}
    row["nutrition"]["facts"]["carbohydrate_g"] = {"value": "2.3", "unit": "g", "evidence": "read"}
    with get_session_context() as db:
        owner = db.get(User, _user_id(983301))
        drafts = []
        for count in (1, 200):
            data = deepcopy(document)
            data["rows"] = []
            for index in range(count):
                item = deepcopy(row)
                item["food"]["name"] = f"Синтетический продукт {count} {index}"
                item["coordinates"]["row"] = index * 2 + 7
                item["quantity_coordinates"][0]["row"] = index * 2 + 8
                data["rows"].append(item)
            draft = create_nutrition_import_draft(
                db,
                owner,
                document=NutritionImportV1.model_validate(data),
                source=b"name,amount\nsynthetic,100\n",
                filename="synthetic.csv",
                content_type="text/csv",
                delimiter=",",
                parser_version="synthetic-v1",
                upload_key=f"batch-upload-{count}",
                adapter_id="synthetic-catalog",
            )
            drafts.append(draft.id)

        def measure(action):
            statements = []

            def track(
                _conn,
                _cursor,
                statement,
                _parameters,
                _context,
                _executemany,
                _statements=statements,
            ):
                _statements.append(statement.split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", track)
            tracemalloc.start()
            started = perf_counter()
            try:
                result = action()
                elapsed = perf_counter() - started
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
                event.remove(engine, "before_cursor_execute", track)
            return result, (len(statements), statements.count("SELECT"), elapsed, peak)

        previews = []
        preview_measurements = []
        for draft_id in drafts:
            preview, measurement = measure(
                lambda draft_id=draft_id: catalog_import_preview(db, owner, draft_id)
            )
            previews.append(preview)
            preview_measurements.append(measurement)
        assert preview_measurements[0][1] == preview_measurements[1][1]
        confirm_measurements = []
        for count, draft_id, preview in zip((1, 200), drafts, previews, strict=True):
            db.refresh(owner)
            if count == 200:
                refreshed = catalog_import_preview(db, owner, draft_id)
                if engine.dialect.name == "postgresql":
                    assert refreshed["preview_signature"] != preview["preview_signature"]
                    with pytest.raises(NutritionDraftError, match="preview_changed"):
                        confirm_catalog_import(
                            db,
                            owner,
                            draft_id,
                            revision=preview["revision"],
                            preview_signature=preview["preview_signature"],
                            confirm_key=f"batch-confirm-{count}",
                            row_indexes=list(range(count)),
                            confirmed=True,
                        )
                    db.rollback()
                    db.refresh(owner)
                preview = refreshed

            def confirm_and_commit(count=count, draft_id=draft_id, preview=preview):
                result = confirm_catalog_import(
                    db,
                    owner,
                    draft_id,
                    revision=preview["revision"],
                    preview_signature=preview["preview_signature"],
                    confirm_key=f"batch-confirm-{count}",
                    row_indexes=list(range(count)),
                    confirmed=True,
                )
                db.commit()
                return result

            receipt, measurement = measure(confirm_and_commit)
            assert len(receipt["rows"]) == count
            confirm_measurements.append(measurement)
        assert confirm_measurements[0][1] == confirm_measurements[1][1]
        print(
            f"catalog preview rows 1/200; total/select/seconds/peak-bytes: {preview_measurements}"
        )
        print(
            f"catalog confirm rows 1/200; total/select/seconds/peak-bytes: {confirm_measurements}"
        )


def test_source_identity_aliases_conflicts_and_stale_previews(client, monkeypatch):
    for number in (983401, 983402, 983403):
        _auth(client, number)
    monkeypatch.setitem(
        ADAPTERS,
        "synthetic-catalog",
        NutritionImportAdapter(
            "fatsecret",
            "synthetic-v1",
            "synthetic-v1",
            ",",
            FIXTURE,
            catalog_source="diary_export",
            catalog_publication_rights=frozenset({"owner_reported"}),
            catalog_food_kinds=frozenset({"standard_food", "branded_food"}),
            catalog_source_versions=frozenset({None}),
            catalog_identity_sources=frozenset({"trusted-goods-v1"}),
        ),
    )
    document = NutritionImportV1.model_validate_json(FIXTURE.read_bytes()).model_dump(mode="json")
    document["rows"] = [document["rows"][0]]
    row = document["rows"][0]
    row["food"] = {
        "name": "Тестовый йогурт",
        "brand": "Тест Бренд",
        "kind": "branded_food",
        "gtin": "4006381333931",
        "identity_source": "trusted-goods-v1",
        "source_id": "product-1",
    }
    row["nutrition"]["facts"]["fat_g"] = {"value": "1.2", "unit": "g", "evidence": "read"}
    row["nutrition"]["facts"]["carbohydrate_g"] = {"value": "2.3", "unit": "g", "evidence": "read"}

    def draft_for(db, owner, data, key):
        return create_nutrition_import_draft(
            db,
            owner,
            document=NutritionImportV1.model_validate(data),
            source=b"name,amount\nsynthetic,100\n",
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="synthetic-v1",
            upload_key=key,
            adapter_id="synthetic-catalog",
        )

    def confirm(db, owner, draft, preview, key):
        return confirm_catalog_import(
            db,
            owner,
            draft.id,
            revision=preview["revision"],
            preview_signature=preview["preview_signature"],
            confirm_key=key,
            row_indexes=[0],
            confirmed=True,
        )

    with get_session_context() as db:
        owner = db.get(User, _user_id(983401))
        second = db.get(User, _user_id(983402))
        third = db.get(User, _user_id(983403))
        first = draft_for(db, owner, document, "identity-upload-one")
        first_preview = catalog_import_preview(db, owner, first.id)
        food_id = confirm(db, owner, first, first_preview, "identity-confirm-one")["rows"][0][
            "food_id"
        ]
        assert (
            db.query(NutritionCatalogIdentifier)
            .filter_by(kind="source", source_id="product-1")
            .count()
            == 1
        )
        alternative = deepcopy(document)
        alternative["rows"][0]["food"]["name"] = "Йогурт альтернативное название"
        conflict = draft_for(db, second, alternative, "identity-upload-two")
        conflict_preview = catalog_import_preview(db, second, conflict.id)
        assert conflict_preview["rows"][0]["outcome"] == "conflict"
        confirm(db, second, conflict, conflict_preview, "identity-confirm-two")
        conflict_record = list_catalog_conflicts(db, after_id=0, limit=10)[0]
        assert (
            confirm_catalog_alias(
                db,
                owner,
                conflict_record["id"],
                preview_signature=conflict_record["preview_signature"],
            )["food_id"]
            == food_id
        )
        alias_draft = draft_for(db, third, alternative, "identity-upload-three")
        alias_preview = catalog_import_preview(db, third, alias_draft.id)
        assert alias_preview["rows"][0]["outcome"] == "reuse"
        assert alias_preview["rows"][0]["food_id"] == food_id

        db.get(Food, food_id).energy_kcal_per_100g = Decimal("99")
        db.flush()
        with pytest.raises(NutritionDraftError, match="preview_changed"):
            confirm(db, third, alias_draft, alias_preview, "identity-confirm-three")
        alias_draft.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.flush()
        with pytest.raises(NutritionDraftError, match="draft_unavailable"):
            catalog_import_preview(db, third, alias_draft.id)
        forged = deepcopy(document)
        forged["rows"][0]["food"].update(
            {
                "name": "Совсем другой продукт",
                "gtin": None,
                "identity_source": "untrusted-source",
            }
        )
        forged_draft = draft_for(db, third, forged, "identity-upload-forged")
        forged_preview = catalog_import_preview(db, third, forged_draft.id)
        assert forged_preview["rows"][0]["outcome"] == "publish"
        assert forged_preview["rows"][0]["food_id"] is None
        forged["source"]["source_version"] = "user-983401"
        version_draft = draft_for(db, third, forged, "identity-upload-version")
        assert (
            catalog_import_preview(db, third, version_draft.id)["rows"][0]["reason"]
            == "publication_rights_unconfirmed"
        )
        db.rollback()


def test_legacy_upload_retry_does_not_inherit_catalog_rights(client, monkeypatch):
    _auth(client, 983501)
    monkeypatch.setitem(
        ADAPTERS,
        "synthetic-catalog",
        NutritionImportAdapter(
            "fatsecret",
            "synthetic-v1",
            "synthetic-v1",
            ",",
            FIXTURE,
            catalog_source="diary_export",
            catalog_publication_rights=frozenset({"owner_reported"}),
            catalog_food_kinds=frozenset({"standard_food", "branded_food"}),
            catalog_source_versions=frozenset({None}),
        ),
    )
    document = NutritionImportV1.model_validate_json(FIXTURE.read_bytes())
    with get_session_context() as db:
        owner = db.get(User, _user_id(983501))
        values = {
            "document": document,
            "source": b"name,amount\nsynthetic,100\n",
            "filename": "synthetic.csv",
            "content_type": "text/csv",
            "delimiter": ",",
            "parser_version": "synthetic-v1",
            "upload_key": "legacy-upload-key",
        }
        legacy = create_nutrition_import_draft(db, owner, **values)
        retried = create_nutrition_import_draft(db, owner, **values, adapter_id="synthetic-catalog")
        assert retried.id == legacy.id
        assert retried.adapter_id is None
        preview = catalog_import_preview(db, owner, legacy.id)
        assert preview["rows"][0]["reason"] == "publication_rights_unconfirmed"
