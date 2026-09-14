from __future__ import annotations

import hashlib
import secrets
import threading
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from fitminiapp_api.schemas.demo import DemoScenario

DEMO_SESSION_TTL = timedelta(minutes=30)
MAX_ACTIVE_DEMO_SESSIONS = 500


class DemoSessionExpiredError(Exception):
    pass


class DemoSessionCapacityError(Exception):
    pass


class DemoActionForbiddenError(Exception):
    pass


class DemoTransitionError(Exception):
    pass


class _DemoCabinetNutritionPayload(TypedDict):
    calories: int
    calorie_target: int
    protein_g: float
    protein_target_g: float
    meals_logged: int
    item_added: bool
    recent_item: dict[str, Any]


@dataclass
class _DemoSession:
    scenario: DemoScenario
    state: dict[str, Any]
    revision: int
    created_at: datetime
    expires_at: datetime


def _training_fixture() -> dict[str, Any]:
    return {
        "kind": "self_training",
        "screen": "today",
        "workout_title": "Верх тела · уверенный старт",
        "workout_subtitle": "Неделя 4 · подготовленная тренировка на сегодня",
        "completed_sets": 2,
        "total_sets": 3,
        "exercises": [
            {
                "name": "Жим гантелей лёжа с контролируемой паузой",
                "prescription": "3 × 10 · 18 кг · отдых 90 сек.",
                "status": "current",
            },
            {
                "name": "Тяга верхнего блока нейтральным хватом",
                "prescription": "3 × 12 · 40 кг · отдых 75 сек.",
                "status": "next",
            },
        ],
        "duration_minutes": 0,
        "total_volume_kg": 0,
        "progress_change_percent": 0.0,
    }


def _nutrition_fixture() -> dict[str, Any]:
    return {
        "kind": "nutrition",
        "screen": "diary",
        "date_label": "Сегодня · подготовленный дневник",
        "item_added": False,
        "recent_item": {
            "name": "Овсяная каша с бананом и греческим йогуртом",
            "serving": "320 г · недавний продукт",
            "calories": 428,
            "protein_g": 24.0,
        },
        "calories": 1160,
        "calorie_target": 2150,
        "protein_g": 82.0,
        "protein_target_g": 145.0,
        "meals_logged": 2,
    }


def _trainer_fixture() -> dict[str, Any]:
    return {
        "kind": "trainer",
        "screen": "client",
        "selected_client_id": "alexey",
        "clients": [
            {
                "id": "alexey",
                "name": "Алексей",
                "status_label": "В ритме",
                "context_label": "8 из 8 тренировок за 4 недели · объём вырос на 6,5%",
                "workout_title": "Ноги и корпус · неделя 4",
                "facts": [
                    {"label": "Выполнено", "value": "6 из 6 упражнений"},
                    {"label": "Объём", "value": "6 840 кг"},
                    {"label": "Самочувствие", "value": "8 из 10"},
                    {"label": "Следующий ориентир", "value": "+2,5 кг в приседе"},
                ],
                "comment": None,
            },
            {
                "id": "maria",
                "name": "Мария",
                "status_label": "Нужна регулярность",
                "context_label": "6 из 8 тренировок за 4 недели · два пропуска подряд",
                "workout_title": "Всё тело · неделя 4",
                "facts": [
                    {"label": "Выполнено", "value": "4 из 6 упражнений"},
                    {"label": "Объём", "value": "4 920 кг"},
                    {"label": "Самочувствие", "value": "6 из 10"},
                    {"label": "Следующий ориентир", "value": "Вернуться к расписанию"},
                ],
                "comment": None,
            },
            {
                "id": "ivan",
                "name": "Иван",
                "status_label": "Плато",
                "context_label": "8 из 8 тренировок за 4 недели · объём без изменений 3 недели",
                "workout_title": "Верх тела · неделя 4",
                "facts": [
                    {"label": "Выполнено", "value": "5 из 5 упражнений"},
                    {"label": "Объём", "value": "6 120 кг"},
                    {"label": "Самочувствие", "value": "7 из 10"},
                    {"label": "Следующий ориентир", "value": "Обсудить прогрессию"},
                ],
                "comment": None,
            },
        ],
    }


def _program_fixture(completed_today: bool = False) -> dict[str, Any]:
    return {
        "name": "Силовая база",
        "current_week": 4,
        "total_weeks": 8,
        "sessions_per_week": 4,
        "schedule": [
            {"day_label": "Пн", "workout_title": "Верх тела", "status": "completed"},
            {"day_label": "Вт", "workout_title": "Кардио", "status": "completed"},
            {
                "day_label": "Ср",
                "workout_title": "Ноги и корпус",
                "status": "completed" if completed_today else "planned",
            },
            {"day_label": "Чт", "workout_title": "Отдых", "status": "rest"},
            {"day_label": "Пт", "workout_title": "Верх тела", "status": "planned"},
            {"day_label": "Сб", "workout_title": "Кардио", "status": "planned"},
            {"day_label": "Вс", "workout_title": "Отдых", "status": "rest"},
        ],
    }


