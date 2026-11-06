import hashlib
from datetime import date, timedelta

from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.timezone import now_for_user_naive, today_for_user
from fitminiapp_api.models.nutrition import (
    NutritionScheduleBinding,
    NutritionTarget,
    NutritionTargetScheduleRule,
)
from fitminiapp_api.models.program import ProgramRevision, UserProgram
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition import (
    NutritionScheduleBindingConfirm,
    NutritionScheduleBindingResponse,
    NutritionScheduleBindingStatus,
    NutritionSchedulePreviewChange,
    NutritionSchedulePreviewRequest,
    NutritionSchedulePreviewResponse,
    NutritionSchedulePreviewTarget,
    NutritionScheduleRuleResponse,
    NutritionScheduleRuleSave,
)
from fitminiapp_api.services.nutrition import (
    NutritionConflictError,
    NutritionError,
    _normalized_note,
    _resolve_target_user,
    _validate_manual_target_energy,
    build_nutrition_target_response_for_user,
    build_nutrition_target_response_from_users,
    load_nutrition_targets_and_date_overrides,
    lock_nutrition_authorization,
    nutrition_request_identity,
)
from fitminiapp_api.services.nutrition_program import (
    program_cycle_identity,
    program_nutrition_day,
    program_week_types,
)
from fitminiapp_api.services.nutrition_schedule import load_scheduled_nutrition_targets


def _program_and_revisions(
    db: Session, user: User, program_id: int, revision_number: int, *, lock: bool
) -> tuple[UserProgram, list[ProgramRevision]]:
    query = db.query(UserProgram).filter_by(id=program_id, user_id=user.id)
    program = (query.with_for_update() if lock else query).first()
    if program is None:
        raise NutritionError("Program not found")
    if not program.is_active or program.status not in {"active", "scheduled"}:
        raise NutritionConflictError("Программа недоступна для назначения целей")
    revisions = (
        db.query(ProgramRevision)
        .filter(
            ProgramRevision.user_program_id == program.id,
            ProgramRevision.revision_number <= revision_number,
        )
        .order_by(ProgramRevision.revision_number)
        .all()
    )
    if not revisions or revisions[-1].revision_number != revision_number:
        raise NutritionError("Program revision not found")
    return program, revisions


def _binding_at(db: Session, user_id: int, day: date) -> NutritionScheduleBinding | None:
    return (
        db.query(NutritionScheduleBinding)
        .filter(
            NutritionScheduleBinding.user_id == user_id,
            NutritionScheduleBinding.effective_from <= day,
        )
        .order_by(
            NutritionScheduleBinding.effective_from.desc(), NutritionScheduleBinding.id.desc()
        )
        .first()
    )


def _rule_response(
    db: Session,
    rule: NutritionTargetScheduleRule,
    target: NutritionTarget,
    user: User,
    authors: dict[int, User] | None = None,
) -> NutritionScheduleRuleResponse:
    target_response = (
        build_nutrition_target_response_for_user(db, target, user)
        if authors is None
        else build_nutrition_target_response_from_users(
            target, user, authors.get(target.assigned_by_user_id)
        )
    )
    if target_response is None:
        raise NutritionError("Цель питания не найдена")
    return NutritionScheduleRuleResponse(
        id=rule.id,
        scope=rule.scope,
        day_type=rule.day_type,
        week_type=rule.week_type,
        effective_from=rule.effective_from,
        program_id=rule.program_id,
        source_cycle_week=rule.source_cycle_week,
        cycle_boundary=rule.cycle_boundary,
        weekday=rule.weekday,
        target=target_response,
    )


