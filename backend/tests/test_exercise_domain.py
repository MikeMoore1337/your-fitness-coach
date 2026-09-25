from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.exercise import (
    Equipment,
    ExerciseAlternative,
    ExerciseEquipment,
    ExerciseGuideMetadata,
    ExerciseMuscle,
    Muscle,
)
from fitminiapp_api.services.exercise_catalog_metadata import (
    CATALOG_METADATA,
    ITEM_GUIDE_CONTENT,
    LOWER_BODY_MACHINE_SLUGS,
    MEDIA_STATE_BY_SLUG,
    UPPER_BODY_MACHINE_SLUGS,
    structured_catalog_metadata,
)
from fitminiapp_api.services.seed import seed_demo_data


def auth(client, telegram_user_id: int, *, is_coach: bool) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "is_coach": is_coach,
            "is_admin": False,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _load_migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0039_exercise_domain.py"
    spec = importlib.util.spec_from_file_location("exercise_domain_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_exercise_domain_migration_backfills_only_supported_metadata(tmp_path: Path) -> None:
    migration = _load_migration()
    assert migration.down_revision == "0038_food_progress_hardening"

    migration_engine = sa.create_engine(
        f"sqlite:///{(tmp_path / 'exercise-domain-migration.db').as_posix()}"
    )
    metadata = sa.MetaData()
    exercises = sa.Table(
        "exercises",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("primary_muscle", sa.String(length=64), nullable=True),
        sa.Column("equipment", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("source_exercise_id", sa.Integer(), nullable=True),
    )
    metadata.create_all(migration_engine)
    with migration_engine.begin() as connection:
        connection.execute(
            exercises.insert(),
            [
                {
                    "id": 1,
                    "slug": "bench-press",
                    "primary_muscle": "Грудь",
                    "equipment": "Штанга",
                    "created_by_user_id": None,
                    "source_exercise_id": None,
                },
                {
                    "id": 2,
                    "slug": "dumbbell-bench-press",
                    "primary_muscle": "Грудь",
                    "equipment": "Гантели",
                    "created_by_user_id": None,
                    "source_exercise_id": None,
                },
                {
                    "id": 3,
                    "slug": "bench-press-u-personal",
                    "primary_muscle": "Грудь",
                    "equipment": "Гантели",
                    "created_by_user_id": 9,
                    "source_exercise_id": 1,
                },
                {
                    "id": 4,
                    "slug": "my-unknown-move",
                    "primary_muscle": None,
                    "equipment": "Своё оборудование",
                    "created_by_user_id": 9,
                    "source_exercise_id": None,
                },
            ],
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        muscle_rows = connection.execute(
            sa.text(
                "SELECT em.exercise_id, m.identifier, em.role, em.position "
                "FROM exercise_muscles em JOIN muscles m ON m.id = em.muscle_id "
                "ORDER BY em.exercise_id, em.role, em.position"
            )
        ).all()
        assert (1, "chest", "primary", 0) in muscle_rows
        assert (1, "triceps", "secondary", 0) in muscle_rows
        assert (1, "anterior_deltoid", "secondary", 1) in muscle_rows
        assert (3, "chest", "primary", 0) in muscle_rows
        assert all(row[0] != 4 for row in muscle_rows)

        equipment_rows = connection.execute(
            sa.text(
                "SELECT ee.exercise_id, e.identifier FROM exercise_equipment ee "
                "JOIN equipment e ON e.id = ee.equipment_id ORDER BY ee.exercise_id"
            )
        ).all()
        assert equipment_rows == [(1, "barbell"), (2, "dumbbell"), (3, "dumbbell")]

        guides = connection.execute(
            sa.text(
                "SELECT exercise_id, source_name, source_license, media_reference "
                "FROM exercise_guide_metadata ORDER BY exercise_id"
            )
        ).all()
        assert guides == [
            (
                1,
                "free-exercise-db",
                "Unlicense (общественное достояние)",
                "exercise-guides:bench-press",
            ),
            (
                2,
                "free-exercise-db",
                "Unlicense (общественное достояние)",
                "exercise-guides:dumbbell-bench-press",
            ),
            (
                3,
                "free-exercise-db",
                "Unlicense (общественное достояние)",
                "exercise-guides:bench-press",
            ),
        ]
        assert connection.execute(
            sa.text("SELECT exercise_id, alternative_exercise_id FROM exercise_alternatives")
        ).all() == [(1, 2)]

        inspector = sa.inspect(connection)
        assert {index["name"] for index in inspector.get_indexes("exercise_muscles")} == {
            "ix_exercise_muscles_muscle_role_exercise"
        }
        assert {index["name"] for index in inspector.get_indexes("exercise_equipment")} == {
            "ix_exercise_equipment_equipment_exercise"
        }
        assert {index["name"] for index in inspector.get_indexes("exercise_alternatives")} == {
            "ix_exercise_alternatives_reverse"
        }

        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                sa.text(
                    "INSERT INTO exercise_alternatives "
                    "(exercise_id, alternative_exercise_id) VALUES (1, 1)"
                )
            )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                sa.text(
                    "INSERT INTO exercise_alternatives "
                    "(exercise_id, alternative_exercise_id) VALUES (1, 2)"
                )
            )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                sa.text(
                    "INSERT INTO exercise_muscles (exercise_id, muscle_id, role, position) "
                    "SELECT 1, id, 'primary', 0 FROM muscles WHERE identifier = 'chest'"
                )
            )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                sa.text(
                    "INSERT INTO exercise_equipment (exercise_id, equipment_id, position) "
                    "SELECT 1, id, 0 FROM equipment WHERE identifier = 'barbell'"
                )
            )

        migration.downgrade()
        assert "exercise_muscles" not in sa.inspect(connection).get_table_names()
    migration_engine.dispose()


