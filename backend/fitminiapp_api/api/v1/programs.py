from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_coach, require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.program import (
    AssignTemplateSelfRequest,
    ClientResponse,
    CoachProgramExerciseAssignmentResponse,
    CoachProgramExerciseCreate,
    ExerciseCatalogCreate,
    ExerciseCatalogItem,
    ExerciseGuide,
    ProgramAssignmentResponse,
    ProgramRecommendationRequest,
    ProgramRecommendationResponse,
    ProgramRevisionResponse,
    ProgramTemplateCreate,
    ProgramTemplateCreateResponse,
    ProgramTemplateResponse,
    TemplateExerciseReplacementRequest,
    TrainingBlockCreate,
    TrainingBlockMutationResponse,
    TrainingBlockResponse,
    TrainingBlockUpdate,
)
from fitminiapp_api.services.exercise_catalog import (
    _effective_exercise_id,
    _source_exercise_slug,
    create_exercise,
    delete_exercise_for_user,
    list_exercises,
    update_exercise_for_user,
)
from fitminiapp_api.services.exercise_catalog_metadata import (
    CANONICAL_EXERCISE_REDIRECTS,
    exercise_catalog_metadata,
)
from fitminiapp_api.services.exercise_domain import (
    alternative_payloads_by_exercise_id,
    exercise_equipment_payload,
    exercise_muscle_payload,
)
from fitminiapp_api.services.exercise_guides import get_exercise_guide
from fitminiapp_api.services.program_common import ProgramError, assignment_error_status
from fitminiapp_api.services.program_recommendation import recommend_program_templates
from fitminiapp_api.services.program_versioning import (
    create_training_block,
    list_program_revisions,
    list_training_blocks,
    update_training_block,
    upsert_future_program_exercise,
)
from fitminiapp_api.services.programs import (
    assign_template_to_self,
    build_template_response,
    build_template_responses,
    create_and_optionally_assign_program,
    delete_assigned_program_for_user,
    delete_template_for_user,
    get_template_for_user,
    list_clients,
    list_hidden_example_templates,
    list_user_templates,
    replace_template_exercise_for_user,
    restore_example_template_for_user,
    update_template_for_user,
)
from fitminiapp_api.services.workout_metrics import exercise_metric_type

router = APIRouter()


def _assigned_program_error(exc: ProgramError) -> HTTPException:
    detail = str(exc)
    if detail in {"Assigned program not found", "Training block not found"}:
        return HTTPException(status_code=404, detail=detail)
    if detail in {
        "Program revision conflict",
        "Assigned program is not editable",
        "Cannot delete a program while a workout is in progress",
        "Training blocks must not overlap",
        "Invalid training block status transition",
        "Complete the previous training block first",
        "Another training block is already active",
        "Completed or archived training blocks are immutable",
        "No future planned workouts for the selected day",
        "Superset position is already occupied",
    }:
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=422, detail=detail)


def _serialize_exercise(
    exercise: Exercise,
    current_user: User,
    *,
    include_guide: bool = False,
    alternatives: list[dict[str, int | str]] | None = None,
) -> dict:
    guide = get_exercise_guide(exercise, alternatives=alternatives)
    muscles = exercise_muscle_payload(exercise)
    equipment = exercise_equipment_payload(exercise)
    source_slug = _source_exercise_slug(exercise)
    redirected_slug = CANONICAL_EXERCISE_REDIRECTS.get(source_slug)
    catalog_metadata = exercise_catalog_metadata(redirected_slug or source_slug)
    canonical_slug = redirected_slug
    if exercise.source_exercise_id is not None:
        canonical_slug = canonical_slug or source_slug
    return {
        "id": _effective_exercise_id(exercise),
        "edit_target_id": exercise.id,
        "slug": exercise.slug,
        "canonical_slug": canonical_slug,
        "title": exercise.title,
        "primary_muscle": exercise.primary_muscle,
        "equipment": exercise.equipment,
        "metric_type": exercise_metric_type(exercise),
        "primary_muscle_ids": [item["identifier"] for item in muscles if item["role"] == "primary"],
        "secondary_muscle_ids": [
            item["identifier"] for item in muscles if item["role"] == "secondary"
        ],
        "equipment_ids": [item["identifier"] for item in equipment],
        "aliases": list(catalog_metadata["aliases"]) if catalog_metadata else [],
        "movement_pattern": catalog_metadata["movement_pattern"] if catalog_metadata else None,
        "machine_variant_tags": (
            list(catalog_metadata["machine_variant_tags"]) if catalog_metadata else []
        ),
        "execution_variant_tags": (
            list(catalog_metadata["execution_variant_tags"]) if catalog_metadata else []
        ),
        "alternatives": alternatives or [],
        "difficulty_level": exercise.difficulty_level,
        "is_custom": exercise.created_by_user_id is not None
        and exercise.source_exercise_id is None,
        "is_personalized": exercise.created_by_user_id == current_user.id,
        "created_by_user_id": exercise.created_by_user_id,
        "source_exercise_id": exercise.source_exercise_id,
        "has_guide": guide is not None,
        "guide": guide if include_guide else None,
    }


