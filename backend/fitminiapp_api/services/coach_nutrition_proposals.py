from __future__ import annotations

import hashlib

from sqlalchemy import func
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    now_for_user_naive,
    today_for_user,
    user_local_naive_to_utc_naive,
)
from fitminiapp_api.models.coach_nutrition_proposal import CoachNutritionProposal
from fitminiapp_api.models.notification import Notification
from fitminiapp_api.models.nutrition import NutritionTarget, NutritionTargetDateOverride
from fitminiapp_api.models.program import UserProgram
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.coach_nutrition_proposal import (
    CoachNutritionProposalCreate,
    CoachNutritionProposalDecision,
)
from fitminiapp_api.schemas.nutrition import NutritionDateOverrideSave
from fitminiapp_api.schemas.nutrition_plan import NutritionPlanDayResponse, NutritionPlanItemUpdate
from fitminiapp_api.services.nutrition import (
    _validate_manual_target_energy,
    get_nutrition_target_for_date,
    save_nutrition_date_override,
)
from fitminiapp_api.services.nutrition_plan import get_plan_day, update_plan_item


class CoachNutritionProposalError(ValueError):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


def _relationship(
    db: Session, coach_id: int, client_id: int, *, relationship_id: int | None = None
) -> CoachClient:
    coach = (
        db.query(User.id)
        .filter(User.id == coach_id, User.is_active.is_(True), User.is_coach.is_(True))
        .first()
    )
    if coach is None:
        raise CoachNutritionProposalError("Предложение недоступно", 404)
    query = db.query(CoachClient).filter(
        CoachClient.coach_user_id == coach_id,
        CoachClient.client_user_id == client_id,
        CoachClient.status == "active",
        CoachClient.nutrition_access.is_not(False),
    )
    if relationship_id is not None:
        query = query.filter(CoachClient.id == relationship_id)
    relation = query.with_for_update().first()
    if relation is None:
        raise CoachNutritionProposalError("Предложение недоступно", 404)
    return relation


def _lock_client(db: Session, client_id: int) -> User:
    client = (
        db.query(User)
        .filter(User.id == client_id, User.is_active.is_(True))
        .with_for_update()
        .first()
    )
    if client is None:
        raise CoachNutritionProposalError("Предложение недоступно", 404)
    return client


def _fingerprint(payload: CoachNutritionProposalCreate) -> str:
    return hashlib.sha256(payload.model_dump_json().encode()).hexdigest()


def _program_revision(db: Session, client_id: int) -> dict[str, int] | None:
    row = (
        db.query(UserProgram.id, UserProgram.current_revision_number)
        .filter(UserProgram.user_id == client_id, UserProgram.is_active.is_(True))
        .first()
    )
    return {"id": row.id, "revision": row.current_revision_number} if row else None


def _current(
    db: Session, client: User, payload: CoachNutritionProposalCreate
) -> tuple[NutritionTarget | None, NutritionPlanDayResponse]:
    if payload.target_date <= today_for_user(client):
        raise CoachNutritionProposalError("Выберите будущую дату")
    target = get_nutrition_target_for_date(db, client.id, payload.target_date)
    if (target.id if target else None) != payload.expected_target_id:
        raise CoachNutritionProposalError("Цель изменилась; обновите данные")
    day = get_plan_day(db, client, payload.target_date)
    if day.revision != payload.expected_plan_revision:
        raise CoachNutritionProposalError("План изменился; обновите данные")
    return target, day


def create_proposal(
    db: Session, coach: User, client_id: int, payload: CoachNutritionProposalCreate, key: str
) -> CoachNutritionProposal:
    key = key.strip()
    if not 8 <= len(key) <= 128:
        raise CoachNutritionProposalError("Некорректный ключ повтора", 422)
    client = _lock_client(db, client_id)
    relation = _relationship(db, coach.id, client.id)
    fingerprint = _fingerprint(payload)
    existing = (
        db.query(CoachNutritionProposal).filter_by(coach_user_id=coach.id, create_key=key).first()
    )
    if existing is not None:
        if existing.request_hash != fingerprint or existing.relationship_id != relation.id:
            raise CoachNutritionProposalError("Ключ повтора уже использован")
        return existing
    _validate_manual_target_energy(payload.target())
    target, day = _current(db, client, payload)
    item = next(
        (item for slot in day.slots for item in slot.items if item.id == payload.item_id), None
    )
    if payload.item_id is not None and (
        item is None or item.status != "planned" or not item.available
    ):
        raise CoachNutritionProposalError("Приём пищи недоступен или изменился")
    version = (
        db.query(func.max(CoachNutritionProposal.version))
        .filter_by(relationship_id=relation.id)
        .scalar()
        or 0
    ) + 1
    before = {
        "target": (
            {name: getattr(target, name) for name in ("calories", "protein_g", "fat_g", "carbs_g")}
            if target
            else None
        ),
        "item": item.model_dump(mode="json") if item else None,
        "program": _program_revision(db, client.id),
    }
    proposal = CoachNutritionProposal(
        relationship_id=relation.id,
        coach_user_id=coach.id,
        client_user_id=client.id,
        version=version,
        target_date=payload.target_date,
        target_id=payload.expected_target_id,
        plan_revision=payload.expected_plan_revision,
        request=payload.model_dump(mode="json"),
        before=before,
        create_key=key,
        request_hash=fingerprint,
        status="pending",
    )
    db.add(proposal)
    db.flush()
    now = now_for_user_naive(client)
    db.add(
        Notification(
            user_id=client.id,
            channel="in_app",
            category="coach_nutrition_proposal",
            event_kind="transactional",
            title="Предложение по питанию",
            body="Тренер предложил изменить план. Откройте питание, чтобы проверить изменения.",
            scheduled_for=now,
            scheduled_for_utc=user_local_naive_to_utc_naive(now, client),
            status="sent",
            sent_at=now,
            attempt_count=1,
            dedupe_key=f"coach-nutrition:{proposal.id}",
            action_url="/app?section=nutrition",
        )
    )
    db.commit()
    db.refresh(proposal)
    return proposal