def save_nutrition_schedule_rule(
    db: Session,
    current_user: User,
    payload: NutritionScheduleRuleSave,
    idempotency_key: str,
) -> NutritionScheduleRuleResponse:
    target_user = _resolve_target_user(db, current_user, payload.target_telegram_user_id)
    key, fingerprint = nutrition_request_identity(current_user, payload, idempotency_key)
    db.query(User.id).filter(User.id == target_user.id).with_for_update().one()
    lock_nutrition_authorization(db, current_user, target_user)
    existing = (
        db.query(NutritionTargetScheduleRule)
        .filter_by(user_id=target_user.id, idempotency_key=key)
        .first()
    )
    if existing is not None:
        if existing.request_hash != fingerprint:
            raise NutritionConflictError("Ключ повтора уже использован для другого изменения")
        target = (
            db.query(NutritionTarget).filter_by(id=existing.target_id, user_id=target_user.id).one()
        )
        return _rule_response(db, existing, target, target_user)

    _validate_manual_target_energy(payload)
    if payload.effective_from <= today_for_user(target_user):
        raise NutritionConflictError("Правило можно применить только к будущим датам")
    program, revisions = _program_and_revisions(
        db, target_user, payload.program_id, payload.revision_number, lock=True
    )
    revision = revisions[-1]
    binding = _binding_at(db, target_user.id, payload.effective_from)
    if binding is None:
        if program.current_revision_number != payload.revision_number:
            raise NutritionConflictError("Программа изменилась; сначала проверьте расписание")
    elif binding.program_revision_id != revision.id:
        raise NutritionConflictError("Подтвердите применение новой версии программы")

    if payload.week_type is not None and payload.week_type not in program_week_types(
        db, program, revisions, payload.revision_number
    ):
        raise NutritionConflictError("В программе не указан выбранный тип недели")
    source_week = boundary = weekday = None
    if payload.scope in {"future", "recovery"}:
        if payload.scope == "recovery" and payload.day_type != "recovery":
            raise NutritionConflictError(
                "Для назначения восстановления выберите восстановительный день"
            )
        day_type, week_type = program_nutrition_day(
            db, program, revisions, payload.revision_number, payload.effective_from
        )
        if day_type is None or week_type != payload.week_type:
            raise NutritionConflictError("Не удалось подтвердить тип дня и недели по программе")
        if day_type != payload.day_type and not (
            day_type == "rest" and payload.day_type == "recovery"
        ):
            raise NutritionConflictError("Тип дня не соответствует расписанию программы")
        source_week, boundary = program_cycle_identity(
            db, program, revisions, payload.revision_number, payload.effective_from
        )
        if payload.day_type == "recovery":
            weekday = payload.effective_from.weekday()

    if binding is None:
        db.add(
            NutritionScheduleBinding(
                user_id=target_user.id,
                program_revision_id=revision.id,
                effective_from=payload.effective_from,
                created_by_user_id=current_user.id,
                idempotency_key="first:" + hashlib.sha256(key.encode()).hexdigest(),
                request_hash=fingerprint,
            )
        )
    target = NutritionTarget(
        user_id=target_user.id,
        assigned_by_user_id=current_user.id,
        source="manual" if current_user.id == target_user.id else "trainer",
        target_scope="schedule",
        effective_from=payload.effective_from,
        effective_to=payload.effective_from,
        note=_normalized_note(payload.note),
        calories=payload.calories,
        protein_g=payload.protein_g,
        fat_g=payload.fat_g,
        carbs_g=payload.carbs_g,
        saved_at=now_for_user_naive(target_user),
    )
    db.add(target)
    db.flush()
    rule = NutritionTargetScheduleRule(
        user_id=target_user.id,
        target_id=target.id,
        program_id=program.id if payload.scope in {"future", "recovery"} else None,
        scope=payload.scope,
        day_type=payload.day_type,
        week_type=payload.week_type,
        effective_from=payload.effective_from,
        source_cycle_week=source_week,
        cycle_boundary=boundary,
        weekday=weekday,
        created_by_user_id=current_user.id,
        idempotency_key=key,
        request_hash=fingerprint,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    db.refresh(target)
    return _rule_response(db, rule, target, target_user)


def preview_nutrition_schedule_binding(
    db: Session, current_user: User, payload: NutritionSchedulePreviewRequest
) -> NutritionSchedulePreviewResponse:
    user = _resolve_target_user(db, current_user, payload.target_telegram_user_id)
    if payload.effective_from <= today_for_user(user):
        raise NutritionConflictError("Новую программу можно применить только к будущим датам")
    if (
        payload.date_from < payload.effective_from
        or payload.date_to < payload.date_from
        or (payload.date_to - payload.date_from).days > 92
    ):
        raise NutritionError("Диапазон просмотра должен содержать не более 93 будущих дней")
    program, revisions = _program_and_revisions(
        db, user, payload.program_id, payload.revision_number, lock=False
    )
    if program.current_revision_number != payload.revision_number:
        raise NutritionConflictError("Программа изменилась; обновите просмотр")
    binding = _binding_at(db, user.id, payload.effective_from)
    binding_id = binding.id if binding else None
    if payload.expected_binding_id is not None and payload.expected_binding_id != binding_id:
        raise NutritionConflictError("Назначение изменилось; обновите просмотр")
    history, overrides, scheduled_users = load_nutrition_targets_and_date_overrides(
        db, {user.id}, payload.date_from, payload.date_to
    )
    old = load_scheduled_nutrition_targets(db, scheduled_users, payload.date_from, payload.date_to)
    new = load_scheduled_nutrition_targets(
        db,
        {user.id},
        payload.date_from,
        payload.date_to,
        preview_binding=(user.id, program, revisions[-1], payload.effective_from),
    )
    history.sort(key=lambda row: (row.effective_from, row.id), reverse=True)
    changes = []
    for offset in range((payload.date_to - payload.date_from).days + 1):
        day = payload.date_from + timedelta(days=offset)
        key = (user.id, day)
        baseline = next(
            (
                target
                for target in history
                if target.effective_from <= day
                and (target.effective_to is None or day < target.effective_to)
            ),
            None,
        )
        before = overrides[key] if key in overrides else old.get(key, baseline)
        after = overrides[key] if key in overrides else new.get(key, baseline)
        if (before.id if before else None) == (after.id if after else None):
            continue
        changes.append(
            NutritionSchedulePreviewChange(
                date=day,
                before=NutritionSchedulePreviewTarget.model_validate(before, from_attributes=True)
                if before
                else None,
                after=NutritionSchedulePreviewTarget.model_validate(after, from_attributes=True)
                if after
                else None,
            )
        )
    return NutritionSchedulePreviewResponse(
        expected_binding_id=binding_id,
        program_id=program.id,
        revision_number=payload.revision_number,
        effective_from=payload.effective_from,
        date_from=payload.date_from,
        date_to=payload.date_to,
        changes=changes,
    )


def confirm_nutrition_schedule_binding(
    db: Session,
    current_user: User,
    payload: NutritionScheduleBindingConfirm,
    idempotency_key: str,
) -> NutritionScheduleBindingResponse:
    user = _resolve_target_user(db, current_user, payload.target_telegram_user_id)
    key, fingerprint = nutrition_request_identity(current_user, payload, idempotency_key)
    db.query(User.id).filter(User.id == user.id).with_for_update().one()
    lock_nutrition_authorization(db, current_user, user)
    existing = (
        db.query(NutritionScheduleBinding).filter_by(user_id=user.id, idempotency_key=key).first()
    )
    if existing is not None:
        if existing.request_hash != fingerprint:
            raise NutritionConflictError("Ключ повтора уже использован для другого изменения")
        revision = db.query(ProgramRevision).filter_by(id=existing.program_revision_id).one()
        return NutritionScheduleBindingResponse(
            id=existing.id,
            program_id=revision.user_program_id,
            revision_number=revision.revision_number,
            effective_from=existing.effective_from,
        )
    if payload.effective_from <= today_for_user(user):
        raise NutritionConflictError("Новую программу можно применить только к будущим датам")
    program, revisions = _program_and_revisions(
        db, user, payload.program_id, payload.revision_number, lock=True
    )
    if program.current_revision_number != payload.revision_number:
        raise NutritionConflictError("Программа изменилась; обновите просмотр")
    previous = _binding_at(db, user.id, payload.effective_from)
    if (previous.id if previous else None) != payload.expected_binding_id:
        raise NutritionConflictError("Назначение изменилось; обновите просмотр")
    binding = NutritionScheduleBinding(
        user_id=user.id,
        program_revision_id=revisions[-1].id,
        effective_from=payload.effective_from,
        created_by_user_id=current_user.id,
        idempotency_key=key,
        request_hash=fingerprint,
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return NutritionScheduleBindingResponse(
        id=binding.id,
        program_id=program.id,
        revision_number=payload.revision_number,
        effective_from=binding.effective_from,
    )


def list_nutrition_schedule_rules(
    db: Session, current_user: User, target_telegram_user_id: int | None = None
) -> list[NutritionScheduleRuleResponse]:
    user = _resolve_target_user(db, current_user, target_telegram_user_id)
    rows = (
        db.query(NutritionTargetScheduleRule, NutritionTarget)
        .join(
            NutritionTarget,
            (NutritionTarget.id == NutritionTargetScheduleRule.target_id)
            & (NutritionTarget.user_id == NutritionTargetScheduleRule.user_id),
        )
        .filter(NutritionTargetScheduleRule.user_id == user.id)
        .order_by(NutritionTargetScheduleRule.id.desc())
        .limit(100)
        .all()
    )
    author_ids = {target.assigned_by_user_id for _, target in rows if target.assigned_by_user_id}
    authors = (
        {
            author.id: author
            for author in db.query(User)
            .options(joinedload(User.profile))
            .filter(User.id.in_(author_ids))
        }
        if author_ids
        else {}
    )
    return [_rule_response(db, rule, target, user, authors) for rule, target in rows]


def read_nutrition_schedule_binding(
    db: Session, current_user: User, target_telegram_user_id: int | None, day: date
) -> NutritionScheduleBindingStatus | None:
    user = _resolve_target_user(db, current_user, target_telegram_user_id)
    binding = _binding_at(db, user.id, day)
    if binding is None:
        return None
    row = (
        db.query(ProgramRevision, UserProgram)
        .join(UserProgram, UserProgram.id == ProgramRevision.user_program_id)
        .filter(ProgramRevision.id == binding.program_revision_id, UserProgram.user_id == user.id)
        .first()
    )
    if row is None:
        raise NutritionError("Program revision not found")
    revision, program = row
    active_program = db.query(UserProgram.id).filter_by(user_id=user.id, is_active=True).first()
    return NutritionScheduleBindingStatus(
        id=binding.id,
        program_id=program.id,
        revision_number=revision.revision_number,
        effective_from=binding.effective_from,
        current_revision_number=program.current_revision_number,
        program_changed=(
            active_program is None
            or active_program[0] != program.id
            or revision.revision_number != program.current_revision_number
        ),
    )