@router.get("/exercises", response_model=list[ExerciseCatalogItem])
def get_exercises(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    exercises = list_exercises(db, current_user)
    alternatives = alternative_payloads_by_exercise_id(db, exercises)
    return [
        _serialize_exercise(
            exercise,
            current_user,
            alternatives=alternatives.get(_effective_exercise_id(exercise), []),
        )
        for exercise in exercises
    ]


@router.get("/exercises/{exercise_id}/guide", response_model=ExerciseGuide)
def get_exercise_guide_details(
    exercise_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    exercises = list_exercises(db, current_user)
    exercise = next(
        (row for row in exercises if _effective_exercise_id(row) == exercise_id),
        None,
    )
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    alternatives = alternative_payloads_by_exercise_id(db, exercises)
    guide = get_exercise_guide(
        exercise,
        alternatives=alternatives.get(_effective_exercise_id(exercise), []),
    )
    if guide is None:
        raise HTTPException(status_code=404, detail="Техника упражнения не заполнена")
    return guide


@router.get("/exercises/{exercise_id}", response_model=ExerciseCatalogItem)
def get_exercise_details(
    exercise_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    exercises = list_exercises(db, current_user)
    exercise = next(
        (row for row in exercises if _effective_exercise_id(row) == exercise_id),
        None,
    )
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    alternatives = alternative_payloads_by_exercise_id(db, exercises)
    return _serialize_exercise(
        exercise,
        current_user,
        include_guide=True,
        alternatives=alternatives.get(_effective_exercise_id(exercise), []),
    )


@router.post(
    "/exercises",
    response_model=ExerciseCatalogItem,
    status_code=status.HTTP_201_CREATED,
)
def add_exercise(
    payload: ExerciseCatalogCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        exercise = create_exercise(
            db=db,
            current_user=current_user,
            title=payload.title.strip(),
            primary_muscle=payload.primary_muscle,
            equipment=payload.equipment,
            metric_type=payload.metric_type or "strength",
            difficulty_level=payload.difficulty_level,
            target_telegram_user_id=payload.target_telegram_user_id,
        )
    except ProgramError as exc:
        detail = str(exc)
        if detail == "No permission to manage this user":
            raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=assignment_error_status(detail), detail=detail)

    return _serialize_exercise(exercise, current_user)


@router.patch("/exercises/{exercise_id}", response_model=ExerciseCatalogItem)
def edit_exercise(
    exercise_id: int,
    payload: ExerciseCatalogCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        exercise = update_exercise_for_user(
            db=db,
            current_user=current_user,
            exercise_id=exercise_id,
            title=payload.title.strip(),
            primary_muscle=payload.primary_muscle,
            equipment=payload.equipment,
            metric_type=payload.metric_type,
            difficulty_level=payload.difficulty_level,
            target_telegram_user_id=payload.target_telegram_user_id,
        )
    except ProgramError as exc:
        detail = str(exc)
        if detail == "Exercise not found":
            raise HTTPException(status_code=404, detail=detail)
        if detail in {"No permission to edit exercise", "No permission to manage this user"}:
            raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return _serialize_exercise(exercise, current_user)


@router.delete("/exercises/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_exercise(
    exercise_id: int,
    target_telegram_user_id: int | None = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_exercise_for_user(
            db=db,
            current_user=current_user,
            exercise_id=exercise_id,
            target_telegram_user_id=target_telegram_user_id,
        )
    except ProgramError as exc:
        detail = str(exc)
        if detail == "Exercise not found":
            raise HTTPException(status_code=404, detail=detail)
        if detail in {"No permission to delete exercise", "No permission to manage this user"}:
            raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.post("/templates", response_model=ProgramTemplateCreateResponse)
def create_template(
    payload: ProgramTemplateCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        template, assigned_program, workouts_created, target_user = (
            create_and_optionally_assign_program(
                db=db,
                current_user=current_user,
                payload=payload,
            )
        )
    except ProgramError as exc:
        detail = str(exc)
        if detail == "No permission to manage this user":
            raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return {
        "template": build_template_response(template, db, current_user),
        "assigned_program_id": assigned_program.id if assigned_program else None,
        "workouts_created": workouts_created,
        "target_user": target_user,
    }


@router.get("/templates/mine", response_model=list[ProgramTemplateResponse])
def my_templates(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    items = list_user_templates(db, current_user)
    return build_template_responses(items, db, current_user)


@router.post(
    "/templates/recommendation",
    response_model=ProgramRecommendationResponse,
)
def recommend_template(
    payload: ProgramRecommendationRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    decision = recommend_program_templates(db, current_user, payload)
    ranked = decision.ranked_candidates[:3]
    serialized_templates = build_template_responses(
        [item.candidate.template for item in ranked],
        db,
        current_user,
    )

    def serialize_item(index: int) -> dict:
        item = ranked[index]
        return {
            "template": serialized_templates[index],
            "reason": item.reason,
            "fit_facts": list(item.fit_facts),
            "limitations": list(item.limitations),
        }

    return {
        "status": decision.status,
        "criteria": {
            "goal": decision.criteria.goal,
            "experience": decision.criteria.experience,
            "workouts_per_week": decision.criteria.workouts_per_week,
            "training_location": decision.criteria.training_location,
            "available_equipment_ids": (
                sorted(decision.criteria.available_equipment_ids)
                if decision.criteria.available_equipment_ids is not None
                else None
            ),
            "profile_fields_used": list(decision.criteria.profile_fields_used),
        },
        "missing_fields": list(decision.missing_fields),
        "message": decision.message,
        "recommendation": serialize_item(0) if ranked else None,
        "alternatives": [serialize_item(index) for index in range(1, len(ranked))],
        "requires_explicit_start": True,
    }


@router.get("/templates/hidden", response_model=list[ProgramTemplateResponse])
def hidden_templates(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    items = list_hidden_example_templates(db, current_user)
    return build_template_responses(items, db, current_user)


@router.post("/templates/{template_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_template(
    template_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        restore_example_template_for_user(db, current_user, template_id)
    except ProgramError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/templates/{template_id}", response_model=ProgramTemplateResponse)
def get_template(
    template_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        template = get_template_for_user(db, current_user, template_id)
    except ProgramError as exc:
        detail = str(exc)
        if detail == "Template not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=403, detail=detail)

    return build_template_response(template, db, current_user)


@router.patch("/templates/{template_id}", response_model=ProgramTemplateResponse)
def edit_template(
    template_id: int,
    payload: ProgramTemplateCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        template = update_template_for_user(
            db=db,
            current_user=current_user,
            template_id=template_id,
            payload=payload,
        )
    except ProgramError as exc:
        detail = str(exc)
        if detail == "Template not found":
            raise HTTPException(status_code=404, detail=detail)
        if detail in {"No permission to edit template", "No permission to manage this user"}:
            raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return build_template_response(template, db, current_user)


@router.post(
    "/templates/{template_id}/exercises/{template_exercise_id}/replace",
    response_model=ProgramTemplateResponse,
)
def replace_template_exercise(
    template_id: int,
    template_exercise_id: int,
    payload: TemplateExerciseReplacementRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        template = replace_template_exercise_for_user(
            db,
            current_user,
            template_id,
            template_exercise_id,
            payload.replacement_exercise_id,
            payload.reason,
        )
    except ProgramError as exc:
        detail = str(exc)
        if detail in {"Template not found", "Template exercise not found"}:
            raise HTTPException(status_code=404, detail=detail) from exc
        if detail == "No permission to edit template":
            raise HTTPException(status_code=403, detail=detail) from exc
        raise HTTPException(status_code=422, detail=detail) from exc
    return build_template_response(template, db, current_user)


@router.post(
    "/templates/{template_id}/assign-to-me",
    response_model=ProgramAssignmentResponse,
)
def assign_template_me(
    template_id: int,
    payload: AssignTemplateSelfRequest | None = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        program, created = assign_template_to_self(
            db=db,
            current_user=current_user,
            template_id=template_id,
            start_date=payload.start_date if payload else None,
            duration_weeks=payload.duration_weeks if payload else 1,
            schedule_weekdays=payload.schedule_weekdays if payload else None,
            replace_active=payload.replace_active if payload else False,
        )
    except ProgramError as exc:
        detail = str(exc)
        if detail == "Template not found":
            raise HTTPException(status_code=404, detail=detail)
        error_status = assignment_error_status(detail)
        if error_status != 400:
            raise HTTPException(status_code=error_status, detail=detail) from exc
        raise HTTPException(status_code=403, detail=detail) from exc

    return {
        "user_program_id": program.id,
        "workouts_created": created,
        "status": program.status,
        "start_date": program.start_date,
        "duration_weeks": program.duration_weeks,
    }


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_template_for_user(db, current_user, template_id)
    except ProgramError as exc:
        detail = str(exc)
        if detail == "Template not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=403, detail=detail)


@router.delete("/assigned/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assigned_program(
    program_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_assigned_program_for_user(db, current_user, program_id)
    except ProgramError as exc:
        raise _assigned_program_error(exc) from exc


@router.get(
    "/assigned/{program_id}/revisions",
    response_model=list[ProgramRevisionResponse],
)
def assigned_program_revisions(
    program_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        rows = list_program_revisions(db, current_user, program_id)
    except ProgramError as exc:
        raise _assigned_program_error(exc) from exc
    return [
        {
            "id": row.id,
            "user_program_id": row.user_program_id,
            "revision_number": row.revision_number,
            "changed_by_user_id": row.changed_by_user_id,
            "actor_role": row.actor_role,
            "change_kind": row.change_kind,
            "reason": row.reason,
            "changed_fields": row.changed_fields,
            "snapshot": row.snapshot,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get(
    "/assigned/{program_id}/blocks",
    response_model=list[TrainingBlockResponse],
)
def assigned_program_blocks(
    program_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return list_training_blocks(db, current_user, program_id)
    except ProgramError as exc:
        raise _assigned_program_error(exc) from exc


@router.post(
    "/assigned/{program_id}/blocks",
    response_model=TrainingBlockMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_assigned_program_block(
    program_id: int,
    payload: TrainingBlockCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        block, revision_number = create_training_block(db, current_user, program_id, payload)
    except ProgramError as exc:
        raise _assigned_program_error(exc) from exc
    return {"block": block, "current_revision_number": revision_number}


@router.patch(
    "/assigned/{program_id}/blocks/{block_id}",
    response_model=TrainingBlockMutationResponse,
)
def edit_assigned_program_block(
    program_id: int,
    block_id: int,
    payload: TrainingBlockUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        block, revision_number = update_training_block(
            db, current_user, program_id, block_id, payload
        )
    except ProgramError as exc:
        raise _assigned_program_error(exc) from exc
    return {"block": block, "current_revision_number": revision_number}


@router.post(
    "/assigned/{program_id}/exercises",
    response_model=CoachProgramExerciseAssignmentResponse,
)
def update_assigned_program_exercise(
    program_id: int,
    payload: CoachProgramExerciseCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        workouts_updated, revision_number = upsert_future_program_exercise(
            db, current_user, program_id, payload
        )
    except ProgramError as exc:
        raise _assigned_program_error(exc) from exc
    return {
        "workouts_updated": workouts_updated,
        "current_revision_number": revision_number,
    }


@router.get("/clients", response_model=list[ClientResponse])
def clients(
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    return list_clients(db, current_user)