def test_seeded_exercise_metadata_and_alternatives_are_serialized(client) -> None:
    headers = auth(client, telegram_user_id=32301, is_coach=False)
    catalog = client.get("/api/v1/programs/exercises", headers=headers)

    assert catalog.status_code == 200
    bench = next(item for item in catalog.json() if item["slug"] == "bench-press")
    assert bench["primary_muscle"] == "Грудь"
    assert bench["equipment"] == "Штанга"
    assert bench["primary_muscle_ids"] == ["chest"]
    assert set(bench["secondary_muscle_ids"]) == {"triceps", "anterior_deltoid"}
    assert bench["equipment_ids"] == ["barbell"]
    assert {item["slug"] for item in bench["alternatives"]} == {
        "dumbbell-bench-press",
        "floor-press",
        "machine-chest-press",
    }

    details = client.get(f"/api/v1/programs/exercises/{bench['id']}", headers=headers)
    assert details.status_code == 200
    guide = details.json()["guide"]
    assert guide["media_reference"] == "exercise-guides:bench-press"
    assert guide["source_name"] == "Gym visual"
    assert guide["source_license"] == "Owner-purchased GymVisual license"
    assert guide["source_license_url"].endswith("terms-and-conditions-of-use")
    assert [item["type"] for item in guide["media"]] == ["animation"]
    assert guide["media"][0]["url"].endswith(".gif")
    assert guide["media"][0]["poster"].endswith(".jpg")
    assert guide["media"][0]["phase"] == "Движение"
    assert guide["media"][0]["source_name"] == "Gym visual"
    assert guide["media"][0]["source_license"] == "Owner-purchased GymVisual license"
    assert guide["media"][0]["sources"] == [
        {
            "url": guide["media"][0]["url"],
            "mime_type": "image/gif",
            "width": 180,
            "height": 180,
            "byte_size": guide["media"][0]["byte_size"],
        }
    ]
    assert guide["images"] == [
        {
            "phase": "Движение",
            "url": guide["media"][0]["url"],
            "alt": "Жим лежа: движение",
        },
    ]
    assert guide["safety_notes"]
    assert guide["equipment"] == [{"identifier": "barbell", "name": "Штанга"}]
    assert guide["muscles"][0]["identifier"] == "chest"
    assert guide["muscles"][0]["role_id"] == "primary"
    assert {item["slug"] for item in guide["alternatives"]} == {
        "dumbbell-bench-press",
        "floor-press",
        "machine-chest-press",
    }
    guide_response = client.get(
        f"/api/v1/programs/exercises/{bench['id']}/guide",
        headers=headers,
    )
    assert guide_response.status_code == 200
    assert guide_response.json()["media_reference"] == "exercise-guides:bench-press"
    assert guide_response.json()["source_license_url"].endswith("terms-and-conditions-of-use")

    lat_pulldown = next(item for item in catalog.json() if item["slug"] == "lat-pulldown")
    lat_pulldown_guide = client.get(
        f"/api/v1/programs/exercises/{lat_pulldown['id']}/guide",
        headers=headers,
    ).json()
    assert [item["phase"] for item in lat_pulldown_guide["media"]] == ["Движение"]

    plank = next(item for item in catalog.json() if item["slug"] == "plank")
    plank_guide = client.get(
        f"/api/v1/programs/exercises/{plank['id']}/guide",
        headers=headers,
    ).json()
    assert [item["phase"] for item in plank_guide["media"]] == ["Движение"]

    reviewed_slugs = {
        "hyperextension",
        "lying-dumbbell-triceps-extension",
        "romanian-deadlift",
        "smith-squat",
        "triceps-kickback",
        "upright-row",
        "pallof-press",
        "rowing-machine",
        "walking-lunge",
        "wall-ball",
    }
    catalog_by_slug = {item["slug"]: item for item in catalog.json()}
    for slug in reviewed_slugs:
        reviewed_guide = client.get(
            f"/api/v1/programs/exercises/{catalog_by_slug[slug]['id']}/guide",
            headers=headers,
        ).json()
        if catalog_by_slug[slug]["media_state"] == "approved_animated":
            assert len(reviewed_guide["media"]) == 1
            assert reviewed_guide["media"][0]["type"] == "animation"
            assert reviewed_guide["media"][0]["url"].endswith(".gif")
            assert reviewed_guide["media"][0]["phase"] == "Движение"
        else:
            assert reviewed_guide["media"] == []


