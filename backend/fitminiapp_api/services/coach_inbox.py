from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.coach_crm import CoachOperationsTodayResponse
from fitminiapp_api.schemas.coach_reviews import CoachCheckInReviewListResponse
from fitminiapp_api.services.coach_attention import build_coach_attention
from fitminiapp_api.services.coach_crm import operations_today
from fitminiapp_api.services.coach_reviews import list_coach_check_in_reviews

_PRIORITY_RANK = {"urgent": 0, "soon": 1, "normal": 2}


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _evidence(label: str, value: object) -> dict[str, str]:
    return {"label": label, "value": str(value)}


def _operation_destination(tool: str) -> str:
    return f"/coach?tab=tools&tool={tool}"


def build_coach_inbox(
    db: Session,
    coach: User,
    *,
    limit: int = 50,
) -> dict[str, object]:
    """Compose one bounded coach workspace from existing authoritative read models.

    The source services already batch their relation reads. This adapter only normalizes
    actionable facts; it intentionally drops notes and other private payload fields.
    """

    attention = build_coach_attention(db, coach, limit=100)
    pending_reviews = CoachCheckInReviewListResponse.model_validate(
        list_coach_check_in_reviews(
            db,
            coach,
            status="pending",
            limit=100,
            offset=0,
        )
    )
    operations = CoachOperationsTodayResponse.model_validate(operations_today(db, coach))
    generated_at = now_msk_naive()
    now = datetime.now(UTC)
    items: list[dict[str, object]] = []
    source_keys: set[tuple[str, int]] = set()
    item_keys: set[str] = set()

    def add(item: dict[str, object]) -> None:
        key = str(item["key"])
        if key in item_keys:
            return
        item_keys.add(key)
        source_kind = item.get("source_kind")
        source_id = item.get("source_id")
        if isinstance(source_kind, str) and isinstance(source_id, int):
            source_keys.add((source_kind, source_id))
        items.append(item)

    for source in attention["items"]:
        source_kind = str(source["source_kind"])
        source_id = int(source["source_id"])
        add(
            {
                "key": f"attention:{source['key']}",
                "kind": "attention",
                "client": source["client"],
                "title": source["title"],
                "reason": source["reason"],
                "source_kind": source_kind,
                "source_id": source_id,
                "action": source["action"],
                "destination": source["destination"],
                "priority": source.get("priority", "normal"),
                "created_at": source["created_at"],
                "evidence": source.get("evidence", []),
            }
        )

    for review in pending_reviews.items:
        check_in_id = review.check_in_id
        if ("weekly_check_in", check_in_id) in source_keys:
            continue
        created_at = review.created_at
        add(
            {
                "key": f"check-in:{check_in_id}",
                "kind": "check_in",
                "client": {"id": review.client_id, "name": review.client_name},
                "title": "Новый недельный итог",
                "reason": "Клиент заполнил недельный итог.",
                "source_kind": "weekly_check_in",
                "source_id": check_in_id,
                "action": "review_check_in",
                "destination": f"/coach?client_id={review.client_id}&focus=weekly_check_in",
                "priority": "urgent",
                "created_at": created_at,
                "evidence": [
                    _evidence("Событие", "Недельный итог отправлен"),
                    _evidence("Неделя", review.week_start),
                ],
            }
        )

    operation_tasks = [*operations.overdue_tasks, *operations.due_tasks]
    for task in operation_tasks:
        if (
            task.source_kind
            and task.source_id
            and (task.source_kind, task.source_id) in source_keys
        ):
            continue
        due_at = task.due_at
        add(
            {
                "key": f"task:{task.id}",
                "kind": "task",
                "client": {"id": task.client_id, "name": task.client_name},
                "title": task.title,
                "reason": task.reason or "Открытая задача тренера.",
                "source_kind": task.source_kind or "task",
                "source_id": task.source_id or task.id,
                "action": "open_task",
                "destination": _operation_destination("tasks"),
                "priority": "urgent" if _aware(due_at) <= now else "soon",
                "created_at": task.created_at,
                "due_at": due_at,
                "evidence": [_evidence("Срок", due_at.isoformat())],
            }
        )

    for session in operations.sessions:
        add(
            {
                "key": f"session:{session.id}",
                "kind": "session",
                "client": {"id": session.client_id, "name": session.client_name},
                "title": "Встреча сегодня",
                "reason": f"{session.starts_at.strftime('%H:%M')} · {session.duration_minutes} мин.",
                "source_kind": "session",
                "source_id": session.id,
                "action": "open_schedule",
                "destination": _operation_destination("schedule"),
                "priority": "soon",
                "created_at": session.created_at,
                "due_at": session.starts_at,
                "evidence": [_evidence("Статус", session.status)],
            }
        )

    for package in operations.low_packages:
        balance = package.balance if package.balance is not None else "—"
        add(
            {
                "key": f"package:{package.id}",
                "kind": "package",
                "client": {"id": package.client_id, "name": package.client_name},
                "title": "Пакет требует проверки",
                "reason": f"Осталось встреч: {balance}.",
                "source_kind": "package",
                "source_id": package.id,
                "action": "open_finance",
                "destination": _operation_destination("finance"),
                "priority": "soon",
                "created_at": package.updated_at,
                "evidence": [_evidence("Состояние", package.state)],
            }
        )

    for payment in operations.payment_facts:
        add(
            {
                "key": f"payment:{payment.id}",
                "kind": "payment",
                "client": {"id": payment.client_id, "name": payment.client_name},
                "title": "Ожидается оплата",
                "reason": f"Статус: {payment.status} · {payment.currency}.",
                "source_kind": "payment",
                "source_id": payment.id,
                "action": "open_finance",
                "destination": _operation_destination("finance"),
                "priority": "normal",
                "created_at": payment.updated_at,
                "evidence": [_evidence("Дата", payment.payment_date or "не указана")],
            }
        )

    def sort_key(item: dict[str, object]) -> tuple[int, float, str]:
        event_at = item.get("due_at") or item["created_at"]
        return (
            _PRIORITY_RANK[str(item["priority"])],
            _aware(_as_datetime(event_at)).timestamp(),
            str(item["key"]),
        )

    items.sort(key=sort_key)
    total = len(items)
    bounded_limit = max(1, min(limit, 100))
    return {
        "date": operations.date,
        "timezone": operations.timezone,
        "items": items[:bounded_limit],
        "total": total,
        "counts": {
            "attention": int(attention["total"]),
            "pending_reviews": pending_reviews.total,
            "tasks": len(operation_tasks),
            "sessions": len(operations.sessions),
            "packages": len(operations.low_packages),
            "payments": len(operations.payment_facts),
        },
        "generated_at": generated_at,
    }


__all__ = ["build_coach_inbox"]
