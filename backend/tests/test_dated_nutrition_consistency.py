from __future__ import annotations

import csv
import io
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import User


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (-11, None),
        (-5, (2000, 150, 70, 200)),
        (0, (1800, 140, 60, 180)),
    ],
)
def test_diary_report_and_csv_use_the_same_dated_target(client, offset, expected) -> None:
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 952001, "is_coach": False},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    today = today_msk()
    selected_date = today + timedelta(days=offset)
    change_day = today - timedelta(days=3)
    with get_session_context() as db:
        user_id = db.query(User.id).filter(User.telegram_user_id == 952001).scalar()
        db.add_all(
            [
                NutritionTarget(
                    user_id=user_id,
                    source="manual",
                    effective_from=today - timedelta(days=10),
                    effective_to=change_day,
                    calories=2000,
                    protein_g=150,
                    fat_g=70,
                    carbs_g=200,
                    saved_at=datetime.combine(today - timedelta(days=10), time()),
                ),
                NutritionTarget(
                    user_id=user_id,
                    source="manual",
                    effective_from=change_day,
                    calories=1800,
                    protein_g=140,
                    fat_g=60,
                    carbs_g=180,
                    saved_at=datetime.combine(change_day, time()),
                ),
            ]
        )

    params = {
        "period": "custom",
        "date_from": selected_date.isoformat(),
        "date_to": today.isoformat(),
    }
    report = client.get(
        "/api/v1/workouts/progress/nutrition-report", params=params, headers=headers
    )
    export = client.get(
        "/api/v1/workouts/progress/nutrition-report.csv", params=params, headers=headers
    )
    diary = client.get(
        "/api/v1/nutrition/diary", params={"diary_date": selected_date.isoformat()}, headers=headers
    )
    assert report.status_code == export.status_code == diary.status_code == 200
    report_day = next(
        day for day in report.json()["daily"] if day["diary_date"] == selected_date.isoformat()
    )
    csv_day = next(
        row
        for row in csv.DictReader(io.StringIO(export.text.lstrip("\ufeff")))
        if row["diary_date"] == selected_date.isoformat()
    )
    targets = diary.json()["targets"]
    if expected is None:
        assert targets is None
        assert report_day["target_calories"] is None
        assert csv_day["target_calories_kcal"] == ""
        return

    for value, diary_key, report_key, csv_key in zip(
        expected,
        ("energy_kcal", "protein_g", "fat_g", "carbs_g"),
        ("target_calories", "target_protein_g", "target_fat_g", "target_carbs_g"),
        ("target_calories_kcal", "target_protein_g", "target_fat_g", "target_carbs_g"),
        strict=True,
    ):
        assert Decimal(targets[diary_key]) == Decimal(value)
        assert report_day[report_key] == value
        assert Decimal(csv_day[csv_key]) == Decimal(value)