def test_task_120b_upper_body_machine_batch_contract(client) -> None:
    headers = auth(client, telegram_user_id=32305, is_coach=False)
    catalog_response = client.get("/api/v1/programs/exercises", headers=headers)

    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    by_slug = {item["slug"]: item for item in catalog}
    assert len(by_slug) == len(catalog) == 207
    assert set(UPPER_BODY_MACHINE_SLUGS) <= set(by_slug)
    assert len({item["title"] for item in catalog}) == len(catalog) - 1

    for slug in UPPER_BODY_MACHINE_SLUGS:
        item = by_slug[slug]
        assert item["metric_type"] == "strength"
        assert item["aliases"]
        assert item["movement_pattern"]
        assert item["execution_variant_tags"]
        assert item["has_guide"] is True
        assert item["equipment_ids"] == (
            ["dumbbell"] if slug == "chest-supported-dumbbell-row" else ["machine"]
        )

    high_row = by_slug["lever-high-row"]
    assert "верхняя тяга хаммер" in high_row["aliases"]
    assert high_row["machine_variant_tags"] == ["plate_loaded", "lever", "independent"]
    assert high_row["primary_muscle_ids"] == ["back"]
    assert {item["slug"] for item in high_row["alternatives"]} == {"chest-supported-row"}

    guide_response = client.get(
        f"/api/v1/programs/exercises/{high_row['id']}/guide",
        headers=headers,
    )
    assert guide_response.status_code == 200
    guide = guide_response.json()
    assert guide["source_name"] == "Gym visual"
    assert guide["source_license"] == "Owner-purchased GymVisual license"
    assert guide["source_license_url"].endswith("terms-and-conditions-of-use")
    assert guide["technique_steps"][0].startswith("Настрой сиденье и грудной упор")
    assert {item["identifier"] for item in guide["muscles"] if item["role_id"] == "secondary"} == {
        "biceps",
        "posterior_deltoid",
        "forearms",
    }
    assert len(guide["media"]) == 1
    assert guide["media"][0]["type"] == "animation"
    assert guide["media"][0]["url"].endswith(".gif")
    assert guide["media"][0]["poster"].endswith(".jpg")
    assert guide["media"][0]["phase"] == "Движение"
    assert guide["media"][0]["asset_version"].startswith("gymvisual-")
    assert len(guide["media"][0]["sources"]) == 1
    assert all("Верхняя рычажная тяга" in item["alt"] for item in guide["media"])

    machine_biceps = by_slug["machine-biceps-curl"]
    assert "сгибание на скамье Скотта в тренажере" in machine_biceps["aliases"]

    normalized_titles = {
        " ".join(item["title"].casefold().split()): item["slug"] for item in catalog
    }
    alias_owners: dict[str, str] = {}
    for slug, metadata in CATALOG_METADATA.items():
        for alias in metadata["aliases"]:
            normalized = " ".join(alias.casefold().split())
            assert normalized
            assert normalized not in alias_owners
            alias_owners[normalized] = slug
            if normalized in normalized_titles:
                assert normalized_titles[normalized] == slug


