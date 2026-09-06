import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import ProgramTemplate, ProgramTemplateDay, UserProgram
from fitminiapp_api.schemas.program import ProgramRecommendationRequest
from fitminiapp_api.services.program_recommendation import (
    ProgramCandidate,
    RecommendationCriteria,
    rank_program_candidates,
)


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _recommend(client, headers, **payload):
    return client.post(
        "/api/v1/programs/templates/recommendation",
        headers=headers,
        json=payload,
    )


def test_recommendation_requires_authenticated_user(client):
    response = _recommend(
        client,
        {},
        goal="recomposition",
        experience="beginner",
        workouts_per_week=3,
    )

    assert response.status_code == 401


def test_legacy_template_duration_defaults_to_one_week_without_backfill():
    template = ProgramTemplate(
        slug="legacy-duration-template",
        title="Legacy duration",
        goal="recomposition",
        level="intermediate",
        is_public=True,
    )

    assert template.default_duration_weeks is None
    assert template.effective_duration_weeks == 1

    template.default_duration_weeks = 12
    assert template.effective_duration_weeks == 12


@pytest.mark.parametrize(
    ("goal", "experience", "workouts_per_week", "expected_status"),
    [
        (goal, experience, workouts_per_week, expected_status)
        for goal in ("fat_loss", "recomposition", "maintenance", "muscle_gain", "strength")
        for experience in ("beginner", "intermediate", "advanced")
        for workouts_per_week in (2, 3, 4, 5)
        for expected_status in (
            "no_match"
            if goal == "strength" or (experience == "beginner" and workouts_per_week == 5)
            else "recommended",
        )
    ],
)
def test_recommendation_matrix_is_controlled_for_goals_levels_and_frequency(
    client,
    goal,
    experience,
    workouts_per_week,
    expected_status,
):
    headers = _auth(client, 92000 + workouts_per_week)

    response = _recommend(
        client,
        headers,
        goal=goal,
        experience=experience,
        workouts_per_week=workouts_per_week,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == expected_status
    assert body["requires_explicit_start"] is True
    if expected_status == "recommended":
        assert body["recommendation"]["template"]["id"] > 0
        assert body["recommendation"]["reason"]
        assert body["recommendation"]["fit_facts"]
    else:
        assert body["recommendation"] is None


@pytest.mark.parametrize(
    ("goal", "experience", "workouts_per_week", "expected_slug"),
    [
        ("fat_loss", "beginner", 2, "strength-fullbody-3d"),
        ("recomposition", "beginner", 3, "strength-fullbody-3d"),
        ("recomposition", "intermediate", 4, "strength-upper-lower-4d"),
        ("muscle_gain", "intermediate", 5, "strength-split-5d"),
        ("muscle_gain", "advanced", 6, "strength-push-pull-legs-6d"),
        ("muscle_gain", "advanced", 8, "strength-pplf-8d"),
    ],
)
def test_decision_table_selects_expected_real_template(
    client,
    goal,
    experience,
    workouts_per_week,
    expected_slug,
):
    headers = _auth(client, 92100 + workouts_per_week)

    response = _recommend(
        client,
        headers,
        goal=goal,
        experience=experience,
        workouts_per_week=workouts_per_week,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "recommended"
    assert body["recommendation"]["template"]["slug"] == expected_slug
    assert "%" not in body["recommendation"]["reason"]


def test_recommendation_uses_profile_without_starting_program(client):
    headers = _auth(client, 92201)
    profile_response = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={
            "goal": "recomposition",
            "level": "intermediate",
            "workouts_per_week": 4,
        },
    )
    assert profile_response.status_code == 200, profile_response.text

    first = _recommend(client, headers)
    second = _recommend(client, headers)

    assert first.status_code == 200, first.text
    assert first.json() == second.json()
    assert first.json()["criteria"]["profile_fields_used"] == [
        "goal",
        "experience",
        "workouts_per_week",
    ]
    assert first.json()["recommendation"]["template"]["slug"] == ("strength-upper-lower-4d")
    with get_session_context() as db:
        assert db.query(UserProgram).count() == 0


def test_recommendation_reports_missing_profile_and_strength_no_match(client):
    headers = _auth(client, 92202)

    missing = _recommend(client, headers)
    strength = _recommend(
        client,
        headers,
        goal="strength",
        experience="advanced",
        workouts_per_week=5,
    )

    assert missing.status_code == 200
    assert missing.json()["status"] == "needs_input"
    assert missing.json()["missing_fields"] == ["goal", "experience", "workouts_per_week"]
    assert strength.status_code == 200
    assert strength.json()["status"] == "no_match"
    assert "сил" in strength.json()["message"].lower()


def test_equipment_mismatch_is_excluded_and_invalid_equipment_is_rejected(client):
    headers = _auth(client, 92203)

    mismatch = _recommend(
        client,
        headers,
        goal="recomposition",
        experience="beginner",
        workouts_per_week=3,
        training_location="home",
        available_equipment_ids=["bodyweight"],
    )
    invalid = _recommend(
        client,
        headers,
        goal="recomposition",
        experience="beginner",
        workouts_per_week=3,
        available_equipment_ids=["unknown"],
    )

    assert mismatch.status_code == 200
    assert mismatch.json()["status"] == "no_match"
    assert "оборудован" in mismatch.json()["message"].lower()
    assert invalid.status_code == 422


def test_hidden_best_template_is_not_recommended_and_tie_break_is_stable(client):
    headers = _auth(client, 92204)
    templates = client.get("/api/v1/programs/templates/mine", headers=headers).json()
    upper_lower = next(item for item in templates if item["slug"] == "strength-upper-lower-4d")
    hidden = client.delete(
        f"/api/v1/programs/templates/{upper_lower['id']}",
        headers=headers,
    )
    assert hidden.status_code == 204

    responses = [
        _recommend(
            client,
            headers,
            goal="recomposition",
            experience="intermediate",
            workouts_per_week=4,
        ).json()
        for _ in range(3)
    ]

    assert {item["recommendation"]["template"]["slug"] for item in responses} == {
        "strength-pplf-4d"
    }


def test_tie_break_and_legacy_metadata_are_deterministic_without_database():
    def candidate(template_id: int, slug: str, split_type: str | None) -> ProgramCandidate:
        template = ProgramTemplate(
            id=template_id,
            slug=slug,
            title=slug,
            goal="recomposition",
            level="intermediate",
            split_type=split_type,
            is_public=True,
        )
        template.days = [
            ProgramTemplateDay(day_number=index, title=f"Day {index}") for index in range(1, 5)
        ]
        return ProgramCandidate(
            template=template,
            required_equipment_ids=frozenset(),
            equipment_metadata_complete=True,
        )

    criteria = RecommendationCriteria(
        goal="recomposition",
        experience="intermediate",
        workouts_per_week=4,
        training_location=None,
        available_equipment_ids=None,
        profile_fields_used=(),
    )

    result = rank_program_candidates(
        [
            candidate(3, "z-template", "upper_lower"),
            candidate(2, "legacy-template", None),
            candidate(1, "a-template", "upper_lower"),
        ],
        criteria,
    )

    assert [item.candidate.template.slug for item in result.ranked_candidates] == [
        "a-template",
        "z-template",
    ]


def test_preferred_exercise_breaks_tie_and_avoided_exercise_excludes_candidate():
    def candidate(template_id: int, slug: str, exercise_ids: set[int]) -> ProgramCandidate:
        template = ProgramTemplate(
            id=template_id,
            slug=slug,
            title=slug,
            goal="recomposition",
            level="intermediate",
            split_type="upper_lower",
            is_public=True,
        )
        template.days = [
            ProgramTemplateDay(day_number=index, title=f"Day {index}") for index in range(1, 5)
        ]
        return ProgramCandidate(
            template=template,
            required_equipment_ids=frozenset(),
            equipment_metadata_complete=True,
            exercise_ids=frozenset(exercise_ids),
        )

    criteria = RecommendationCriteria(
        goal="recomposition",
        experience="intermediate",
        workouts_per_week=4,
        training_location=None,
        available_equipment_ids=None,
        preferred_exercise_ids=frozenset({22}),
        avoided_exercise_ids=frozenset({99}),
    )

    result = rank_program_candidates(
        [
            candidate(1, "without-preferred", {1}),
            candidate(2, "with-preferred", {22}),
            candidate(3, "with-avoided", {22, 99}),
        ],
        criteria,
    )

    assert [item.candidate.template.slug for item in result.ranked_candidates] == [
        "with-preferred",
        "without-preferred",
    ]


def test_request_rejects_duplicate_equipment():
    with pytest.raises(ValidationError, match="must be unique"):
        ProgramRecommendationRequest(
            available_equipment_ids=["dumbbell", "dumbbell"],
        )


def test_program_split_migration_backfills_known_templates_and_preserves_legacy(tmp_path: Path):
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0041_program_template_split_type.py"
    )
    spec = importlib.util.spec_from_file_location("program_split_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "0040_workout_set_rir"

    migration_engine = sa.create_engine(
        f"sqlite:///{(tmp_path / 'program-split-migration.db').as_posix()}"
    )
    metadata = sa.MetaData()
    templates = sa.Table(
        "program_templates",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
    )
    metadata.create_all(migration_engine)

    with migration_engine.begin() as connection:
        connection.execute(
            templates.insert(),
            [
                {"id": 1, "slug": "strength-fullbody-3d"},
                {"id": 2, "slug": "legacy-template"},
            ],
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = connection.execute(
            sa.text("SELECT slug, split_type FROM program_templates ORDER BY id")
        ).all()
        assert rows == [("strength-fullbody-3d", "full_body"), ("legacy-template", None)]

        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.execute(
                sa.text(
                    "INSERT INTO program_templates (id, slug, split_type) "
                    "VALUES (3, 'invalid', 'unknown')"
                )
            )

        migration.downgrade()
        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("program_templates")
        }
        assert "split_type" not in columns

    migration_engine.dispose()
