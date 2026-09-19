from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    get_user_timezone_name,
    is_valid_timezone,
    local_naive_to_utc_naive_strict,
    now_msk_naive,
    today_in_timezone,
    utc_naive_to_timezone_naive,
)
from fitminiapp_api.models.coach_crm import (
    CoachBusinessSession,
    CoachPackage,
    CoachPackageLedgerEntry,
    CoachPayment,
    CoachSessionSeries,
    CoachTask,
)
from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.user import CoachClient, User, UserProfile
from fitminiapp_api.schemas.coach_crm import (
    CoachPackageCreate,
    CoachPackageResponse,
    CoachPaymentCreate,
    CoachPaymentResponse,
    CoachPaymentUpdate,
    CoachSessionCreate,
    CoachSessionResponse,
    CoachSessionUpdate,
    CoachTaskCreate,
    CoachTaskResponse,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.coach_clients import get_client_managed_by_coach
from fitminiapp_api.services.program_common import ProgramError


class CoachCrmError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _client_name(user: User) -> str:
    profile_name = user.profile.full_name if user.profile else None
    return profile_name or user.username or f"Клиент #{user.id}"


def _managed_client(db: Session, coach: User, client_id: int) -> User:
    try:
        return get_client_managed_by_coach(db, coach, client_id)
    except ProgramError as exc:
        raise CoachCrmError("Клиент не найден в активном списке тренера", 404) from exc


def _ensure_timezone(timezone_name: str) -> None:
    if not is_valid_timezone(timezone_name):
        raise CoachCrmError("Укажите корректную IANA timezone", 422)


def _local_naive(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)


def _to_utc(value: datetime, timezone_name: str, fold: int) -> datetime:
    _ensure_timezone(timezone_name)
    try:
        return local_naive_to_utc_naive_strict(
            _local_naive(value, timezone_name), timezone_name, fold=fold
        )
    except ValueError as exc:
        raise CoachCrmError(
            "Время не существует в выбранной timezone из-за перехода DST", 422
        ) from exc


def _local_response(value: datetime, timezone_name: str) -> datetime:
    return utc_naive_to_timezone_naive(value, timezone_name).replace(tzinfo=ZoneInfo(timezone_name))


def _client_names(db: Session, client_ids: set[int]) -> dict[int, str]:
    if not client_ids:
        return {}
    rows = (
        db.query(User.id, User.username, UserProfile.full_name)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(User.id.in_(client_ids))
        .all()
    )
    return {
        user_id: full_name or username or f"Клиент #{user_id}"
        for user_id, username, full_name in rows
    }


def _ledger_totals(db: Session, package_ids: set[int]) -> dict[int, dict[str, int]]:
    if not package_ids:
        return {}
    rows = (
        db.query(
            CoachPackageLedgerEntry.package_id,
            CoachPackageLedgerEntry.entry_type,
            func.coalesce(func.sum(CoachPackageLedgerEntry.quantity), 0),
        )
        .filter(CoachPackageLedgerEntry.package_id.in_(package_ids))
        .group_by(CoachPackageLedgerEntry.package_id, CoachPackageLedgerEntry.entry_type)
        .all()
    )
    result: dict[int, dict[str, int]] = defaultdict(lambda: {"charge": 0, "reversal": 0})
    for package_id, entry_type, quantity in rows:
        result[package_id][entry_type] = int(quantity)
    return dict(result)


def _package_response(
    package: CoachPackage,
    name: str,
    totals: dict[str, int],
) -> CoachPackageResponse:
    charged = totals.get("charge", 0)
    reversed_count = totals.get("reversal", 0)
    balance = (
        package.included_sessions - charged + reversed_count
        if package.counts_sessions and package.included_sessions is not None
        else None
    )
    return CoachPackageResponse(
        id=package.id,
        client_id=package.client_user_id,
        client_name=name,
        name=package.name,
        counts_sessions=package.counts_sessions,
        included_sessions=package.included_sessions,
        charged_sessions=charged,
        reversed_sessions=reversed_count,
        balance=balance,
        starts_on=package.starts_on,
        expires_on=package.expires_on,
        state=package.state,
        note=package.note,
        created_at=package.created_at,
        updated_at=package.updated_at,
    )


def _payment_status(payment: CoachPayment) -> str:
    if payment.status == "cancelled":
        return "cancelled"
    if payment.paid_amount_minor == 0:
        return "expected"
    if payment.paid_amount_minor < payment.expected_amount_minor:
        return "partial"
    return "paid"


def _payment_response(payment: CoachPayment, name: str) -> CoachPaymentResponse:
    return CoachPaymentResponse(
        id=payment.id,
        client_id=payment.client_user_id,
        client_name=name,
        package_id=payment.package_id,
        expected_amount_minor=payment.expected_amount_minor,
        paid_amount_minor=payment.paid_amount_minor,
        currency=payment.currency,
        payment_date=payment.payment_date,
        method=payment.method,
        note=payment.note,
        status=_payment_status(payment),
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


def _task_response(task: CoachTask, name: str) -> CoachTaskResponse:
    return CoachTaskResponse(
        id=task.id,
        client_id=task.client_user_id,
        client_name=name,
        title=task.title,
        due_at=_local_response(task.due_at_utc, task.timezone),
        due_at_utc=task.due_at_utc.replace(tzinfo=UTC),
        timezone=task.timezone,
        state=task.state,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _session_response(
    session: CoachBusinessSession,
    name: str,
    package_totals: dict[int, dict[str, int]],
    package_map: dict[int, CoachPackage],
) -> CoachSessionResponse:
    package = package_map.get(session.package_id) if session.package_id else None
    totals = package_totals.get(session.package_id or 0, {})
    balance = None
    if package and package.counts_sessions and package.included_sessions is not None:
        balance = package.included_sessions - totals.get("charge", 0) + totals.get("reversal", 0)
    return CoachSessionResponse(
        id=session.id,
        client_id=session.client_user_id,
        client_name=name,
        starts_at=_local_response(session.starts_at_utc, session.timezone),
        starts_at_utc=session.starts_at_utc.replace(tzinfo=UTC),
        timezone=session.timezone,
        duration_minutes=session.duration_minutes,
        format=session.format,
        location=session.location,
        status=session.status,
        private_note=session.private_note,
        package_id=session.package_id,
        package_balance=balance,
        user_workout_id=session.user_workout_id,
        series_id=session.series_id,
        occurrence_key=session.occurrence_key,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _session_responses(db: Session, rows: list[CoachBusinessSession]) -> list[CoachSessionResponse]:
    client_map = _client_names(db, {row.client_user_id for row in rows})
    package_ids = {row.package_id for row in rows if row.package_id is not None}
    package_map = {
        package.id: package
        for package in db.query(CoachPackage).filter(CoachPackage.id.in_(package_ids)).all()
    }
    totals = _ledger_totals(db, package_ids)
    return [
        _session_response(
            row,
            client_map.get(row.client_user_id, f"Клиент #{row.client_user_id}"),
            totals,
            package_map,
        )
        for row in rows
    ]


def _session_end(starts_at_utc: datetime, duration_minutes: int) -> datetime:
    return starts_at_utc + timedelta(minutes=duration_minutes)


def _check_conflicts(
    db: Session,
    coach_id: int,
    candidates: list[tuple[datetime, int]],
    *,
    exclude_id: int | None = None,
) -> None:
    if not candidates:
        return
    earliest = min(value for value, _ in candidates) - timedelta(days=2)
    latest = max(value + timedelta(minutes=duration) for value, duration in candidates)
    existing = (
        db.query(CoachBusinessSession)
        .filter(
            CoachBusinessSession.coach_user_id == coach_id,
            CoachBusinessSession.starts_at_utc >= earliest,
            CoachBusinessSession.starts_at_utc < latest,
            CoachBusinessSession.status != "cancelled",
        )
        .all()
    )
    for candidate_start, candidate_duration in candidates:
        candidate_end = _session_end(candidate_start, candidate_duration)
        for row in existing:
            if row.id == exclude_id:
                continue
            if row.starts_at_utc < candidate_end and candidate_start < _session_end(
                row.starts_at_utc, row.duration_minutes
            ):
                raise CoachCrmError(
                    "В расписании уже есть пересекающееся business-занятие. Выберите другое время.",
                    409,
                )
    for index, (left_start, left_duration) in enumerate(candidates):
        left_end = _session_end(left_start, left_duration)
        for right_start, right_duration in candidates[index + 1 :]:
            if left_start < _session_end(right_start, right_duration) and right_start < left_end:
                raise CoachCrmError("Повторяющиеся занятия пересекаются между собой", 409)


def _recurrence_occurrences(
    payload: CoachSessionCreate,
) -> tuple[list[tuple[datetime, str | None]], datetime]:
    _ensure_timezone(payload.timezone)
    local_start = _local_naive(payload.starts_at, payload.timezone)
    recurrence = payload.recurrence
    if recurrence is None:
        return [(local_start, None)], _to_utc(payload.starts_at, payload.timezone, payload.fold)
    if recurrence.until and recurrence.until < local_start.date():
        raise CoachCrmError("Дата окончания повторения раньше первого занятия", 422)
    limit_date = min(
        recurrence.until or local_start.date() + timedelta(days=366),
        local_start.date() + timedelta(days=366),
    )
    occurrences: list[tuple[datetime, str | None]] = []
    cursor = local_start.date()
    while cursor <= limit_date and len(occurrences) < (recurrence.occurrence_count or 52):
        if cursor.weekday() in recurrence.weekdays:
            value = datetime.combine(cursor, local_start.time())
            occurrences.append((value, cursor.isoformat()))
        cursor += timedelta(days=1)
    if not occurrences:
        raise CoachCrmError("В заданном диапазоне нет выбранных дней недели", 422)
    if recurrence.occurrence_count and len(occurrences) < recurrence.occurrence_count:
        raise CoachCrmError("Не удалось построить все повторения в ограниченном диапазоне", 422)
    return occurrences, _to_utc(local_start, payload.timezone, payload.fold)


def _get_package(
    db: Session,
    coach: User,
    client_id: int,
    package_id: int | None,
    *,
    lock: bool,
) -> CoachPackage | None:
    if package_id is None:
        return None
    query = db.query(CoachPackage).filter(
        CoachPackage.id == package_id,
        CoachPackage.coach_user_id == coach.id,
        CoachPackage.client_user_id == client_id,
    )
    if lock:
        query = query.with_for_update()
    package = query.first()
    if package is None:
        raise CoachCrmError("Пакет клиента не найден", 404)
    return package


def _charge_package(db: Session, coach: User, session: CoachBusinessSession) -> None:
    if session.package_id is None:
        return
    package = _get_package(db, coach, session.client_user_id, session.package_id, lock=True)
    if package is None or not package.counts_sessions:
        return
    latest_charge = (
        db.query(CoachPackageLedgerEntry)
        .filter(
            CoachPackageLedgerEntry.package_id == package.id,
            CoachPackageLedgerEntry.session_id == session.id,
            CoachPackageLedgerEntry.entry_type == "charge",
        )
        .order_by(CoachPackageLedgerEntry.id.desc())
        .first()
    )
    if latest_charge is not None:
        active_reversal = (
            db.query(CoachPackageLedgerEntry.id)
            .filter(
                CoachPackageLedgerEntry.package_id == package.id,
                CoachPackageLedgerEntry.session_id == session.id,
                CoachPackageLedgerEntry.entry_type == "reversal",
                CoachPackageLedgerEntry.id > latest_charge.id,
            )
            .first()
        )
        if active_reversal is None:
            return
    if package.state != "active":
        raise CoachCrmError("Нельзя списать занятие из неактивного пакета", 409)
    totals = _ledger_totals(db, {package.id}).get(package.id, {})
    balance = package.included_sessions - totals.get("charge", 0) + totals.get("reversal", 0)
    if balance <= 0:
        raise CoachCrmError("В пакете закончились занятия", 409)
    charge_count = (
        db.query(func.count(CoachPackageLedgerEntry.id))
        .filter(
            CoachPackageLedgerEntry.package_id == package.id,
            CoachPackageLedgerEntry.entry_type == "charge",
        )
        .scalar()
        or 0
    )
    db.add(
        CoachPackageLedgerEntry(
            package_id=package.id,
            session_id=session.id,
            actor_user_id=coach.id,
            entry_type="charge",
            quantity=1,
            idempotency_key=f"session:{session.id}:charge:{charge_count + 1}",
            reason="completed_session" if session.status == "completed" else "no_show_policy",
        )
    )
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=session.client_user_id,
        action="coach.package_charge",
        resource_type="coach_package",
        resource_id=package.id,
        details={"session_id": session.id, "quantity": 1},
    )


def _reverse_package_charge(db: Session, coach: User, session: CoachBusinessSession) -> None:
    if session.package_id is None:
        return
    package = _get_package(db, coach, session.client_user_id, session.package_id, lock=True)
    if package is None or not package.counts_sessions:
        return
    charged = (
        db.query(CoachPackageLedgerEntry)
        .filter(
            CoachPackageLedgerEntry.package_id == package.id,
            CoachPackageLedgerEntry.session_id == session.id,
            CoachPackageLedgerEntry.entry_type == "charge",
        )
        .order_by(CoachPackageLedgerEntry.id.desc())
        .first()
    )
    if charged is None:
        return
    already_reversed = (
        db.query(CoachPackageLedgerEntry.id)
        .filter(
            CoachPackageLedgerEntry.package_id == package.id,
            CoachPackageLedgerEntry.session_id == session.id,
            CoachPackageLedgerEntry.entry_type == "reversal",
            CoachPackageLedgerEntry.id > charged.id,
        )
        .first()
    )
    if already_reversed is not None:
        return
    db.add(
        CoachPackageLedgerEntry(
            package_id=package.id,
            session_id=session.id,
            actor_user_id=coach.id,
            entry_type="reversal",
            quantity=1,
            idempotency_key=f"session:{session.id}:reversal:{charged.id}",
            reason="session_status_reverted",
        )
    )
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=session.client_user_id,
        action="coach.package_reversal",
        resource_type="coach_package",
        resource_id=package.id,
        details={"session_id": session.id, "quantity": 1},
    )


def list_sessions(
    db: Session,
    coach: User,
    *,
    date_from: date,
    date_to: date,
) -> list[CoachSessionResponse]:
    if date_to < date_from or date_to - date_from > timedelta(days=42):
        raise CoachCrmError("Диапазон agenda ограничен 42 днями", 422)
    timezone_name = get_user_timezone_name(coach)
    start_utc = local_naive_to_utc_naive_strict(
        datetime.combine(date_from, time.min), timezone_name
    )
    end_utc = local_naive_to_utc_naive_strict(
        datetime.combine(date_to + timedelta(days=1), time.min), timezone_name
    )
    rows = (
        db.query(CoachBusinessSession)
        .filter(
            CoachBusinessSession.coach_user_id == coach.id,
            CoachBusinessSession.starts_at_utc < end_utc,
            CoachBusinessSession.starts_at_utc >= start_utc - timedelta(days=2),
        )
        .order_by(CoachBusinessSession.starts_at_utc.asc(), CoachBusinessSession.id.asc())
        .all()
    )
    rows = [
        row
        for row in rows
        if date_from <= _local_response(row.starts_at_utc, row.timezone).date() <= date_to
    ]
    return _session_responses(db, rows)


def create_sessions(
    db: Session,
    coach: User,
    payload: CoachSessionCreate,
    *,
    idempotency_key: str | None = None,
) -> list[CoachSessionResponse]:
    db.query(User.id).filter(User.id == coach.id).with_for_update().one()
    client = _managed_client(db, coach, payload.client_id)
    package = _get_package(db, coach, client.id, payload.package_id, lock=True)
    if payload.user_workout_id is not None:
        workout_exists = (
            db.query(UserWorkout.id)
            .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
            .filter(UserWorkout.id == payload.user_workout_id, UserProgram.user_id == client.id)
            .first()
        )
        if workout_exists is None:
            raise CoachCrmError("Тренировка клиента не найдена", 404)
    if idempotency_key:
        existing_series = (
            db.query(CoachSessionSeries)
            .filter(
                CoachSessionSeries.coach_user_id == coach.id,
                CoachSessionSeries.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing_series:
            rows = (
                db.query(CoachBusinessSession)
                .filter(CoachBusinessSession.series_id == existing_series.id)
                .order_by(CoachBusinessSession.starts_at_utc.asc())
                .all()
            )
            return _session_responses(db, rows)
        existing_session = (
            db.query(CoachBusinessSession)
            .filter(
                CoachBusinessSession.coach_user_id == coach.id,
                CoachBusinessSession.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing_session:
            return _session_responses(db, [existing_session])

    occurrences, _ = _recurrence_occurrences(payload)
    utc_occurrences = [
        (_to_utc(local_value, payload.timezone, payload.fold), occurrence_key)
        for local_value, occurrence_key in occurrences
    ]
    _check_conflicts(
        db,
        coach.id,
        [(utc_value, payload.duration_minutes) for utc_value, _ in utc_occurrences],
    )
    series = None
    if payload.recurrence is not None:
        local_start = _local_naive(payload.starts_at, payload.timezone)
        series = CoachSessionSeries(
            coach_user_id=coach.id,
            client_user_id=client.id,
            package_id=package.id if package else None,
            idempotency_key=idempotency_key,
            weekdays=payload.recurrence.weekdays,
            start_date=local_start.date(),
            start_time=local_start.time(),
            recurrence_end_date=payload.recurrence.until,
            occurrence_count=payload.recurrence.occurrence_count,
            timezone=payload.timezone,
            duration_minutes=payload.duration_minutes,
            format=payload.format,
            location=payload.location.strip() if payload.location else None,
        )
        db.add(series)
        db.flush()
    created_rows: list[CoachBusinessSession] = []
    for utc_value, occurrence_key in utc_occurrences:
        row = CoachBusinessSession(
            coach_user_id=coach.id,
            client_user_id=client.id,
            series_id=series.id if series else None,
            package_id=package.id if package else None,
            user_workout_id=payload.user_workout_id,
            occurrence_key=occurrence_key,
            idempotency_key=idempotency_key if series is None else None,
            starts_at_utc=utc_value,
            timezone=payload.timezone,
            duration_minutes=payload.duration_minutes,
            format=payload.format,
            location=payload.location.strip() if payload.location else None,
            private_note=payload.private_note.strip() if payload.private_note else None,
        )
        db.add(row)
        created_rows.append(row)
    db.flush()
    for row in created_rows:
        record_audit_event(
            db,
            actor_user_id=coach.id,
            target_user_id=client.id,
            action="coach.business_session_created",
            resource_type="coach_business_session",
            resource_id=row.id,
            details={"status": row.status, "series": bool(series)},
        )
    db.commit()
    return _session_responses(db, created_rows)


def update_session(
    db: Session,
    coach: User,
    session_id: int,
    payload: CoachSessionUpdate,
) -> CoachSessionResponse:
    db.query(User.id).filter(User.id == coach.id).with_for_update().one()
    row = (
        db.query(CoachBusinessSession)
        .filter(
            CoachBusinessSession.id == session_id, CoachBusinessSession.coach_user_id == coach.id
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise CoachCrmError("Business-занятие не найдено", 404)
    client = _managed_client(db, coach, row.client_user_id)
    if payload.apply_to == "series" and row.series_id is not None:
        if payload.starts_at is not None:
            raise CoachCrmError("Перенос всей серии требует отдельного выбора дат", 422)
        targets = (
            db.query(CoachBusinessSession)
            .filter(
                CoachBusinessSession.coach_user_id == coach.id,
                CoachBusinessSession.series_id == row.series_id,
                CoachBusinessSession.status == "scheduled",
                CoachBusinessSession.starts_at_utc >= row.starts_at_utc,
            )
            .with_for_update()
            .all()
        )
    else:
        targets = [row]
    for target in targets:
        new_timezone = payload.timezone or target.timezone
        new_start = target.starts_at_utc
        if payload.starts_at is not None:
            new_start = _to_utc(payload.starts_at, new_timezone, payload.fold)
        new_duration = payload.duration_minutes or target.duration_minutes
        if new_start != target.starts_at_utc or new_duration != target.duration_minutes:
            _check_conflicts(
                db,
                coach.id,
                [(new_start, new_duration)],
                exclude_id=target.id,
            )
        previous_status = target.status
        target.starts_at_utc = new_start
        target.timezone = new_timezone
        if payload.duration_minutes is not None:
            target.duration_minutes = payload.duration_minutes
        if payload.format is not None:
            target.format = payload.format
        if payload.location is not None:
            target.location = payload.location.strip() or None
        if payload.private_note is not None:
            target.private_note = payload.private_note.strip() or None
        status_changed = payload.status is not None and payload.status != previous_status
        if payload.status is not None and (status_changed or payload.charge_package is not None):
            target.status = payload.status
            should_charge = payload.status == "completed" or (
                payload.status == "no_show" and payload.charge_package is True
            )
            if should_charge:
                _charge_package(db, coach, target)
            else:
                _reverse_package_charge(db, coach, target)
            if status_changed:
                record_audit_event(
                    db,
                    actor_user_id=coach.id,
                    target_user_id=client.id,
                    action="coach.business_session_status_changed",
                    resource_type="coach_business_session",
                    resource_id=target.id,
                    details={"from": previous_status, "to": target.status},
                )
        target.updated_at = now_msk_naive()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.business_session_updated",
        resource_type="coach_business_session",
        resource_id=row.id,
        details={"scope": payload.apply_to},
    )
    db.commit()
    return _session_responses(db, [row])[0]


def list_packages(
    db: Session, coach: User, client_id: int | None = None
) -> list[CoachPackageResponse]:
    query = db.query(CoachPackage).filter(CoachPackage.coach_user_id == coach.id)
    if client_id is not None:
        _managed_client(db, coach, client_id)
        query = query.filter(CoachPackage.client_user_id == client_id)
    rows = query.order_by(CoachPackage.updated_at.desc(), CoachPackage.id.desc()).all()
    names = _client_names(db, {row.client_user_id for row in rows})
    totals = _ledger_totals(db, {row.id for row in rows})
    return [
        _package_response(row, names.get(row.client_user_id, "Клиент"), totals.get(row.id, {}))
        for row in rows
    ]


def create_package(
    db: Session,
    coach: User,
    payload: CoachPackageCreate,
    *,
    idempotency_key: str | None = None,
) -> CoachPackageResponse:
    client = _managed_client(db, coach, payload.client_id)
    if idempotency_key:
        existing = (
            db.query(CoachPackage)
            .filter(
                CoachPackage.coach_user_id == coach.id,
                CoachPackage.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing:
            totals = _ledger_totals(db, {existing.id})
            return _package_response(
                existing,
                _client_name(client),
                totals.get(existing.id, {}),
            )
    package = CoachPackage(
        coach_user_id=coach.id,
        client_user_id=client.id,
        idempotency_key=idempotency_key,
        name=payload.name.strip(),
        counts_sessions=payload.counts_sessions,
        included_sessions=payload.included_sessions,
        starts_on=payload.starts_on,
        expires_on=payload.expires_on,
        note=payload.note.strip() if payload.note else None,
    )
    db.add(package)
    db.flush()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.package_created",
        resource_type="coach_package",
        resource_id=package.id,
        details={"counts_sessions": package.counts_sessions},
    )
    db.commit()
    return _package_response(package, _client_name(client), {})


def update_package_state(
    db: Session,
    coach: User,
    package_id: int,
    state: str,
) -> CoachPackageResponse:
    package = (
        db.query(CoachPackage)
        .filter(CoachPackage.id == package_id, CoachPackage.coach_user_id == coach.id)
        .with_for_update()
        .first()
    )
    if package is None:
        raise CoachCrmError("Пакет не найден", 404)
    _managed_client(db, coach, package.client_user_id)
    previous = package.state
    package.state = state
    package.updated_at = now_msk_naive()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=package.client_user_id,
        action="coach.package_state_changed",
        resource_type="coach_package",
        resource_id=package.id,
        details={"from": previous, "to": state},
    )
    db.commit()
    return list_packages(db, coach, package.client_user_id)[0]


def list_payments(
    db: Session, coach: User, client_id: int | None = None
) -> list[CoachPaymentResponse]:
    query = db.query(CoachPayment).filter(CoachPayment.coach_user_id == coach.id)
    if client_id is not None:
        _managed_client(db, coach, client_id)
        query = query.filter(CoachPayment.client_user_id == client_id)
    rows = query.order_by(CoachPayment.payment_date.desc(), CoachPayment.id.desc()).all()
    names = _client_names(db, {row.client_user_id for row in rows})
    return [_payment_response(row, names.get(row.client_user_id, "Клиент")) for row in rows]


def create_payment(
    db: Session,
    coach: User,
    payload: CoachPaymentCreate,
    *,
    idempotency_key: str | None = None,
) -> CoachPaymentResponse:
    client = _managed_client(db, coach, payload.client_id)
    if payload.package_id is not None:
        _get_package(db, coach, client.id, payload.package_id, lock=False)
    if idempotency_key:
        existing = (
            db.query(CoachPayment)
            .filter(
                CoachPayment.coach_user_id == coach.id,
                CoachPayment.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing:
            return _payment_response(existing, _client_name(client))
    payment = CoachPayment(
        coach_user_id=coach.id,
        client_user_id=client.id,
        package_id=payload.package_id,
        idempotency_key=idempotency_key,
        expected_amount_minor=payload.expected_amount_minor,
        paid_amount_minor=payload.paid_amount_minor,
        currency=payload.currency,
        payment_date=payload.payment_date,
        method=payload.method.strip() if payload.method else None,
        note=payload.note.strip() if payload.note else None,
        status=(
            "expected"
            if payload.paid_amount_minor == 0
            else "partial"
            if payload.paid_amount_minor < payload.expected_amount_minor
            else "paid"
        ),
    )
    db.add(payment)
    db.flush()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.payment_recorded",
        resource_type="coach_payment",
        resource_id=payment.id,
        details={"status": payment.status, "currency": payment.currency},
    )
    db.commit()
    return _payment_response(payment, _client_name(client))


def update_payment(
    db: Session,
    coach: User,
    payment_id: int,
    payload: CoachPaymentUpdate,
) -> CoachPaymentResponse:
    payment = (
        db.query(CoachPayment)
        .filter(CoachPayment.id == payment_id, CoachPayment.coach_user_id == coach.id)
        .with_for_update()
        .first()
    )
    if payment is None:
        raise CoachCrmError("Запись об оплате не найдена", 404)
    client = _managed_client(db, coach, payment.client_user_id)
    expected_amount_minor = payload.expected_amount_minor or payment.expected_amount_minor
    paid_amount_minor = (
        payload.paid_amount_minor
        if payload.paid_amount_minor is not None
        else payment.paid_amount_minor
    )
    if paid_amount_minor > expected_amount_minor:
        raise CoachCrmError("Оплата не может быть больше ожидаемой суммы", 422)
    previous_status = payment.status
    payment.expected_amount_minor = expected_amount_minor
    payment.paid_amount_minor = paid_amount_minor
    if payload.currency is not None:
        payment.currency = payload.currency
    if payload.payment_date is not None:
        payment.payment_date = payload.payment_date
    if payload.method is not None:
        payment.method = payload.method.strip() or None
    if payload.note is not None:
        payment.note = payload.note.strip() or None
    payment.status = (
        "cancelled"
        if payload.status == "cancelled"
        else "expected"
        if paid_amount_minor == 0
        else "partial"
        if paid_amount_minor < expected_amount_minor
        else "paid"
    )
    payment.updated_at = now_msk_naive()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.payment_updated",
        resource_type="coach_payment",
        resource_id=payment.id,
        details={"from": previous_status, "to": payment.status},
    )
    db.commit()
    return _payment_response(payment, _client_name(client))


def list_tasks(
    db: Session,
    coach: User,
    *,
    client_id: int | None = None,
    state: str | None = None,
) -> list[CoachTaskResponse]:
    query = db.query(CoachTask).filter(CoachTask.coach_user_id == coach.id)
    if client_id is not None:
        _managed_client(db, coach, client_id)
        query = query.filter(CoachTask.client_user_id == client_id)
    if state:
        query = query.filter(CoachTask.state == state)
    rows = query.order_by(CoachTask.due_at_utc.asc(), CoachTask.id.asc()).all()
    names = _client_names(db, {row.client_user_id for row in rows})
    return [_task_response(row, names.get(row.client_user_id, "Клиент")) for row in rows]


def create_task(
    db: Session,
    coach: User,
    payload: CoachTaskCreate,
    *,
    idempotency_key: str | None = None,
) -> CoachTaskResponse:
    client = _managed_client(db, coach, payload.client_id)
    due_at_utc = _to_utc(payload.due_at, payload.timezone, payload.fold)
    if idempotency_key:
        existing = (
            db.query(CoachTask)
            .filter(
                CoachTask.coach_user_id == coach.id,
                CoachTask.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing:
            return _task_response(existing, _client_name(client))
    task = CoachTask(
        coach_user_id=coach.id,
        client_user_id=client.id,
        idempotency_key=idempotency_key,
        title=payload.title.strip(),
        due_at_utc=due_at_utc,
        timezone=payload.timezone,
    )
    db.add(task)
    db.flush()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.task_created",
        resource_type="coach_task",
        resource_id=task.id,
        details={"state": task.state},
    )
    db.commit()
    return _task_response(task, _client_name(client))


def update_task_state(
    db: Session,
    coach: User,
    task_id: int,
    state: str,
) -> CoachTaskResponse:
    task = (
        db.query(CoachTask)
        .filter(CoachTask.id == task_id, CoachTask.coach_user_id == coach.id)
        .with_for_update()
        .first()
    )
    if task is None:
        raise CoachCrmError("Задача не найдена", 404)
    _managed_client(db, coach, task.client_user_id)
    previous = task.state
    task.state = state
    now = now_msk_naive()
    task.completed_at = now if state == "completed" else None
    task.reopened_at = now if state == "open" and previous == "completed" else task.reopened_at
    task.updated_at = now
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=task.client_user_id,
        action="coach.task_state_changed",
        resource_type="coach_task",
        resource_id=task.id,
        details={"from": previous, "to": state},
    )
    db.commit()
    return _task_response(task, _client_name(_managed_client(db, coach, task.client_user_id)))


def operations_today(db: Session, coach: User) -> dict[str, object]:
    timezone_name = get_user_timezone_name(coach)
    current_date = today_in_timezone(timezone_name)
    sessions = list_sessions(db, coach, date_from=current_date, date_to=current_date)
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    day_end = local_naive_to_utc_naive_strict(
        datetime.combine(current_date + timedelta(days=1), time.min), timezone_name
    )
    task_rows = (
        db.query(CoachTask)
        .filter(
            CoachTask.coach_user_id == coach.id,
            CoachTask.state == "open",
            CoachTask.due_at_utc < day_end,
        )
        .order_by(CoachTask.due_at_utc.asc(), CoachTask.id.asc())
        .all()
    )
    names = _client_names(db, {row.client_user_id for row in task_rows})
    task_response = [
        _task_response(row, names.get(row.client_user_id, "Клиент")) for row in task_rows
    ]
    overdue = [
        item for item, row in zip(task_response, task_rows, strict=True) if row.due_at_utc < now_utc
    ]
    due = [
        item
        for item, row in zip(task_response, task_rows, strict=True)
        if row.due_at_utc >= now_utc
    ]
    package_rows = (
        db.query(CoachPackage)
        .filter(CoachPackage.coach_user_id == coach.id, CoachPackage.state == "active")
        .all()
    )
    package_names = _client_names(db, {row.client_user_id for row in package_rows})
    totals = _ledger_totals(db, {row.id for row in package_rows})
    low_packages = [
        _package_response(
            row, package_names.get(row.client_user_id, "Клиент"), totals.get(row.id, {})
        )
        for row in package_rows
        if not row.counts_sessions
        or row.included_sessions is None
        or row.included_sessions
        - totals.get(row.id, {}).get("charge", 0)
        + totals.get(row.id, {}).get("reversal", 0)
        <= 2
    ]
    payment_rows = (
        db.query(CoachPayment)
        .filter(
            CoachPayment.coach_user_id == coach.id,
            CoachPayment.status.in_(("expected", "partial")),
        )
        .order_by(CoachPayment.payment_date.asc(), CoachPayment.id.asc())
        .limit(20)
        .all()
    )
    payment_names = _client_names(db, {row.client_user_id for row in payment_rows})
    return {
        "date": current_date,
        "timezone": timezone_name,
        "sessions": sessions,
        "overdue_tasks": overdue,
        "due_tasks": due,
        "low_packages": [item for item in low_packages if item.counts_sessions],
        "payment_facts": [
            _payment_response(row, payment_names.get(row.client_user_id, "Клиент"))
            for row in payment_rows
        ],
    }


def client_operations(db: Session, coach: User, client_id: int) -> dict[str, object]:
    _managed_client(db, coach, client_id)
    current_date = today_in_timezone(get_user_timezone_name(coach))
    sessions = [
        item
        for item in list_sessions(
            db,
            coach,
            date_from=current_date - timedelta(days=14),
            date_to=current_date + timedelta(days=28),
        )
        if item.client_id == client_id
    ]
    return {
        "sessions": sessions,
        "packages": list_packages(db, coach, client_id),
        "payments": list_payments(db, coach, client_id),
        "tasks": list_tasks(db, coach, client_id=client_id),
    }


def update_client_operational_status(
    db: Session,
    coach: User,
    client_id: int,
    operational_status: str,
) -> None:
    client = _managed_client(db, coach, client_id)
    link = (
        db.query(CoachClient)
        .filter(
            CoachClient.coach_user_id == coach.id,
            CoachClient.client_user_id == client.id,
            CoachClient.status == "active",
        )
        .with_for_update()
        .one()
    )
    previous = link.operational_status
    link.operational_status = operational_status
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.client_operational_status_changed",
        resource_type="coach_client",
        resource_id=link.id,
        details={"from": previous, "to": operational_status},
    )
    db.commit()