def test_task_120e_human_visual_manifest_provenance_and_integrity() -> None:
    assets = Path(__file__).resolve().parents[1] / "assets" / "exercise-guides"
    manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 3
    assert manifest["asset_count"] == 334
    assert manifest["derivative_count"] == 0
    assert len(manifest["exercises"]) == 206
    assert manifest["counts"] == {
        "canonical_exercises": 206,
        "approved_animated": 167,
        "blocked": 39,
        "approved_coverage_percent": 81.07,
        "static_only": 0,
        "remote_runtime_assets": 0,
    }
    approved = [item for item in manifest["exercises"].values() if item["status"] == "approved"]
    blocked = [item for item in manifest["exercises"].values() if item["status"] == "blocked"]
    assert len(approved) == 167
    assert len(blocked) == 39
    assert manifest["source"]["name"] == "Gym visual"
    assert manifest["source"]["license"] == "Owner-purchased GymVisual license"
    assert manifest["source"]["source_revision"] == ("7455efae41b330c265e7cd4b78dfa848e7ce5ebd")
    for exercise in approved:
        source = exercise["source"]
        assert source["url"] == "https://github.com/hasaneyldrm/exercises-dataset"
        assert len(exercise["media"]) == 1
        media = exercise["media"][0]
        path = assets / media["path"]
        poster = assets / media["poster_path"]
        assert path.suffix == ".gif"
        assert poster.suffix == ".jpg"
        assert path.is_file() and poster.is_file()
        assert media["type"] == "animation"
        assert media["animated"] is True
        assert media["frame_count"] > 1
        assert hashlib.sha256(path.read_bytes()).hexdigest() == media["asset_sha256"]
        assert hashlib.sha256(poster.read_bytes()).hexdigest() == media["poster_sha256"]
        assert media["sources"] == [
            {
                "path": media["path"],
                "mime_type": "image/gif",
                "width": media["width"],
                "height": media["height"],
                "byte_size": media["byte_size"],
            }
        ]
    for exercise in blocked:
        assert exercise["source"] is None
        assert exercise["media"] == []


def test_task_120e_builder_cannot_mint_semantic_approval(tmp_path: Path) -> None:
    from scripts.build_exercise_human_visual_assets import load_review_lock

    review_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "exercises"
        / "catalog-v2"
        / "120E_ASSET_REVIEW.json"
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["automated_semantic_approval"] = True
    invalid_lock = tmp_path / "invalid-review-lock.json"
    invalid_lock.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(ValueError, match="Automated semantic approval"):
        load_review_lock(invalid_lock)


def test_task_120e_builders_require_exact_gate_b_verdict(tmp_path: Path) -> None:
    from scripts.build_exercise_human_visual_assets import load_review_lock

    review_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "exercises"
        / "catalog-v2"
        / "120E_ASSET_REVIEW.json"
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["owner_gates"]["gate_b"] = {
        "status": "approved",
        "verdict": "APPROVE_DIFFERENT_REVISION",
        "approved_at": "2026-08-31",
    }
    invalid_lock = tmp_path / "wrong-gate-b-verdict-review-lock.json"
    invalid_lock.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(ValueError, match="Gate B exact verdict"):
        load_review_lock(invalid_lock)


def test_task_120e_builder_stages_before_replacing_derivatives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image
    from scripts import build_exercise_human_visual_assets as builder

    slug = "test-machine"
    monkeypatch.setattr(
        builder,
        "HUMAN_VISUAL_SPECS",
        {slug: builder.HumanVisualSpec("canonical_test_machine")},
    )
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    source_name = f"{slug}-concentric_end-v1.png"
    source_path = source_dir / source_name
    Image.new("RGB", (1536, 1024), (32, 32, 32)).save(source_path)
    source_digest = builder.sha256(source_path)
    reviews = {
        "domain": "pass",
        "anatomy": "pass",
        "equipment": "pass",
        "phase": "pass",
        "visual_style": "pass",
        "mobile": "pass",
        "legal": "pass_with_limitations",
    }
    lock = {
        "schema_version": 1,
        "asset_version": builder.ASSET_VERSION,
        "review_record_kind": "human_review_exact_revision",
        "automated_semantic_approval": False,
        "owner_gates": {
            "gate_a": {
                "status": "approved",
                "verdict": "APPROVE_120E_VISUAL_DIRECTION",
            },
            "gate_b": {
                "status": "approved",
                "verdict": "APPROVE_120E_EXACT_ASSET_REVISION",
            },
        },
        "exercises": {
            slug: {
                "variant_key": "canonical_test_machine",
                "phases": {
                    "concentric_end": {
                        "source_master_filename": source_name,
                        "source_master_sha256": source_digest,
                        "reviews": reviews,
                        "sources": [],
                    }
                },
            }
        },
        "source_set_sha256": "not-reached",
        "derivative_set_sha256": "not-reached",
    }
    lock_path = tmp_path / "review-lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    asset_dir = tmp_path / "assets"
    existing = asset_dir / "human-v1" / slug / "concentric_end-480w.webp"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"approved-existing-derivative")

    with pytest.raises(ValueError, match="Derivative output is not the reviewed revision"):
        builder.build(source_dir, asset_dir, lock_path)

    assert existing.read_bytes() == b"approved-existing-derivative"