def list_proposals(
    db: Session, actor: User, *, client_id: int | None = None
) -> list[CoachNutritionProposal]:
    if client_id is None:
        return (
            db.query(CoachNutritionProposal)
            .filter_by(client_user_id=actor.id)
            .order_by(CoachNutritionProposal.id.desc())
            .limit(50)
            .all()
        )
    _relationship(db, actor.id, client_id)
    return (
        db.query(CoachNutritionProposal)
        .filter_by(coach_user_id=actor.id, client_user_id=client_id)
        .join(CoachClient, CoachClient.id == CoachNutritionProposal.relationship_id)
        .filter(CoachClient.status == "active", CoachClient.nutrition_access.is_not(False))
        .order_by(CoachNutritionProposal.id.desc())
        .limit(50)
        .all()
    )


def decide_proposal(
    db: Session, actor: User, proposal_id: int, payload: CoachNutritionProposalDecision, key: str
) -> CoachNutritionProposal:
    key = key.strip()
    if not 8 <= len(key) <= 128:
        raise CoachNutritionProposalError("Некорректный ключ повтора", 422)
    client = _lock_client(db, actor.id)
    proposal = (
        db.query(CoachNutritionProposal).filter_by(id=proposal_id, client_user_id=actor.id).first()
    )
    if proposal is None:
        raise CoachNutritionProposalError("Предложение недоступно", 404)
    if proposal.coach_user_id is None or proposal.relationship_id is None:
        raise CoachNutritionProposalError("Предложение недоступно", 404)
    _relationship(db, proposal.coach_user_id, client.id, relationship_id=proposal.relationship_id)
    proposal = (
        db.query(CoachNutritionProposal)
        .filter_by(id=proposal_id)
        .populate_existing()
        .with_for_update()
        .one()
    )
    if proposal.version != payload.version:
        raise CoachNutritionProposalError("Предложение изменилось; обновите страницу")
    final_status = "accepted" if payload.decision == "accept" else "rejected"
    if proposal.status != "pending":
        if proposal.status == final_status and proposal.decision_key == key:
            return proposal
        raise CoachNutritionProposalError("Решение уже принято")
    request = CoachNutritionProposalCreate.model_validate(proposal.request)
    if payload.decision == "accept":
        if _program_revision(db, client.id) != proposal.before.get("program"):
            raise CoachNutritionProposalError("Программа изменилась; запросите новое предложение")
        _current(db, client, request)
        target_payload = NutritionDateOverrideSave(
            effective_from=request.target_date,
            calories=request.calories,
            protein_g=request.protein_g,
            fat_g=request.fat_g,
            carbs_g=request.carbs_g,
            expected_target_id=request.expected_target_id,
            confirm_energy_mismatch=request.confirm_energy_mismatch,
        )
        result = save_nutrition_date_override(
            db, client, target_payload, f"coach-proposal-{proposal.id}", commit=False
        )
        target = db.query(NutritionTarget).filter_by(id=result.target.id, user_id=client.id).one()
        target.source = "trainer"
        target.assigned_by_user_id = proposal.coach_user_id
        override = (
            db.query(NutritionTargetDateOverride)
            .filter_by(user_id=client.id, target_id=target.id)
            .one()
        )
        override.created_by_user_id = proposal.coach_user_id
        if request.item_id is not None:
            update_plan_item(
                db,
                client,
                request.item_id,
                NutritionPlanItemUpdate(
                    amount=request.item_amount, expected_revision=request.expected_plan_revision
                ),
                commit=False,
            )
    proposal.status = final_status
    proposal.decision_key = key
    proposal.decided_at = now_for_user_naive(client)
    db.commit()
    db.refresh(proposal)
    return proposal