def _training_history_fixture(completed_today: bool = False) -> list[dict[str, Any]]:
    history = [
        {
            "period_label": "4 недели назад",
            "workout_title": "Ноги и корпус",
            "completed_sets": 16,
            "volume_kg": 5920,
        },
        {
            "period_label": "3 недели назад",
            "workout_title": "Верх тела",
            "completed_sets": 17,
            "volume_kg": 6080,
        },
        {
            "period_label": "2 недели назад",
            "workout_title": "Верх тела",
            "completed_sets": 18,
            "volume_kg": 6220,
        },
        {
            "period_label": "На прошлой неделе",
            "workout_title": "Ноги и корпус",
            "completed_sets": 18,
            "volume_kg": 6480,
        },
    ]
    if completed_today:
        history.append(
            {
                "period_label": "Сегодня",
                "workout_title": "Верх тела · уверенный старт",
                "completed_sets": 3,
                "volume_kg": 6840,
            }
        )
    return history


def _volume_history_fixture(completed_today: bool = False) -> list[dict[str, Any]]:
    history = [
        {"period_label": "4 недели назад", "volume_kg": 5920},
        {"period_label": "3 недели назад", "volume_kg": 6080},
        {"period_label": "2 недели назад", "volume_kg": 6220},
        {"period_label": "На прошлой неделе", "volume_kg": 6480},
    ]
    if completed_today:
        history.append({"period_label": "Сегодня", "volume_kg": 6840})
    return history


def _nutrition_history_fixture(item_added: bool = False) -> list[dict[str, Any]]:
    return [
        {"date_label": "4 дня назад", "status": "complete", "calories": 1980, "protein_g": 132.0},
        {"date_label": "3 дня назад", "status": "complete", "calories": 2140, "protein_g": 141.0},
        {"date_label": "2 дня назад", "status": "incomplete", "calories": 1160, "protein_g": 82.0},
        {"date_label": "Вчера", "status": "complete", "calories": 2060, "protein_g": 139.0},
        {
            "date_label": "Сегодня",
            "status": "complete" if item_added else "incomplete",
            "calories": 1588 if item_added else 1160,
            "protein_g": 106.0 if item_added else 82.0,
        },
        {"date_label": "Позавчера", "status": "not_logged", "calories": None, "protein_g": None},
        {"date_label": "6 дней назад", "status": "complete", "calories": 2010, "protein_g": 128.0},
    ]


def _measurements_fixture() -> list[dict[str, str]]:
    return [
        {"label": "Вес", "value": "77,8 кг", "date_label": "4 недели назад"},
        {"label": "Вес", "value": "77,1 кг", "date_label": "Сегодня"},
    ]


def _fixture_for(scenario: DemoScenario) -> dict[str, Any]:
    fixtures = {
        "self_training": _training_fixture,
        "nutrition": _nutrition_fixture,
        "trainer": _trainer_fixture,
    }
    return fixtures[scenario]()


