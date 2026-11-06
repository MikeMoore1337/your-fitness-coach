from datetime import timedelta

from fitminiapp_api.core.timezone import today_in_timezone


def _auth(client) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 1431001, "is_coach": False, "is_admin": False},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_copy_day_same_date_keeps_server_validation(client) -> None:
    headers = _auth(client)
    today = today_in_timezone("Europe/Moscow").isoformat()
    body = {"source_date": today, "target_date": today}
    response = client.post(
        "/api/v1/nutrition/diary/copy/day/preview",
        headers=headers,
        json=body,
    )
    print(f"same-day request={body}; response={response.status_code} {response.json()}")
    assert response.status_code == 422
    assert response.json() == {"detail": "source and target day must differ"}


def test_copy_day_preserves_source_nutrition_and_replays_once(client) -> None:
    headers = _auth(client)
    target = today_in_timezone("Europe/Moscow")
    source = target - timedelta(days=1)
    for meal, calories in (("breakfast", "320"), ("dinner", "520")):
        response = client.post(
            "/api/v1/nutrition/diary/entries",
            headers=headers,
            json={
                "quick_add": {
                    "energy_kcal": calories,
                    "protein_g": "35",
                    "fat_g": "18",
                    "carbs_g": "52",
                },
                "diary_date": source.isoformat(),
                "meal_type": meal,
                "amount": "1",
                "amount_unit": "serving",
            },
        )
        assert response.status_code == 201, response.text

    def day(date):
        response = client.get(
            "/api/v1/nutrition/diary", headers=headers, params={"diary_date": date.isoformat()}
        )
        assert response.status_code == 200, response.text
        return response.json()

    source_before = day(source)
    target_before = day(target)
    body = {"source_date": source.isoformat(), "target_date": target.isoformat()}
    preview = client.post("/api/v1/nutrition/diary/copy/day/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert day(target)["meals"] == target_before["meals"]
    payload = {**body, "preview_token": preview.json()["preview_token"]}
    copy_headers = {**headers, "Idempotency-Key": "copy-day-1431-test"}
    copied = client.post("/api/v1/nutrition/diary/copy/day", headers=copy_headers, json=payload)
    replay = client.post("/api/v1/nutrition/diary/copy/day", headers=copy_headers, json=payload)
    duplicate = client.post(
        "/api/v1/nutrition/diary/copy/day",
        headers={**headers, "Idempotency-Key": "copy-day-1431-other"},
        json=payload,
    )
    assert copied.status_code == replay.status_code == 201
    assert duplicate.status_code == 409
    assert copied.json()["replayed"] is False
    assert replay.json()["replayed"] is True
    assert [entry["id"] for entry in copied.json()["entries"]] == [
        entry["id"] for entry in replay.json()["entries"]
    ]
    source_entries = [entry for meal in source_before["meals"] for entry in meal["entries"]]
    copied_entries = copied.json()["entries"]
    assert [(entry["meal_type"], entry["nutrition"]) for entry in copied_entries] == [
        (entry["meal_type"], entry["nutrition"]) for entry in source_entries
    ]
    assert day(source)["meals"] == source_before["meals"]
    target_after = day(target)
    assert sum(len(meal["entries"]) for meal in target_after["meals"]) == 2
    assert target_after["totals"] == source_before["totals"]


def test_copy_day_empty_source_and_fasted_target_fail_without_writes(client) -> None:
    headers = _auth(client)
    today = today_in_timezone("Europe/Moscow")
    source = today - timedelta(days=2)
    target = today - timedelta(days=1)
    body = {"source_date": source.isoformat(), "target_date": target.isoformat()}
    empty = client.post("/api/v1/nutrition/diary/copy/day/preview", headers=headers, json=body)
    assert empty.status_code == 422
    assert empty.json()["detail"] == "source day is empty"
    fasted = client.put(
        "/api/v1/nutrition/diary/status",
        headers=headers,
        json={"diary_date": target.isoformat(), "status": "fasted"},
    )
    assert fasted.status_code == 200
    blocked = client.post("/api/v1/nutrition/diary/copy/day/preview", headers=headers, json=body)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == (
        "day is marked as fasted; change completeness before adding food"
    )
    target_after = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": target.isoformat()}
    ).json()
    assert target_after["status"] == "fasted"
    assert all(not meal["entries"] for meal in target_after["meals"])


def test_copy_day_rejects_preview_after_source_changes(client) -> None:
    headers = _auth(client)
    target = today_in_timezone("Europe/Moscow")
    source = target - timedelta(days=1)
    entry = {
        "quick_add": {"energy_kcal": "320"},
        "diary_date": source.isoformat(),
        "meal_type": "breakfast",
        "amount": "1",
        "amount_unit": "serving",
    }
    assert (
        client.post("/api/v1/nutrition/diary/entries", headers=headers, json=entry).status_code
        == 201
    )
    body = {"source_date": source.isoformat(), "target_date": target.isoformat()}
    preview = client.post("/api/v1/nutrition/diary/copy/day/preview", headers=headers, json=body)
    assert preview.status_code == 200
    assert (
        client.post("/api/v1/nutrition/diary/entries", headers=headers, json=entry).status_code
        == 201
    )
    confirm = client.post(
        "/api/v1/nutrition/diary/copy/day",
        headers={**headers, "Idempotency-Key": "copy-day-1431-stale"},
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert confirm.status_code == 409
    assert confirm.json()["detail"] == "repeat preview is stale; request a new preview"
    target_after = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": target.isoformat()}
    ).json()
    assert all(not meal["entries"] for meal in target_after["meals"])