def test_legacy_media_manifest_builder_is_fail_closed() -> None:
    from scripts import build_exercise_guide_media_manifest as builder

    assert "retired schema 2" in builder.DEPRECATION_MESSAGE
    assert builder.main() == 2


def test_task_120c_lower_body_machine_batch_contract_and_workout_integration(client) -> None:
    headers = auth(client, telegram_user_id=32306, is_coach=False)
    catalog_response = client.get("/api/v1/programs/exercises", headers=headers)

    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    by_slug = {item["slug"]: item for item in catalog}
    assert len(by_slug) == len(catalog) == 207
    assert set(LOWER_BODY_MACHINE_SLUGS) <= set(by_slug)
    assert len({item["title"] for item in catalog}) == len(catalog) - 1

    expected_patterns = {
        "pendulum-squat": "squat",
        "plate-loaded-leg-press": "squat",
        "unilateral-leg-press": "squat",
        "machine-hip-thrust": "glute",
        "smith-split-squat": "lunge",
        "machine-glute-kickback": "leg_isolation",
        "v-squat-machine": "squat",
        "reverse-hyperextension": "hinge",
    }
    for slug, movement_pattern in expected_patterns.items():
        item = by_slug[slug]
        assert item["metric_type"] == "strength"
        assert item["aliases"]
        assert item["movement_pattern"] == movement_pattern
        assert item["machine_variant_tags"]
        assert item["execution_variant_tags"]
        assert item["equipment_ids"] == ["machine"]
        assert item["has_guide"] is True

        guide_response = client.get(
            f"/api/v1/programs/exercises/{item['id']}/guide",
            headers=headers,
        )
        assert guide_response.status_code == 200
        guide = guide_response.json()
        assert len(guide["technique_steps"]) == 3
        assert len(guide["common_mistakes"]) == 3
        assert guide["safety_notes"]
        if item["media_state"] == "approved_animated":
            assert guide["source_name"] == "Gym visual"
            assert guide["source_license"] == "Owner-purchased GymVisual license"
            assert len(guide["media"]) == 1
            assert guide["media"][0]["type"] == "animation"
            assert guide["media"][0]["url"].endswith(".gif")
            assert guide["media"][0]["poster"].endswith(".jpg")
        else:
            assert item["media_state"] == "blocked"
            assert guide["media"] == []

    assert "жим ногами на блинах" in by_slug["plate-loaded-leg-press"]["aliases"]
    assert "pendulum squat" in by_slug["pendulum-squat"]["aliases"]
    assert "ягодичный тренажер" in by_slug["machine-hip-thrust"]["aliases"]
    assert "smith lunge" in by_slug["smith-split-squat"]["aliases"]
    assert "смит присед" in by_slug["smith-squat"]["aliases"]
    assert "hack squat" in by_slug["hack-squat"]["aliases"]
    assert "сгибание ног лежа" in by_slug["leg-curl"]["aliases"]
    assert "сгибание ног сидя" in by_slug["seated-leg-curl"]["aliases"]
    assert "сгибание ног стоя" in by_slug["standing-leg-curl"]["aliases"]
    assert "жим ногами широкая постановка" in by_slug["leg-press"]["aliases"]
    assert by_slug["calf-press"]["movement_pattern"] == "calf"
    assert by_slug["unilateral-leg-press"]["execution_variant_tags"] == ["unilateral"]
    assert by_slug["smith-split-squat"]["machine_variant_tags"] == ["smith"]
    assert {item["slug"] for item in by_slug["machine-hip-thrust"]["alternatives"]} == {
        "hip-thrust"
    }

    machine_hip_thrust = by_slug["machine-hip-thrust"]
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Ноги и ягодицы 120C",
            "goal": "recomposition",
            "level": "beginner",
            "mode": "self",
            "assign_after_create": True,
            "days": [
                {
                    "title": "Низ тела",
                    "exercises": [
                        {
                            "exercise_id": machine_hip_thrust["id"],
                            "prescribed_sets": 1,
                            "prescribed_reps": "10-12",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200
    today = client.get("/api/v1/workouts/today", headers=headers)
    assert today.status_code == 200
    workout = today.json()
    assert workout["exercises"][0]["exercise_id"] == machine_hip_thrust["id"]
    assert workout["exercises"][0]["exercise_title"] == machine_hip_thrust["title"]
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200


def test_task_120d_remaining_coverage_redirects_and_validator(client) -> None:
    headers = auth(client, telegram_user_id=32307, is_coach=False)
    response = client.get("/api/v1/programs/exercises", headers=headers)

    assert response.status_code == 200
    catalog = response.json()
    by_slug = {item["slug"]: item for item in catalog}
    assert len(catalog) == 207
    assert len({item["canonical_slug"] or item["slug"] for item in catalog}) == 206

    expected_metric_types = {
        "bodyweight-squat": "strength",
        "bodyweight-glute-bridge": "strength",
        "barbell-wrist-curl": "strength",
        "barbell-wrist-extension": "strength",
        "dead-hang": "strength",
        "recumbent-bike": "cardio",
    }
    for slug, metric_type in expected_metric_types.items():
        item = by_slug[slug]
        assert item["metric_type"] == metric_type
        assert item["aliases"]
        assert item["movement_pattern"]
        assert item["execution_variant_tags"]
        assert item["has_guide"] is True
        guide = client.get(f"/api/v1/programs/exercises/{item['id']}/guide", headers=headers).json()
        assert len(guide["technique_steps"]) == 3
        assert len(guide["common_mistakes"]) >= 3
        assert guide["breathing"]
        if item["media_state"] == "approved_animated":
            assert guide["media"]
            assert all(
                media["type"] == "animation" and media["alt"] and media["sources"]
                for media in guide["media"]
            )
        else:
            assert item["media_state"] == "blocked"
            assert guide["media"] == []

    assert by_slug["recumbent-bike"]["equipment_ids"] == ["cardio"]
    assert by_slug["rowing-machine"]["equipment"] == "Гребной тренажёр"
    assert by_slug["treadmill-run"]["equipment"] == "Беговая дорожка"
    assert by_slug["assault-bike"]["title"] == "Воздушный велотренажёр"
    assert by_slug["kettlebell-goblet-squat"]["canonical_slug"] == "goblet-squat"
    assert by_slug["goblet-squat"]["canonical_slug"] is None
    assert "high to low cable fly" in by_slug["cable-fly"]["aliases"]

    legacy_goblet = by_slug["kettlebell-goblet-squat"]
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "History-safe goblet redirect",
            "goal": "maintenance",
            "level": "beginner",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "День 1",
                    "exercises": [
                        {
                            "exercise_id": legacy_goblet["id"],
                            "prescribed_sets": 3,
                            "prescribed_reps": "8-12",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200
    assert (
        created.json()["template"]["days"][0]["exercises"][0]["exercise_id"] == legacy_goblet["id"]
    )

    for slug, personalized_title in (
        ("kettlebell-goblet-squat", "Мой гоблет с гирей"),
        ("goblet-squat", "Мой канонический гоблет"),
    ):
        personalized = client.patch(
            f"/api/v1/programs/exercises/{by_slug[slug]['edit_target_id']}",
            headers=headers,
            json={"title": personalized_title},
        )
        assert personalized.status_code == 200
        personalized_item = personalized.json()
        assert personalized_item["slug"].startswith(f"{slug}-u-")
        assert personalized_item["canonical_slug"] == "goblet-squat"
        assert personalized_item["aliases"]
        assert personalized_item["movement_pattern"] == "squat"

    personalized_catalog = client.get("/api/v1/programs/exercises", headers=headers).json()
    assert len(personalized_catalog) == 207
    assert len({item["canonical_slug"] or item["slug"] for item in personalized_catalog}) == 206

    validator_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "validate_exercise_catalog.py"
    )
    spec = importlib.util.spec_from_file_location("exercise_catalog_validator", validator_path)
    assert spec is not None and spec.loader is not None
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    report = validator.validate_catalog()
    assert report == {
        "catalog_records": 207,
        "canonical_records": 206,
        "titles": 207,
        "cardio_records": 14,
        "assets": 334,
        "derivatives": 0,
        "coverage_decisions": 36,
        "guide_item_content_records": 49,
        "guide_profile_records": 206,
        "media_approved_animated": 167,
        "media_blocked": 39,
        "media_remote_runtime_assets": 0,
        "media_static_only": 0,
        "metadata_aliases_populated": 69,
        "metadata_aliases_reviewed_empty": 137,
        "metadata_execution_populated": 69,
        "metadata_execution_reviewed_empty": 137,
        "metadata_machine_applicable": 52,
        "metadata_machine_populated": 23,
        "metadata_machine_reviewed_empty": 29,
        "metadata_records": 206,
        "metadata_required_missing": 0,
        "new_guide_content_records": 25,
    }


def test_task_395_approved_canonicals_metadata_search_and_workout(client) -> None:
    headers = auth(client, telegram_user_id=32395, is_coach=False)
    approved_slugs = {
        "floor-press",
        "push-press",
        "assisted-pull-ups",
        "decline-crunch",
        "pistol-squat",
        "overhead-squat",
        "cable-external-rotation",
        "hanging-knee-raise",
        "trap-bar-deadlift",
        "safety-bar-squat",
        "negative-pull-ups",
        "scapular-pull-ups",
        "muscle-ups",
        "assisted-dips",
        "machine-seated-crunch",
        "band-pull-apart",
        "db-squat",
        "kettlebell-overhead-carry",
        "dragon-flag",
        "jackknife-sit-up",
        "l-sit",
        "clean-and-jerk",
        "hang-power-clean",
        "wrist-roller",
        "rope-climb",
    }
    catalog = client.get("/api/v1/programs/exercises", headers=headers).json()
    by_slug = {item["slug"]: item for item in catalog}
    structured = structured_catalog_metadata()

    assert approved_slugs <= set(by_slug)
    assert "roman-chair-crunch" not in by_slug
    assert approved_slugs == set(MEDIA_STATE_BY_SLUG)
    for slug in approved_slugs:
        item = by_slug[slug]
        record = structured[slug]
        assert item["primary_muscle_ids"]
        assert item["secondary_muscle_ids"]
        assert item["equipment_ids"]
        assert item["metric_type"] == record["metric_type"] == "strength"
        assert item["difficulty_level"] == record["difficulty_level"]
        assert item["movement_pattern"] == record["movement_pattern"]
        assert item["aliases"]
        assert len(ITEM_GUIDE_CONTENT[slug]["steps"]) == 3
        assert len(ITEM_GUIDE_CONTENT[slug]["mistakes"]) >= 3
        assert ITEM_GUIDE_CONTENT[slug]["breathing"]

    assert "тяга трэп-гриф" in by_slug["trap-bar-deadlift"]["aliases"]
    assert "safety bar squat" in by_slug["safety-bar-squat"]["aliases"]
    assert "подтягивания в гравитроне" in by_slug["assisted-pull-ups"]["aliases"]
    assert by_slug["machine-seated-crunch"]["equipment_ids"] == ["machine"]
    assert by_slug["wrist-roller"]["equipment_ids"] == ["other"]

    floor_press = by_slug["floor-press"]
    seated_crunch = by_slug["machine-seated-crunch"]
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Issue 395 canonical workout",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": True,
            "days": [
                {
                    "title": "Новые канонические движения",
                    "exercises": [
                        {
                            "exercise_id": floor_press["id"],
                            "prescribed_sets": 1,
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                        },
                        {
                            "exercise_id": seated_crunch["id"],
                            "prescribed_sets": 1,
                            "prescribed_reps": "12",
                            "rest_seconds": 60,
                        },
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200

    today = client.get("/api/v1/workouts/today", headers=headers).json()
    today_by_exercise = {item["exercise_id"]: item for item in today["exercises"]}
    assert today_by_exercise[floor_press["id"]]["exercise_title"] == floor_press["title"]
    assert today_by_exercise[seated_crunch["id"]]["exercise_title"] == seated_crunch["title"]
    assert client.post(f"/api/v1/workouts/{today['id']}/start", headers=headers).status_code == 200
    for item in today["exercises"]:
        saved = client.patch(
            f"/api/v1/workouts/sets/{item['sets'][0]['id']}",
            json={"actual_reps": 8, "actual_weight": 20, "is_completed": True},
            headers=headers,
        )
        assert saved.status_code == 200
    assert client.post(f"/api/v1/workouts/{today['id']}/finish", headers=headers).status_code == 200
    history = client.get("/api/v1/workouts/history", headers=headers).json()
    assert len(history) == 1
    assert {item["title"] for item in history[0]["exercises"]} == {
        floor_press["title"],
        seated_crunch["title"],
    }


def test_custom_exercise_structured_metadata_can_be_partial(client) -> None:
    headers = auth(client, telegram_user_id=32302, is_coach=False)

    minimal = client.post(
        "/api/v1/programs/exercises",
        json={"title": "Моё движение без классификации"},
        headers=headers,
    )
    assert minimal.status_code == 201
    assert minimal.json()["primary_muscle_ids"] == []
    assert minimal.json()["secondary_muscle_ids"] == []
    assert minimal.json()["equipment_ids"] == []
    assert minimal.json()["alternatives"] == []

    recognized = client.post(
        "/api/v1/programs/exercises",
        json={
            "title": "Мой жим гантелей",
            "primary_muscle": "shoulders",
            "equipment": "dumbbell",
        },
        headers=headers,
    )
    assert recognized.status_code == 201
    assert recognized.json()["primary_muscle_ids"] == ["shoulders"]
    assert recognized.json()["secondary_muscle_ids"] == []
    assert recognized.json()["equipment_ids"] == ["dumbbell"]
    assert recognized.json()["has_guide"] is False


def test_personalized_copy_keeps_guide_provenance_and_base_alternatives(client) -> None:
    headers = auth(client, telegram_user_id=32303, is_coach=False)
    catalog = client.get("/api/v1/programs/exercises", headers=headers).json()
    bench = next(item for item in catalog if item["slug"] == "bench-press")

    updated = client.patch(
        f"/api/v1/programs/exercises/{bench['edit_target_id']}",
        json={
            "title": "Мой жим лежа",
            "primary_muscle": "Плечи",
            "equipment": "Гантели",
        },
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == bench["id"]
    assert updated.json()["source_exercise_id"] == bench["id"]
    assert updated.json()["primary_muscle_ids"] == ["shoulders"]
    assert updated.json()["equipment_ids"] == ["dumbbell"]

    details = client.get(f"/api/v1/programs/exercises/{bench['id']}", headers=headers)
    assert details.status_code == 200
    assert details.json()["title"] == "Мой жим лежа"
    assert details.json()["guide"]["source_name"] == "Gym visual"
    assert details.json()["guide"]["media_reference"] == "exercise-guides:bench-press"
    assert {item["slug"] for item in details.json()["alternatives"]} == {
        "dumbbell-bench-press",
        "floor-press",
        "machine-chest-press",
    }


def test_exercise_domain_seed_is_idempotent() -> None:
    with get_session_context() as session:
        before = {
            "muscles": session.query(Muscle).count(),
            "equipment": session.query(Equipment).count(),
            "muscle_links": session.query(ExerciseMuscle).count(),
            "equipment_links": session.query(ExerciseEquipment).count(),
            "alternatives": session.query(ExerciseAlternative).count(),
            "guides": session.query(ExerciseGuideMetadata).count(),
        }
        seed_demo_data(session, include_demo_users=False)
        after = {
            "muscles": session.query(Muscle).count(),
            "equipment": session.query(Equipment).count(),
            "muscle_links": session.query(ExerciseMuscle).count(),
            "equipment_links": session.query(ExerciseEquipment).count(),
            "alternatives": session.query(ExerciseAlternative).count(),
            "guides": session.query(ExerciseGuideMetadata).count(),
        }
    assert before == after
    assert before["muscles"] == 26
    assert before["equipment"] == 9
    assert before["alternatives"] > 0


def test_exercise_catalog_metadata_loading_has_no_per_row_queries(client) -> None:
    headers = auth(client, telegram_user_id=32304, is_coach=False)
    select_count = 0

    def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        response = client.get("/api/v1/programs/exercises", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)

    assert response.status_code == 200
    assert len(response.json()) == 207
    assert select_count <= 20