def _cabinet_for(scenario: DemoScenario, state: dict[str, Any]) -> dict[str, Any]:
    training_completed = scenario == "self_training" and state["screen"] in {"summary", "progress"}
    nutrition_added = scenario == "nutrition" and state["item_added"]
    trainer_commented = scenario == "trainer" and any(
        client["comment"] is not None for client in state["clients"]
    )

    program = _program_fixture(training_completed)

    nutrition: _DemoCabinetNutritionPayload = (
        {
            "calories": state["calories"],
            "calorie_target": state["calorie_target"],
            "protein_g": state["protein_g"],
            "protein_target_g": state["protein_target_g"],
            "meals_logged": state["meals_logged"],
            "item_added": state["item_added"],
            "recent_item": deepcopy(state["recent_item"]),
        }
        if scenario == "nutrition"
        else {
            "calories": 1580 if scenario == "self_training" else 1760,
            "calorie_target": 2150 if scenario == "self_training" else 2350,
            "protein_g": 104.0 if scenario == "self_training" else 126.0,
            "protein_target_g": 145.0 if scenario == "self_training" else 160.0,
            "meals_logged": 3,
            "item_added": True,
            "recent_item": {
                "name": "Творог с ягодами",
                "serving": "220 г · подготовленная запись",
                "calories": 286,
                "protein_g": 31.0,
            },
        }
    )

    if scenario == "self_training":
        today = {
            "title": state["workout_title"],
            "summary": state["workout_subtitle"],
            "status_label": "Тренировка завершена" if training_completed else "Остался один подход",
            "completed_days": 3 if training_completed else 2,
            "planned_days": 4,
        }
        progress = {
            "workouts_completed": 12 if training_completed else 11,
            "latest_volume_kg": state["total_volume_kg"] if training_completed else 6220,
            "volume_change_percent": state["progress_change_percent"]
            if training_completed
            else 4.2,
            "nutrition_days_logged": 5,
            "nutrition_completion_percent": round(
                nutrition["calories"] / nutrition["calorie_target"] * 100
            ),
            "adherence_percent": 82 if training_completed else 78,
            "training_history": _training_history_fixture(training_completed),
            "volume_history": _volume_history_fixture(training_completed),
            "nutrition_history": _nutrition_history_fixture(),
            "measurements": _measurements_fixture(),
            "summary": (
                "Сегодняшняя тренировка уже учтена в динамике."
                if training_completed
                else "Динамика обновится после завершения тренировки."
            ),
        }
        conversion_title = "Готово. Вы посмотрели основной сценарий"
    elif scenario == "nutrition":
        today = {
            "title": "Дневник питания на сегодня",
            "summary": "Быстро добавьте подготовленный недавний продукт и проверьте новый итог.",
            "status_label": "Дневной итог обновлён" if nutrition_added else "Дневник не завершён",
            "completed_days": 5 if nutrition_added else 4,
            "planned_days": 7,
        }
        progress = {
            "workouts_completed": 10,
            "latest_volume_kg": 6480,
            "volume_change_percent": 3.8,
            "nutrition_days_logged": 6 if nutrition_added else 5,
            "nutrition_completion_percent": round(
                nutrition["calories"] / nutrition["calorie_target"] * 100
            ),
            "adherence_percent": 86 if nutrition_added else 79,
            "training_history": _training_history_fixture(),
            "volume_history": _volume_history_fixture(),
            "nutrition_history": _nutrition_history_fixture(nutrition_added),
            "measurements": _measurements_fixture(),
            "summary": (
                "Новая запись уже отражена в дневном итоге."
                if nutrition_added
                else "Итог использует только подтверждённые записи."
            ),
        }
        conversion_title = "Готово. Вы посмотрели основной сценарий"
    else:
        today = {
            "title": "Результат клиента готов к разбору",
            "summary": next(
                client["context_label"]
                for client in state["clients"]
                if client["id"] == state["selected_client_id"]
            ),
            "status_label": "Комментарий сохранён" if trainer_commented else "Нужна обратная связь",
            "completed_days": 4,
            "planned_days": 5,
        }
        progress = {
            "workouts_completed": 16,
            "latest_volume_kg": 6840,
            "volume_change_percent": 5.1,
            "nutrition_days_logged": 5,
            "nutrition_completion_percent": round(
                nutrition["calories"] / nutrition["calorie_target"] * 100
            ),
            "adherence_percent": 88,
            "training_history": _training_history_fixture(),
            "volume_history": _volume_history_fixture(),
            "nutrition_history": _nutrition_history_fixture(),
            "measurements": _measurements_fixture(),
            "summary": (
                "Комментарий связан с подготовленным результатом клиента."
                if trainer_commented
                else "Факты тренировки готовы для контекстной обратной связи."
            ),
        }
        conversion_title = "Готово. Вы посмотрели основной сценарий"

    return {
        "program": program,
        "today": today,
        "nutrition": nutrition,
        "progress": progress,
        "trainer": deepcopy(state) if scenario == "trainer" else None,
        "meaningful_action_completed": training_completed or nutrition_added or trainer_commented,
        "conversion_title": conversion_title,
    }


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DemoSessionStore:
    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        ttl: timedelta = DEMO_SESSION_TTL,
        max_sessions: int = MAX_ACTIVE_DEMO_SESSIONS,
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._ttl = ttl
        self._max_sessions = max_sessions
        self._sessions: dict[str, _DemoSession] = {}
        self._lock = threading.RLock()

    def _prune_expired(self, now: datetime) -> None:
        expired = [key for key, value in self._sessions.items() if value.expires_at <= now]
        for key in expired:
            self._sessions.pop(key, None)

    def _session(self, token: str, now: datetime) -> _DemoSession:
        digest = _token_digest(token)
        session = self._sessions.get(digest)
        if session is None or session.expires_at <= now:
            self._sessions.pop(digest, None)
            raise DemoSessionExpiredError
        return session

    @staticmethod
    def _snapshot(session: _DemoSession) -> dict[str, Any]:
        return {
            "capability": "demo",
            "scenario": session.scenario,
            "fixture_version": "demo-curated-v2",
            "revision": session.revision,
            "expires_at": session.expires_at,
            "state": deepcopy(session.state),
            "cabinet": _cabinet_for(session.scenario, session.state),
        }

    def create(self, scenario: DemoScenario) -> tuple[str, dict[str, Any]]:
        with self._lock:
            now = self._now()
            self._prune_expired(now)
            if len(self._sessions) >= self._max_sessions:
                raise DemoSessionCapacityError
            token = secrets.token_urlsafe(32)
            session = _DemoSession(
                scenario=scenario,
                state=_fixture_for(scenario),
                revision=1,
                created_at=now,
                expires_at=now + self._ttl,
            )
            self._sessions[_token_digest(token)] = session
            return token, self._snapshot(session)

    def get(self, token: str) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            self._prune_expired(now)
            return self._snapshot(self._session(token, now))

    def reset(self, token: str) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            session = self._session(token, now)
            session.state = _fixture_for(session.scenario)
            session.revision += 1
            session.expires_at = now + self._ttl
            return self._snapshot(session)

    def apply_action(
        self,
        token: str,
        action: str,
        comment: str | None = None,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            session = self._session(token, now)
            changed = self._apply_allowed_action(session, action, comment, client_id)
            if changed:
                session.revision += 1
            return self._snapshot(session)

    @staticmethod
    def _apply_allowed_action(
        session: _DemoSession,
        action: str,
        comment: str | None,
        client_id: str | None,
    ) -> bool:
        state = session.state
        if session.scenario == "self_training":
            return DemoSessionStore._apply_training_action(state, action)
        if session.scenario == "nutrition":
            return DemoSessionStore._apply_nutrition_action(state, action)
        if session.scenario == "trainer":
            return DemoSessionStore._apply_trainer_action(state, action, comment, client_id)
        raise DemoActionForbiddenError

    @staticmethod
    def _apply_training_action(state: dict[str, Any], action: str) -> bool:
        screen = state["screen"]
        if action == "start_workout":
            if screen == "active_workout":
                return False
            if screen != "today":
                raise DemoTransitionError
            state["screen"] = "active_workout"
            return True
        if action == "complete_set":
            if screen != "active_workout":
                raise DemoTransitionError
            if state["completed_sets"] >= state["total_sets"]:
                return False
            state["completed_sets"] = state["total_sets"]
            state["exercises"][0]["status"] = "completed"
            state["exercises"][1]["status"] = "current"
            return True
        if action == "finish_workout":
            if screen == "summary":
                return False
            if screen != "active_workout" or state["completed_sets"] < state["total_sets"]:
                raise DemoTransitionError
            state["screen"] = "summary"
            state["duration_minutes"] = 46
            state["total_volume_kg"] = 6840
            return True
        if action == "open_progress":
            if screen == "progress":
                return False
            if screen != "summary":
                raise DemoTransitionError
            state["screen"] = "progress"
            state["progress_change_percent"] = 6.5
            return True
        raise DemoActionForbiddenError

    @staticmethod
    def _apply_nutrition_action(state: dict[str, Any], action: str) -> bool:
        if action == "add_recent":
            if state["screen"] != "diary":
                raise DemoTransitionError
            if state["item_added"]:
                return False
            item = state["recent_item"]
            state["item_added"] = True
            state["calories"] += item["calories"]
            state["protein_g"] += item["protein_g"]
            state["meals_logged"] += 1
            return True
        if action == "open_nutrition_report":
            if state["screen"] == "report":
                return False
            if state["screen"] != "diary" or not state["item_added"]:
                raise DemoTransitionError
            state["screen"] = "report"
            return True
        raise DemoActionForbiddenError

    @staticmethod
    def _apply_trainer_action(
        state: dict[str, Any],
        action: str,
        comment: str | None,
        client_id: str | None,
    ) -> bool:
        if action == "select_client":
            if client_id is None:
                raise DemoTransitionError
            available_ids = {client["id"] for client in state["clients"]}
            if client_id not in available_ids:
                raise DemoTransitionError
            if state["selected_client_id"] == client_id:
                return False
            state["selected_client_id"] = client_id
            return True
        if action != "save_comment":
            raise DemoActionForbiddenError
        if comment is None:
            raise DemoTransitionError
        selected_client = next(
            client for client in state["clients"] if client["id"] == state["selected_client_id"]
        )
        if selected_client["comment"] == comment:
            return False
        selected_client["comment"] = comment
        return True


demo_session_store = DemoSessionStore()
