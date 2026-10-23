from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Event, get_ident

import pytest
from sqlalchemy import event

from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food_diary import (
    FoodDiaryDayStatusUpdate,
    FoodDiaryEntryCreate,
    FoodDiaryEntryUpdate,
)
from fitminiapp_api.services.food_diary import (
    FoodDiaryConflictError,
    create_food_diary_entry,
    set_food_diary_day_status,
    update_food_diary_entry,
)


def _create_diary_user_and_food(telegram_user_id: int) -> tuple[int, int]:
    with get_session_context() as db:
        user = User(telegram_user_id=telegram_user_id)
        db.add(user)
        db.flush()
        food = Food(
            name="Тестовый продукт целостности",
            brand="YFC",
            energy_kcal_per_100g=Decimal("200"),
            protein_g_per_100g=Decimal("10"),
            fat_g_per_100g=Decimal("5"),
            carbs_g_per_100g=Decimal("30"),
            fiber_g_per_100g=Decimal("4"),
            standard_serving_amount=Decimal("1"),
            standard_serving_unit="serving",
            standard_serving_weight_g=Decimal("50"),
            food_type="system",
            owner_user_id=None,
            provenance="internal",
            source_name="yfc-test",
            trust_level="verified",
            status="active",
        )
        db.add(food)
        db.flush()
        return user.id, food.id


def _entry_payload(food_id: int, diary_date: date, amount: str = "100") -> FoodDiaryEntryCreate:
    return FoodDiaryEntryCreate(
        food_id=food_id,
        diary_date=diary_date,
        meal_type="breakfast",
        amount=Decimal(amount),
        amount_unit="g",
    )


def _wait_for_worker_user_lock(
    worker, user_id: int
) -> tuple[ThreadPoolExecutor, Future[object], Event, Callable]:
    worker_ready = Event()
    lock_started = Event()
    worker_thread_id: int | None = None

    def wrapped_worker():
        nonlocal worker_thread_id
        worker_thread_id = get_ident()
        worker_ready.set()
        return worker()

    def observe_user_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
        if (
            worker_thread_id == get_ident()
            and "FOR UPDATE" in statement.upper()
            and "USER" in statement.upper()
            and str(user_id) in str(_parameters)
        ):
            lock_started.set()

    event.listen(engine, "before_cursor_execute", observe_user_lock)
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(wrapped_worker)
    assert worker_ready.wait(timeout=5)
    return executor, future, lock_started, observe_user_lock


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_diary_entry_cannot_cross_a_concurrent_fasted_transition() -> None:
    user_id, food_id = _create_diary_user_and_food(982_820)
    diary_date = date.today()
    owner_db = SessionLocal()
    owner = owner_db.get(User, user_id)
    assert owner is not None
    owner_db.query(User.id).filter(User.id == user_id).with_for_update().one()

    def create_entry():
        db = SessionLocal()
        try:
            create_food_diary_entry(db, db.get(User, user_id), _entry_payload(food_id, diary_date))
            return "created"
        except FoodDiaryConflictError:
            db.rollback()
            return "rejected"
        finally:
            db.close()

    executor, future, lock_started, observe_user_lock = _wait_for_worker_user_lock(
        create_entry, user_id
    )
    try:
        assert lock_started.wait(timeout=5)
        status = set_food_diary_day_status(
            owner_db,
            owner,
            FoodDiaryDayStatusUpdate(diary_date=diary_date, status="fasted"),
        )
        assert status.status == "fasted"
        assert future.result(timeout=5) == "rejected"
    finally:
        owner_db.rollback()
        event.remove(engine, "before_cursor_execute", observe_user_lock)
        executor.shutdown(wait=True)
        owner_db.close()

    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_diary_edits_are_serialized_before_recalculating_the_latest_entry() -> None:
    user_id, food_id = _create_diary_user_and_food(982_821)
    diary_date = date.today()
    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None
        created = create_food_diary_entry(db, user, _entry_payload(food_id, diary_date))
        entry_id = created.id

    owner_db = SessionLocal()
    owner = owner_db.get(User, user_id)
    assert owner is not None
    owner_db.query(User.id).filter(User.id == user_id).with_for_update().one()

    def edit_meal():
        db = SessionLocal()
        try:
            return update_food_diary_entry(
                db,
                db.get(User, user_id),
                entry_id,
                FoodDiaryEntryUpdate(meal_type="lunch"),
            )
        finally:
            db.close()

    executor, future, lock_started, observe_user_lock = _wait_for_worker_user_lock(
        edit_meal, user_id
    )
    try:
        assert lock_started.wait(timeout=5)
        update_food_diary_entry(
            owner_db,
            owner,
            entry_id,
            FoodDiaryEntryUpdate(amount=Decimal("150"), amount_unit="g"),
        )
        future.result(timeout=5)
    finally:
        owner_db.rollback()
        event.remove(engine, "before_cursor_execute", observe_user_lock)
        executor.shutdown(wait=True)
        owner_db.close()

    with get_session_context() as db:
        entry = db.get(FoodDiaryEntry, entry_id)
        assert entry is not None
        assert entry.amount == Decimal("150.000")
        assert entry.meal_type == "lunch"
