"""Exercise the real preview API against an isolated in-memory seed catalog (#1335)."""

from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQUIPMENT_PRESETS = {
    "bodyweight": ["bodyweight"],
    "dumbbells": ["bodyweight", "dumbbell"],
    "dumbbells_bench": ["bodyweight", "dumbbell", "bench"],
    "gym": ["bodyweight", "dumbbell", "barbell", "bench", "cable", "machine"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample", action="store_true", help="Run six representative requests")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "backend"))
    # Always override inherited database/auth settings; this tool never opens a live database.
    os.environ.update(
        APP_ENV="test",
        APP_NAME="YFC synthetic program matrix",
        APP_DEBUG="false",
        DATABASE_URL="sqlite:///:memory:",
        SECRET_KEY="synthetic-matrix-secret-at-least-thirty-two-characters",
        ACCESS_TOKEN_EXPIRE_MINUTES="60",
        REFRESH_TOKEN_EXPIRE_DAYS="30",
        ENABLE_DEV_AUTH="true",
        TELEGRAM_BOT_TOKEN="synthetic-test-token",
        NEWS_INGESTION_ENABLED="false",
        NEWS_PUBLICATION_ENABLED="false",
    )
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from fitminiapp_api.core.rate_limit import limiter
    from fitminiapp_api.db.base import Base
    from fitminiapp_api.db.session import get_db
    from fitminiapp_api.main import app
    from fitminiapp_api.models.user import User
    from fitminiapp_api.schemas.program_generator import ProgramGeneratorRequest
    from fitminiapp_api.services.program_generator import (
        SELECTION_POLICY_VERSION,
        _CandidateIncompatible,
        _evaluate_candidate,
        _load_catalog,
    )
    from fitminiapp_api.services.program_seed_data import STRENGTH_TEMPLATE_SPECS
    from fitminiapp_api.services.seed import seed_demo_data

    engine = create_engine(
        "sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)

    def matrix_db():
        with Session(engine) as db:
            yield db

    def counts():
        with Session(engine) as db:
            return {
                table.name: db.scalar(select(func.count()).select_from(table))
                for table in Base.metadata.sorted_tables
            }

    app.dependency_overrides[get_db] = matrix_db
    with Session(engine) as db:
        seed_demo_data(db, include_demo_users=False)
        db.commit()
    client = TestClient(app)
    try:
        auth = client.post("/api/v1/auth/dev-login", json={"telegram_user_id": 133500})
        assert auth.status_code == 200, auth.text
        headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
        with Session(engine) as db:
            user = db.query(User).filter(User.telegram_user_id == 133500).one()
            templates, visible, alternatives, revision, hidden = _load_catalog(db, user)
            assert {template.slug for template in templates} == {
                spec["slug"] for spec in STRENGTH_TEMPLATE_SPECS
            }
            before = counts()
            cases = []
            combinations = list(
                itertools.product(
                    ["fat_loss", "recomposition", "maintenance", "muscle_gain", "strength"],
                    ["beginner", "intermediate", "advanced"],
                    [2, 3, 4, 5, 6],
                    [30, 45, 60, 90],
                    EQUIPMENT_PRESETS,
                )
            )
            if args.sample:
                combinations = [
                    ("strength", "beginner", 3, 60, "gym"),
                    ("strength", "beginner", 2, 60, "gym"),
                    ("recomposition", "beginner", 3, 45, "dumbbells_bench"),
                    ("recomposition", "beginner", 2, 60, "dumbbells"),
                    ("recomposition", "beginner", 3, 60, "bodyweight"),
                    ("recomposition", "beginner", 3, 60, "gym"),
                ]
            for goal, experience, days, duration, preset in combinations:
                limiter.reset()
                payload = ProgramGeneratorRequest.model_validate(
                    {
                        "goal": goal,
                        "experience": experience,
                        "days_per_week": days,
                        "preferred_session_duration_minutes": duration,
                        "training_location": "gym" if preset == "gym" else "home",
                        "available_equipment_ids": EQUIPMENT_PRESETS[preset],
                    }
                )
                response = client.post(
                    "/api/v1/programs/generator/preview",
                    headers=headers,
                    json=payload.model_dump(mode="json"),
                )
                assert response.status_code == 200, response.text
                body = response.json()
                body.pop("draft_token", None)
                diagnostics = []
                for template in templates:
                    code = "compatible"
                    try:
                        _evaluate_candidate(template, payload, visible, alternatives)
                    except _CandidateIncompatible as exc:
                        code = exc.code
                    stage = (
                        "validated"
                        if code == "compatible"
                        else "selection"
                        if code
                        in {
                            "unsupported_structure",
                            "goal_not_supported",
                            "experience_incompatible",
                            "frequency_not_supported",
                        }
                        else "adaptation"
                    )
                    diagnostics.append(
                        {"slug": template.slug, "stage": stage, "first_failure": code}
                    )
                for suggestion in body.get("suggestions", []):
                    suggested = ProgramGeneratorRequest.model_validate(suggestion["inputs"])
                    assert suggested.experience == payload.experience
                    source = next(
                        t for t in templates if t.id == suggestion["source"]["template_id"]
                    )
                    _evaluate_candidate(source, suggested, visible, alternatives)
                if body["status"] == "preview":
                    assert body["program"]["goal"] == payload.goal
                    assert body["program"]["days_per_week"] == payload.days_per_week
                cases.append(
                    {
                        "inputs": payload.model_dump(mode="json"),
                        "response": body,
                        "candidates": diagnostics,
                    }
                )
            assert counts() == before, "Preview or suggestions persisted data"
            summary = Counter(
                "preview"
                if case["response"]["status"] == "preview"
                else "verified_path"
                if case["response"].get("suggestions")
                else "no_compatible"
                for case in cases
            )
            report = {
                "checkout_sha": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "environment": "isolated local DEV API / synthetic SQLite seed; no production data",
                "migration_validation": "NOT_RUN: ORM create_all; PostgreSQL migrations are checked separately",
                "selection_policy_version": SELECTION_POLICY_VERSION,
                "catalog_revision": revision,
                "catalog": [
                    {
                        "slug": t.slug,
                        "sessions_per_week": t.sessions_per_week,
                        "distinct_days": len(t.days),
                        "goal": t.goal,
                        "level": t.level,
                        "public": t.is_public,
                        "provenance": t.provenance_type,
                    }
                    for t in templates
                ],
                "visible_exercises": len(visible),
                "hidden_templates": sorted(hidden),
                "side_effects": "NONE: all table row counts unchanged",
                "total": len(cases),
                "summary": dict(summary),
                "cases": cases,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "total": len(cases),
                        "catalog": len(templates),
                        "summary": summary,
                        "side_effects": "NONE",
                    }
                )
            )
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


if __name__ == "__main__":
    main()
