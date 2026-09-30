from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import cast

from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.exercise import (
    Exercise,
    ExerciseAlternative,
    ExerciseEquipment,
    ExerciseMuscle,
)
from fitminiapp_api.models.program import (
    ProgramTemplate,
    ProgramTemplateDay,
    ProgramTemplateExercise,
    ProgramTemplateExerciseWeekPrescription,
    UserProgram,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.program import (
    ExerciseMetricType,
    ExerciseMovementPattern,
    ExercisePrescriptionPlan,
    PrescriptionGroupKind,
    ProgramExperience,
    ProgramLifecycleStatus,
    ProgramProvenanceType,
    ProgramRecommendationGoal,
    ProgramSplitType,
    ProgramTemplateCreate,
    ProgramTemplateDayCreate,
    ProgramTemplateExerciseCreate,
)
from fitminiapp_api.schemas.program_generator import (
    ProgramGeneratorActiveProgram,
    ProgramGeneratorAdaptation,
    ProgramGeneratorConfirmRequest,
    ProgramGeneratorDay,
    ProgramGeneratorExercise,
    ProgramGeneratorPreviewResponse,
    ProgramGeneratorProgram,
    ProgramGeneratorRequest,
    ProgramGeneratorSource,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.exercise_catalog import (
    _effective_exercise_id,
    _source_exercise_slug,
    get_visible_exercise_display_map,
)
from fitminiapp_api.services.exercise_catalog_metadata import exercise_catalog_metadata
from fitminiapp_api.services.exercise_domain import (
    BODY_PRIORITY_TAXONOMY,
    EQUIPMENT_NAME_BY_IDENTIFIER,
    canonical_equipment_identifier,
    canonical_muscle_identifier,
)
from fitminiapp_api.services.prescription_semantics import compatible_for_substitution
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.programs import (
    LEGACY_DEMO_TEMPLATE_SLUG,
    assign_template_to_user,
    build_template_response,
    create_template,
)
from fitminiapp_api.services.workout_metrics import exercise_metric_type

SELECTION_POLICY_VERSION = "program_generator_v1"
_TOKEN_SALT = "program-generator-v1"
_TOKEN_MAX_AGE_SECONDS = 60 * 60
_DURATION_TOLERANCE_MINUTES = 10
_DURATION_TOLERANCE_RATIO = 0.20
_ACTIVE_SECONDS_PER_SET = 45
_TRANSITION_SECONDS_PER_EXERCISE = 60
_GOAL_ORDER = {
    "fat_loss": ("fat_loss", "recomposition", "maintenance"),
    "recomposition": ("recomposition", "muscle_gain", "maintenance"),
    "maintenance": ("maintenance", "recomposition", "muscle_gain"),
    "muscle_gain": ("muscle_gain", "recomposition"),
    "strength": ("strength",),
}
_LEVEL_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}
_SPLIT_LABELS = {
    "full_body": "всё тело за тренировку",
    "upper_lower": "верх/низ",
    "push_pull_legs": "толкай/тяни/ноги",
    "body_part": "по группам мышц",
    "hybrid": "комбинированный сплит",
}
_MUSCLE_NAMES = dict(BODY_PRIORITY_TAXONOMY)
_ALLOWED_PROVENANCE = {"YFC_GENERIC", "SOURCE_ADAPTATION"}


class ProgramGeneratorError(ProgramError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class _CandidateIncompatible(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _Slot:
    day_number: int
    source_item: ProgramTemplateExercise
    source_exercise: Exercise
    selected_exercise: Exercise
    substitution: bool = False
    removed: bool = False

    @property
    def source_id(self) -> int:
        return _effective_exercise_id(self.source_exercise)

    @property
    def selected_id(self) -> int:
        return _effective_exercise_id(self.selected_exercise)


@dataclass
class _AdaptedCandidate:
    template: ProgramTemplate
    slots_by_day: dict[int, list[_Slot]]
    selected_by_source_id: dict[int, Exercise]
    substitutions: list[dict[str, object]]
    removals: list[dict[str, object]]
    schedule_adapted: bool
    day_estimates: dict[int, int]
    selected_ids: frozenset[int]
    primary_muscle_ids: frozenset[str]
    rank: tuple[object, ...] = ()
    score: int = 0
    fit_reasons: tuple[str, ...] = ()
    tradeoffs: tuple[str, ...] = ()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_TOKEN_SALT)


def _normalized_inputs(payload: ProgramGeneratorRequest) -> dict[str, object]:
    result = payload.model_dump(mode="json")
    for name in (
        "available_equipment_ids",
        "priority_muscle_ids",
        "preferred_exercise_ids",
        "excluded_exercise_ids",
    ):
        result[name] = sorted(result[name])
    return result


def _active_state(db: Session, current_user: User) -> dict[str, object] | None:
    program = (
        db.query(UserProgram)
        .filter(UserProgram.user_id == current_user.id, UserProgram.is_active.is_(True))
        .order_by(UserProgram.id.desc())
        .first()
    )
    if program is None:
        return None
    return {
        "program_id": program.id,
        "revision_number": program.current_revision_number,
        "status": program.status,
        "assigned_by_user_id": program.assigned_by_user_id,
    }


def _active_response(
    state: dict[str, object] | None, current_user: User
) -> ProgramGeneratorActiveProgram | None:
    if state is None:
        return None
    program_id = state.get("program_id")
    revision_number = state.get("revision_number")
    status = state.get("status")
    if (
        not isinstance(program_id, int)
        or not isinstance(revision_number, int)
        or not isinstance(status, str)
    ):
        return None
    assigned_by = state.get("assigned_by_user_id")
    return ProgramGeneratorActiveProgram(
        program_id=program_id,
        revision_number=revision_number,
        status=cast(ProgramLifecycleStatus, status),
        assigned_by_user_id=int(assigned_by) if isinstance(assigned_by, int) else None,
        trainer_owned=isinstance(assigned_by, int) and assigned_by != current_user.id,
    )


def _same_active_state(left: object, right: object) -> bool:
    return _canonical_json(left) == _canonical_json(right)


def _exercise_equipment(exercise: Exercise) -> tuple[set[str], bool]:
    identifiers = {link.equipment.identifier for link in exercise.equipment_links}
    if identifiers:
        return identifiers - {"bodyweight"}, True
    if exercise.equipment is None:
        return set(), True
    identifier = canonical_equipment_identifier(exercise.equipment)
    if identifier is None:
        return set(), False
    return ({identifier} - {"bodyweight"}, True)


def _exercise_muscles(exercise: Exercise) -> set[str]:
    primary = {link.muscle.identifier for link in exercise.muscle_links if link.role == "primary"}
    if primary:
        return primary
    fallback = canonical_muscle_identifier(exercise.primary_muscle)
    return {fallback} if fallback else set()


def _exercise_movement_pattern(exercise: Exercise) -> ExerciseMovementPattern | None:
    metadata = exercise_catalog_metadata(_source_exercise_slug(exercise))
    if metadata is None:
        return None
    return cast(ExerciseMovementPattern, metadata["movement_pattern"])


def _prescription_sets(item: ProgramTemplateExercise) -> int:
    if isinstance(item.prescription, dict) and isinstance(item.prescription.get("segments"), list):
        return max(1, len(item.prescription["segments"]))
    return max(1, item.prescribed_sets)


def _estimate_item_minutes(item: ProgramTemplateExercise, exercise: Exercise) -> int:
    if exercise_metric_type(exercise) == "cardio":
        duration = item.prescribed_duration_minutes or 0
        return duration + (1 if duration else 0)
    sets = _prescription_sets(item)
    seconds = sets * _ACTIVE_SECONDS_PER_SET
    seconds += max(sets - 1, 0) * item.rest_seconds
    seconds += _TRANSITION_SECONDS_PER_EXERCISE
    return math.ceil(seconds / 60)


def _estimate_day_minutes(slots: list[_Slot]) -> int:
    return sum(
        _estimate_item_minutes(slot.source_item, slot.selected_exercise)
        for slot in slots
        if not slot.removed
    )


def _source_frequency(template: ProgramTemplate) -> int:
    metadata = template.program_metadata or {}
    representation = metadata.get("representation_days")
    if isinstance(representation, int) and representation == len(template.days):
        return representation
    return len(template.days)


def _template_fingerprint_payload(template: ProgramTemplate) -> dict[str, object]:
    days: list[dict[str, object]] = []
    for day in sorted(template.days, key=lambda row: row.day_number):
        exercises: list[dict[str, object]] = []
        for item in sorted(day.exercises, key=lambda row: (row.sort_order, row.id)):
            exercises.append(
                {
                    "id": _effective_exercise_id(item.exercise),
                    "sets": item.prescribed_sets,
                    "reps": item.prescribed_reps,
                    "duration": item.prescribed_duration_minutes,
                    "rest": item.rest_seconds,
                    "notes": item.notes,
                    "superset_group": item.superset_group,
                    "superset_order": item.superset_order,
                    "group_id": item.group_id,
                    "group_kind": item.group_kind,
                    "group_order": item.group_order,
                    "prescription": item.prescription,
                    "weekly": [
                        {
                            "id": _effective_exercise_id(row.exercise),
                            "week": row.week_number,
                            "sets": row.prescribed_sets,
                            "reps": row.prescribed_reps,
                            "duration": row.prescribed_duration_minutes,
                            "rest": row.rest_seconds,
                            "prescription": row.prescription,
                        }
                        for row in sorted(
                            item.weekly_prescriptions,
                            key=lambda row: (row.week_number, row.id),
                        )
                    ],
                }
            )
        days.append({"number": day.day_number, "title": day.title, "exercises": exercises})
    return {
        "id": template.id,
        "slug": template.slug,
        "goal": template.goal,
        "level": template.level,
        "split_type": template.split_type,
        "default_duration_weeks": template.effective_duration_weeks,
        "provenance_type": template.provenance_type,
        "provenance": template.provenance,
        "program_metadata": template.program_metadata,
        "days": days,
    }


def _load_catalog(
    db: Session,
    current_user: User,
) -> tuple[list[ProgramTemplate], dict[int, Exercise], dict[int, set[int]], str, set[int]]:
    # The explicit query below avoids relying on a database's physical row order.
    from fitminiapp_api.models.program import HiddenProgramTemplate

    hidden_ids = {
        template_id
        for (template_id,) in db.query(HiddenProgramTemplate.template_id)
        .filter(HiddenProgramTemplate.user_id == current_user.id)
        .order_by(HiddenProgramTemplate.template_id.asc())
        .all()
    }
    base = selectinload(ProgramTemplate.days).selectinload(ProgramTemplateDay.exercises)
    base_exercise = base.selectinload(ProgramTemplateExercise.exercise)
    weekly = base.selectinload(ProgramTemplateExercise.weekly_prescriptions)
    weekly_exercise = weekly.selectinload(ProgramTemplateExerciseWeekPrescription.exercise)
    options = [
        base_exercise.selectinload(Exercise.equipment_links).selectinload(
            ExerciseEquipment.equipment
        ),
        base_exercise.selectinload(Exercise.muscle_links).selectinload(ExerciseMuscle.muscle),
        weekly_exercise.selectinload(Exercise.equipment_links).selectinload(
            ExerciseEquipment.equipment
        ),
        weekly_exercise.selectinload(Exercise.muscle_links).selectinload(ExerciseMuscle.muscle),
    ]
    templates = (
        db.query(ProgramTemplate)
        .options(*options)
        .filter(
            ProgramTemplate.is_public.is_(True),
            ProgramTemplate.owner_user_id.is_(None),
            ProgramTemplate.created_by_user_id.is_(None),
            ProgramTemplate.provenance_type.in_(_ALLOWED_PROVENANCE),
            ProgramTemplate.slug != LEGACY_DEMO_TEMPLATE_SLUG,
        )
        .order_by(ProgramTemplate.slug.asc(), ProgramTemplate.id.asc())
        .all()
    )
    visible = get_visible_exercise_display_map(db, current_user)
    pairs = db.query(ExerciseAlternative).order_by(
        ExerciseAlternative.exercise_id.asc(),
        ExerciseAlternative.alternative_exercise_id.asc(),
    )
    alternatives: dict[int, set[int]] = {}
    alternative_rows = pairs.all()
    for pair in alternative_rows:
        alternatives.setdefault(pair.exercise_id, set()).add(pair.alternative_exercise_id)
        alternatives.setdefault(pair.alternative_exercise_id, set()).add(pair.exercise_id)
    catalog_revision = _sha256(
        {
            "templates": [_template_fingerprint_payload(template) for template in templates],
            "exercises": [
                {
                    "id": exercise_id,
                    "slug": _source_exercise_slug(exercise),
                    "title": exercise.title,
                    "metric_type": exercise_metric_type(exercise),
                    "equipment": sorted(_exercise_equipment(exercise)[0]),
                    "equipment_complete": _exercise_equipment(exercise)[1],
                    "muscles": sorted(_exercise_muscles(exercise)),
                    "difficulty_level": exercise.difficulty_level,
                }
                for exercise_id, exercise in sorted(visible.items())
                if exercise.created_by_user_id is None or exercise.source_exercise_id is not None
            ],
            "alternatives": [
                (pair.exercise_id, pair.alternative_exercise_id) for pair in alternative_rows
            ],
        }
    )
    return templates, visible, alternatives, catalog_revision, hidden_ids


def _validate_request_domain(
    db: Session,
    current_user: User,
    payload: ProgramGeneratorRequest,
    visible: dict[int, Exercise],
) -> tuple[set[str], set[int], set[int]]:
    allowed_muscles = set(_MUSCLE_NAMES)
    invalid_muscles = sorted(set(payload.priority_muscle_ids) - allowed_muscles)
    if invalid_muscles:
        raise ProgramGeneratorError(
            "unsupported_priority_muscle",
            "Выбранная мышечная группа отсутствует в каноническом справочнике.",
            422,
        )
    preferred: set[int] = set()
    excluded: set[int] = set()
    for target, destination in (
        (payload.preferred_exercise_ids, preferred),
        (payload.excluded_exercise_ids, excluded),
    ):
        for exercise_id in target:
            exercise = visible.get(exercise_id)
            if exercise is None or (
                exercise.created_by_user_id is not None and exercise.source_exercise_id is None
            ):
                raise ProgramGeneratorError(
                    "exercise_not_canonical",
                    "Подбор принимает только упражнения из канонического каталога.",
                    422,
                )
            destination.add(_effective_exercise_id(exercise))
    return set(payload.available_equipment_ids), preferred, excluded


def _alternative_score(target: Exercise, candidate: Exercise, curated: bool) -> int:
    score = 100 if curated else 0
    target_metadata = exercise_catalog_metadata(_source_exercise_slug(target))
    candidate_metadata = exercise_catalog_metadata(_source_exercise_slug(candidate))
    if target_metadata and candidate_metadata:
        if target_metadata["movement_pattern"] == candidate_metadata["movement_pattern"]:
            score += 50
        if set(target_metadata["machine_variant_tags"]) & set(
            candidate_metadata["machine_variant_tags"]
        ):
            score += 5
        if set(target_metadata["execution_variant_tags"]) & set(
            candidate_metadata["execution_variant_tags"]
        ):
            score += 5
    if _exercise_muscles(target) & _exercise_muscles(candidate):
        score += 30
    return score


def _choose_exercise(
    source: Exercise,
    *,
    visible: dict[int, Exercise],
    alternatives: dict[int, set[int]],
    available_equipment: set[str],
    excluded_ids: set[int],
) -> tuple[Exercise, bool]:
    source_id = _effective_exercise_id(source)
    current = visible.get(source_id)
    if current is None:
        raise _CandidateIncompatible("exercise_not_canonical")
    equipment, complete = _exercise_equipment(current)
    if complete and source_id not in excluded_ids and equipment.issubset(available_equipment):
        return current, False

    candidates: list[tuple[int, Exercise]] = []
    for alternative_id in sorted(alternatives.get(source_id, set())):
        candidate = visible.get(alternative_id)
        if candidate is None:
            continue
        if candidate.created_by_user_id is not None and candidate.source_exercise_id is None:
            continue
        candidate_id = _effective_exercise_id(candidate)
        candidate_equipment, candidate_complete = _exercise_equipment(candidate)
        if (
            candidate_id == source_id
            or candidate_id in excluded_ids
            or not candidate_complete
            or not candidate_equipment.issubset(available_equipment)
            or exercise_metric_type(candidate) != exercise_metric_type(current)
        ):
            continue
        compatible, _reason_keys = compatible_for_substitution(
            None,
            None,
            source_metric=exercise_metric_type(current),
            target_metric=exercise_metric_type(candidate),
        )
        if not compatible:
            continue
        candidates.append((-_alternative_score(current, candidate, True), candidate))
    if not candidates:
        if source_id in excluded_ids:
            raise _CandidateIncompatible("excluded_exercise_no_substitution")
        raise _CandidateIncompatible("equipment_no_canonical_substitution")
    candidates.sort(
        key=lambda item: (item[0], item[1].title.casefold(), _effective_exercise_id(item[1]))
    )
    return candidates[0][1], True


def _duration_envelope(preferred_minutes: int) -> int:
    return preferred_minutes + max(
        _DURATION_TOLERANCE_MINUTES,
        round(preferred_minutes * _DURATION_TOLERANCE_RATIO),
    )


def _adapt_candidate(
    template: ProgramTemplate,
    *,
    payload: ProgramGeneratorRequest,
    visible: dict[int, Exercise],
    alternatives: dict[int, set[int]],
    available_equipment: set[str],
    excluded_ids: set[int],
) -> _AdaptedCandidate:
    selected_by_source_id: dict[int, Exercise] = {}
    substitutions: list[dict[str, object]] = []
    slots_by_day: dict[int, list[_Slot]] = {}
    priority_ids = set(payload.priority_muscle_ids)
    for day in sorted(template.days, key=lambda row: row.day_number):
        slots: list[_Slot] = []
        for item in sorted(day.exercises, key=lambda row: (row.sort_order, row.id)):
            source = item.exercise
            source_id = _effective_exercise_id(source)
            if source_id not in selected_by_source_id:
                selected, substituted = _choose_exercise(
                    source,
                    visible=visible,
                    alternatives=alternatives,
                    available_equipment=available_equipment,
                    excluded_ids=excluded_ids,
                )
                selected_by_source_id[source_id] = selected
                if substituted:
                    substitutions.append(
                        {
                            "code": "equipment_substitution",
                            "message": (
                                f"«{source.title}» заменено на «{selected.title}» из канонического каталога."
                            ),
                            "day_number": day.day_number,
                            "source_exercise_id": source_id,
                            "replacement_exercise_id": _effective_exercise_id(selected),
                        }
                    )
            selected = selected_by_source_id[source_id]
            slots.append(
                _Slot(
                    day_number=day.day_number,
                    source_item=item,
                    source_exercise=source,
                    selected_exercise=selected,
                    substitution=selected is not source,
                )
            )
        slots_by_day[day.day_number] = slots

    removals: list[dict[str, object]] = []
    envelope = _duration_envelope(payload.preferred_session_duration_minutes)
    for day_number, slots in slots_by_day.items():
        while _estimate_day_minutes(slots) > envelope:
            groups: dict[tuple[str, int], list[_Slot]] = {}
            for slot in slots:
                if slot.removed:
                    continue
                key = (
                    (
                        "group",
                        slot.source_item.group_id,
                    )
                    if slot.source_item.group_id is not None
                    else ("item", slot.source_item.id)
                )
                groups.setdefault(key, []).append(slot)
            removable: list[tuple[int, tuple[str, int], list[_Slot]]] = []
            for key, group in groups.items():
                if any(slot.source_item.sort_order <= 2 for slot in group):
                    continue
                if any(_exercise_muscles(slot.selected_exercise) & priority_ids for slot in group):
                    continue
                removable.append((max(slot.source_item.sort_order for slot in group), key, group))
            if not removable:
                raise _CandidateIncompatible("duration_incompatible")
            _sort_order, _key, group = max(removable, key=lambda item: (item[0], item[1]))
            for slot in group:
                slots[slots.index(slot)] = _Slot(
                    day_number=slot.day_number,
                    source_item=slot.source_item,
                    source_exercise=slot.source_exercise,
                    selected_exercise=slot.selected_exercise,
                    substitution=slot.substitution,
                    removed=True,
                )
                removals.append(
                    {
                        "code": "duration_accessory_reduction",
                        "message": f"Необязательная аксессуарная работа убрана из дня {day_number}, чтобы уложиться в допустимую длительность.",
                        "day_number": day_number,
                        "source_exercise_id": slot.source_id,
                        "replacement_exercise_id": None,
                    }
                )

    day_estimates = {day: _estimate_day_minutes(slots) for day, slots in slots_by_day.items()}
    selected_ids = frozenset(
        slot.selected_id for slots in slots_by_day.values() for slot in slots if not slot.removed
    )
    muscles = frozenset(
        muscle
        for slots in slots_by_day.values()
        for slot in slots
        if not slot.removed
        for muscle in _exercise_muscles(slot.selected_exercise)
    )
    metadata_days = (template.program_metadata or {}).get("days_per_week")
    schedule_adapted = isinstance(metadata_days, int) and metadata_days != len(template.days)
    return _AdaptedCandidate(
        template=template,
        slots_by_day=slots_by_day,
        selected_by_source_id=selected_by_source_id,
        substitutions=substitutions,
        removals=removals,
        schedule_adapted=schedule_adapted,
        day_estimates=day_estimates,
        selected_ids=selected_ids,
        primary_muscle_ids=muscles,
    )


def _candidate_rank(
    candidate: _AdaptedCandidate,
    payload: ProgramGeneratorRequest,
) -> tuple[int, tuple[object, ...], dict[str, int]]:
    template = candidate.template
    goal_penalty = _GOAL_ORDER[payload.goal].index(template.goal)
    level_penalty = abs(_LEVEL_RANK[payload.experience] - _LEVEL_RANK.get(template.level, 99))
    duration_fit = sum(
        abs(value - payload.preferred_session_duration_minutes)
        for value in candidate.day_estimates.values()
    )
    priority_penalty = int(
        bool(payload.priority_muscle_ids)
        and not (set(payload.priority_muscle_ids) & set(candidate.primary_muscle_ids))
    )
    preference_miss = len(set(payload.preferred_exercise_ids) - set(candidate.selected_ids))
    substitution_count = len(candidate.substitutions)
    adaptation_cost = substitution_count * 3 + len(candidate.removals) * 4
    if candidate.schedule_adapted:
        adaptation_cost += 1
    dimensions = {
        "goal_fit": goal_penalty,
        "experience_fit": level_penalty,
        "schedule_fit": int(candidate.schedule_adapted),
        "equipment_fit": substitution_count,
        "duration_fit": duration_fit,
        "priority_muscle_fit": priority_penalty,
        "exercise_preference_fit": preference_miss,
        "adaptation_cost": adaptation_cost,
    }
    score = (
        goal_penalty * 10_000
        + level_penalty * 1_000
        + substitution_count * 100
        + duration_fit * 10
        + priority_penalty * 5
        + preference_miss * 2
        + adaptation_cost
    )
    rank = (
        adaptation_cost,
        goal_penalty,
        level_penalty,
        0,
        substitution_count,
        duration_fit,
        priority_penalty,
        preference_miss,
        template.slug,
        template.id,
    )
    candidate.rank = rank
    candidate.score = score
    candidate.fit_reasons = _fit_reasons(candidate, payload)
    candidate.tradeoffs = _tradeoffs(candidate, payload)
    return score, rank, dimensions


def _fit_reasons(candidate: _AdaptedCandidate, payload: ProgramGeneratorRequest) -> tuple[str, ...]:
    template = candidate.template
    reasons = [
        f"Цель программы — {_goal_label(template.goal)}; запрос — {_goal_label(payload.goal)}.",
        f"Уровень программы: {_level_label(template.level)}; выбранный опыт: {_level_label(payload.experience)}.",
        f"В структуре {len(template.days)} тренировочных дней — частота запроса соблюдена.",
    ]
    split_label = _SPLIT_LABELS.get(template.split_type or "")
    if split_label:
        reasons.append(f"Формат структуры: {split_label}.")
    location_labels = {
        "gym": "тренажёрном зале",
        "home": "дома",
        "other": "другом месте",
    }
    reasons.append(
        f"Место учтено через выбранное оборудование: {location_labels[payload.training_location]}."
    )
    names = [EQUIPMENT_NAME_BY_IDENTIFIER[item] for item in sorted(payload.available_equipment_ids)]
    reasons.append(
        f"Оборудование проверено по каноническим упражнениям: {', '.join(names)}."
        if names
        else "Проверка выполнена для упражнений без отдельного оборудования."
    )
    if candidate.substitutions:
        reasons.append(
            f"Выполнено канонических замен оборудования: {len(candidate.substitutions)}."
        )
    max_duration = max(candidate.day_estimates.values(), default=0)
    reasons.append(
        f"Расчётная длительность самой длинной тренировки — {max_duration} мин; предпочтение учтено как планировочный ориентир."
    )
    if payload.priority_muscle_ids:
        matched = sorted(set(payload.priority_muscle_ids) & set(candidate.primary_muscle_ids))
        if matched:
            reasons.append(
                "Приоритетные группы представлены в структуре: "
                + ", ".join(_MUSCLE_NAMES.get(item, item) for item in matched)
                + "."
            )
    preferred_matches = set(payload.preferred_exercise_ids) & set(candidate.selected_ids)
    if preferred_matches:
        reasons.append(f"Сохранено предпочитаемых упражнений: {len(preferred_matches)}.")
    if payload.excluded_exercise_ids:
        reasons.append("Исключённые упражнения не вошли в итоговый draft.")
    return tuple(reasons)


def _tradeoffs(candidate: _AdaptedCandidate, payload: ProgramGeneratorRequest) -> tuple[str, ...]:
    template = candidate.template
    result: list[str] = []
    if template.goal != payload.goal:
        result.append(
            f"Точного шаблона для цели «{_goal_label(payload.goal)}» нет; выбран ближайший совместимый источник."
        )
    if template.level != payload.experience:
        result.append(
            f"Источник рассчитан на {_level_label(template.level)} уровень, без advanced-only структуры для выбранного опыта."
        )
    max_duration = max(candidate.day_estimates.values(), default=0)
    if max_duration != payload.preferred_session_duration_minutes:
        result.append(
            f"Длительность не является обещанием точного времени: расчёт составляет до {max_duration} мин."
        )
    if candidate.removals:
        result.append(
            "Часть необязательной аксессуарной работы сокращена; core-структура сохранена."
        )
    if payload.priority_muscle_ids and not (
        set(payload.priority_muscle_ids) & set(candidate.primary_muscle_ids)
    ):
        result.append(
            "Источник не содержит отдельного source-backed priority slot для выбранных групп."
        )
    missing_preferences = set(payload.preferred_exercise_ids) - set(candidate.selected_ids)
    if missing_preferences:
        result.append("Некоторые предпочитаемые упражнения отсутствуют в выбранной структуре.")
    if candidate.schedule_adapted:
        result.append(
            "Частота использует представление source-backed структуры в текущей модели YFC."
        )
    return tuple(result)


def _goal_label(value: str) -> str:
    return {
        "fat_loss": "снижение веса",
        "recomposition": "рекомпозиция",
        "maintenance": "поддержание формы",
        "muscle_gain": "набор мышц",
        "strength": "развитие силы",
    }[value]


def _level_label(value: str) -> str:
    return {"beginner": "начальный", "intermediate": "средний", "advanced": "продвинутый"}[value]


def _program_from_candidate(
    candidate: _AdaptedCandidate,
) -> ProgramGeneratorProgram:
    days: list[ProgramGeneratorDay] = []
    for day in sorted(candidate.template.days, key=lambda row: row.day_number):
        slots = [slot for slot in candidate.slots_by_day[day.day_number] if not slot.removed]
        exercises = [
            ProgramGeneratorExercise(
                exercise_id=slot.selected_id,
                exercise_title=slot.selected_exercise.title,
                metric_type=cast(ExerciseMetricType, exercise_metric_type(slot.selected_exercise)),
                movement_pattern=_exercise_movement_pattern(slot.selected_exercise),
                prescribed_sets=slot.source_item.prescribed_sets,
                prescribed_reps=slot.source_item.prescribed_reps,
                prescribed_duration_minutes=slot.source_item.prescribed_duration_minutes,
                rest_seconds=slot.source_item.rest_seconds,
                notes=slot.source_item.notes,
                superset_group=slot.source_item.superset_group,
                superset_order=slot.source_item.superset_order,
                prescription=copy.deepcopy(slot.source_item.prescription),
                group_id=slot.source_item.group_id,
                group_kind=cast(PrescriptionGroupKind | None, slot.source_item.group_kind),
                group_order=slot.source_item.group_order,
                source_exercise_id=slot.source_id,
            )
            for slot in slots
        ]
        days.append(
            ProgramGeneratorDay(
                day_number=day.day_number,
                title=day.title,
                estimated_duration_minutes=candidate.day_estimates[day.day_number],
                exercises=exercises,
            )
        )
    return ProgramGeneratorProgram(
        title=candidate.template.title,
        goal=cast(ProgramRecommendationGoal, candidate.template.goal),
        level=cast(ProgramExperience, candidate.template.level),
        split_type=cast(ProgramSplitType | None, candidate.template.split_type),
        days=days,
        estimated_duration_minutes=max(candidate.day_estimates.values(), default=0),
    )


def _adaptation_models(candidate: _AdaptedCandidate) -> list[ProgramGeneratorAdaptation]:
    values = [*candidate.substitutions, *candidate.removals]
    if candidate.schedule_adapted:
        values.append(
            {
                "code": "schedule_representation",
                "message": "Source-backed частотная модель представлена в поддерживаемом цикле YFC.",
                "day_number": None,
                "source_exercise_id": None,
                "replacement_exercise_id": None,
            }
        )
    return [ProgramGeneratorAdaptation.model_validate(value) for value in values]


def _build_fingerprint(
    payload: ProgramGeneratorRequest,
    *,
    catalog_revision: str,
    hidden_ids: set[int],
    active_state: dict[str, object] | None,
) -> str:
    return _sha256(
        {
            "selection_policy_version": SELECTION_POLICY_VERSION,
            "inputs": _normalized_inputs(payload),
            "catalog_revision": catalog_revision,
            "hidden_template_ids": sorted(hidden_ids),
            "active_program_state": active_state,
        }
    )


def _draft_token(
    *,
    current_user: User,
    payload: ProgramGeneratorRequest,
    catalog_revision: str,
    hidden_ids: set[int],
    active_state: dict[str, object] | None,
    source_template_id: int,
    input_fingerprint: str,
) -> str:
    return _serializer().dumps(
        {
            "selection_policy_version": SELECTION_POLICY_VERSION,
            "user_id": current_user.id,
            "inputs": _normalized_inputs(payload),
            "catalog_revision": catalog_revision,
            "hidden_template_ids": sorted(hidden_ids),
            "active_program_state": active_state,
            "source_template_id": source_template_id,
            "input_fingerprint": input_fingerprint,
        }
    )


def _decode_draft_token(token: str, current_user: User) -> dict[str, object]:
    try:
        payload = _serializer().loads(token, max_age=_TOKEN_MAX_AGE_SECONDS)
    except BadTimeSignature as exc:
        raise ProgramGeneratorError(
            "stale_draft", "Предпросмотр программы устарел. Сформируйте его заново.", 409
        ) from exc
    except BadSignature as exc:
        raise ProgramGeneratorError(
            "invalid_draft", "Предпросмотр программы недействителен.", 422
        ) from exc
    if not isinstance(payload, dict) or payload.get("user_id") != current_user.id:
        raise ProgramGeneratorError("invalid_draft", "Предпросмотр программы недействителен.", 422)
    if payload.get("selection_policy_version") != SELECTION_POLICY_VERSION:
        raise ProgramGeneratorError("stale_draft", "Сформируйте предпросмотр заново.", 409)
    return payload


def _find_confirmed_template(
    db: Session,
    current_user: User,
    input_fingerprint: str,
) -> tuple[ProgramTemplate, UserProgram] | None:
    templates = (
        db.query(ProgramTemplate)
        .filter(
            ProgramTemplate.created_by_user_id == current_user.id,
            ProgramTemplate.owner_user_id == current_user.id,
            ProgramTemplate.provenance_type == "SOURCE_ADAPTATION",
        )
        .order_by(ProgramTemplate.id.asc())
        .all()
    )
    for template in templates:
        metadata = template.program_metadata or {}
        generator = metadata.get("generator")
        if (
            not isinstance(generator, dict)
            or generator.get("input_fingerprint") != input_fingerprint
        ):
            continue
        program = (
            db.query(UserProgram)
            .filter(UserProgram.user_id == current_user.id, UserProgram.template_id == template.id)
            .order_by(UserProgram.id.asc())
            .first()
        )
        if program is not None:
            return template, program
    return None


def _confirm_options(metadata: dict[str, object]) -> dict[str, object]:
    generator = metadata.get("generator")
    if isinstance(generator, dict) and isinstance(generator.get("confirmation"), dict):
        return dict(generator["confirmation"])
    return {}


def _build_decision(
    db: Session,
    current_user: User,
    payload: ProgramGeneratorRequest,
    *,
    expected_source_template_id: int | None = None,
) -> tuple[
    ProgramGeneratorPreviewResponse,
    _AdaptedCandidate | None,
    str,
    dict[str, object] | None,
]:
    templates, visible, alternatives, catalog_revision, hidden_ids = _load_catalog(db, current_user)
    available, preferred, excluded = _validate_request_domain(db, current_user, payload, visible)
    active_state = _active_state(db, current_user)
    fingerprint = _build_fingerprint(
        payload,
        catalog_revision=catalog_revision,
        hidden_ids=hidden_ids,
        active_state=active_state,
    )
    candidates: list[_AdaptedCandidate] = []
    reason_codes: set[str] = set()
    for template in templates:
        if template.id in hidden_ids:
            continue
        if expected_source_template_id is not None and template.id != expected_source_template_id:
            continue
        if template.split_type not in _SPLIT_LABELS:
            reason_codes.add("unsupported_structure")
            continue
        if template.goal not in _GOAL_ORDER[payload.goal]:
            reason_codes.add("goal_not_supported")
            continue
        if _LEVEL_RANK.get(template.level, 99) > _LEVEL_RANK[payload.experience]:
            reason_codes.add("experience_incompatible")
            continue
        if _source_frequency(template) != payload.days_per_week:
            reason_codes.add("frequency_not_supported")
            continue
        try:
            candidate = _adapt_candidate(
                template,
                payload=payload,
                visible=visible,
                alternatives=alternatives,
                available_equipment=available,
                excluded_ids=excluded,
            )
        except _CandidateIncompatible as exc:
            reason_codes.add(exc.code)
            continue
        # Reuse the normalized canonical IDs for ranking rather than trusting the raw client order.
        payload_for_rank = payload.model_copy(
            update={
                "preferred_exercise_ids": sorted(preferred),
                "excluded_exercise_ids": sorted(excluded),
            }
        )
        _candidate_rank(candidate, payload_for_rank)
        candidates.append(candidate)

    candidates.sort(key=lambda item: item.rank)
    if not candidates:
        if not reason_codes:
            reason_codes.add("no_compatible_program")
        ordered_codes = sorted(reason_codes)
        message = "Не удалось подобрать программу под все выбранные ограничения. Измените конкретные параметры и повторите подбор."
        if "duration_incompatible" in reason_codes:
            message = "Расчётная структура не помещается в допустимую длительность даже после безопасного сокращения аксессуарной работы."
        elif "equipment_no_canonical_substitution" in reason_codes:
            message = "Не найдено канонической замены для обязательного упражнения под выбранное оборудование."
        elif "frequency_not_supported" in reason_codes:
            message = "Для выбранной частоты нет совместимой source-backed структуры."
        response = ProgramGeneratorPreviewResponse(
            status="no_compatible",
            selection_policy_version=SELECTION_POLICY_VERSION,
            input_fingerprint=fingerprint,
            message=message,
            reason_codes=ordered_codes,
            active_program=_active_response(active_state, current_user),
        )
        return response, None, catalog_revision, active_state

    selected = candidates[0]
    token = _draft_token(
        current_user=current_user,
        payload=payload,
        catalog_revision=catalog_revision,
        hidden_ids=hidden_ids,
        active_state=active_state,
        source_template_id=selected.template.id,
        input_fingerprint=fingerprint,
    )
    source = ProgramGeneratorSource(
        template_id=selected.template.id,
        slug=selected.template.slug,
        title=selected.template.title,
        goal=cast(ProgramRecommendationGoal, selected.template.goal),
        level=cast(ProgramExperience, selected.template.level),
        split_type=cast(ProgramSplitType | None, selected.template.split_type),
        provenance_type=cast(ProgramProvenanceType, selected.template.provenance_type or "CUSTOM"),
    )
    response = ProgramGeneratorPreviewResponse(
        status="preview",
        selection_policy_version=SELECTION_POLICY_VERSION,
        input_fingerprint=fingerprint,
        message="Предпросмотр готов. Программа будет сохранена только после явного подтверждения.",
        draft_token=token,
        source=source,
        program=_program_from_candidate(selected),
        fit_reasons=list(selected.fit_reasons),
        tradeoffs=list(selected.tradeoffs),
        adaptations=_adaptation_models(selected),
        active_program=_active_response(active_state, current_user),
    )
    return response, selected, catalog_revision, active_state


def generate_program_preview(
    db: Session,
    current_user: User,
    payload: ProgramGeneratorRequest,
) -> ProgramGeneratorPreviewResponse:
    response, _candidate, _catalog_revision, _active_state_value = _build_decision(
        db, current_user, payload
    )
    return response


def _template_payload(
    candidate: _AdaptedCandidate, payload: ProgramGeneratorRequest
) -> ProgramTemplateCreate:
    days = []
    for day in sorted(candidate.template.days, key=lambda row: row.day_number):
        slots = [slot for slot in candidate.slots_by_day[day.day_number] if not slot.removed]
        days.append(
            ProgramTemplateDayCreate(
                title=day.title,
                exercises=[
                    ProgramTemplateExerciseCreate(
                        exercise_id=slot.selected_id,
                        prescribed_sets=slot.source_item.prescribed_sets,
                        prescribed_reps=slot.source_item.prescribed_reps,
                        prescribed_duration_minutes=slot.source_item.prescribed_duration_minutes,
                        rest_seconds=slot.source_item.rest_seconds,
                        notes=slot.source_item.notes,
                        superset_group=slot.source_item.superset_group,
                        superset_order=slot.source_item.superset_order,
                        group_id=slot.source_item.group_id,
                        group_kind=cast(PrescriptionGroupKind | None, slot.source_item.group_kind),
                        group_order=slot.source_item.group_order,
                        prescription=cast(
                            ExercisePrescriptionPlan | None,
                            copy.deepcopy(slot.source_item.prescription),
                        ),
                    )
                    for slot in slots
                ],
            )
        )
    return ProgramTemplateCreate(
        title=(f"Подобранная программа · {candidate.template.title}")[:128],
        goal=cast(ProgramRecommendationGoal, candidate.template.goal),
        level=cast(ProgramExperience, candidate.template.level),
        mode="self",
        days=days,
        assign_after_create=False,
        duration_weeks=candidate.template.effective_duration_weeks,
    )


def _copy_weekly_prescriptions(
    db: Session,
    source_candidate: _AdaptedCandidate,
    generated_template: ProgramTemplate,
) -> None:
    generated_items: dict[int, ProgramTemplateExercise] = {}
    for day in generated_template.days:
        source_slots = [
            slot for slot in source_candidate.slots_by_day[day.day_number] if not slot.removed
        ]
        for item, source_slot in zip(
            sorted(day.exercises, key=lambda row: (row.sort_order, row.id)),
            source_slots,
            strict=True,
        ):
            generated_items[source_slot.source_item.id] = item
    for day_slots in source_candidate.slots_by_day.values():
        for slot in day_slots:
            if slot.removed:
                continue
            target_item = generated_items.get(slot.source_item.id)
            if target_item is None:
                continue
            for weekly in sorted(
                slot.source_item.weekly_prescriptions, key=lambda row: row.week_number
            ):
                source_weekly = weekly.exercise
                selected = source_candidate.selected_by_source_id.get(
                    _effective_exercise_id(source_weekly), source_weekly
                )
                db.add(
                    ProgramTemplateExerciseWeekPrescription(
                        template_exercise_id=target_item.id,
                        exercise_id=_effective_exercise_id(selected),
                        week_number=weekly.week_number,
                        prescribed_sets=weekly.prescribed_sets,
                        prescribed_reps=weekly.prescribed_reps,
                        prescribed_duration_minutes=weekly.prescribed_duration_minutes,
                        rest_seconds=weekly.rest_seconds,
                        prescription=copy.deepcopy(weekly.prescription),
                    )
                )


def _generated_metadata(
    candidate: _AdaptedCandidate,
    payload: ProgramGeneratorRequest,
    *,
    fingerprint: str,
    catalog_revision: str,
    confirmation: ProgramGeneratorConfirmRequest,
) -> tuple[dict[str, object], dict[str, object]]:
    metadata = copy.deepcopy(candidate.template.program_metadata or {})
    adaptations = [item.model_dump(mode="json") for item in _adaptation_models(candidate)]
    generator = {
        "selection_policy_version": SELECTION_POLICY_VERSION,
        "input_fingerprint": fingerprint,
        "catalog_revision": catalog_revision,
        "source_template_id": candidate.template.id,
        "source_template_slug": candidate.template.slug,
        "adaptations": adaptations,
        "trade_offs": list(candidate.tradeoffs),
        "fit_reasons": list(candidate.fit_reasons),
        "confirmation": {
            "start_date": confirmation.start_date.isoformat() if confirmation.start_date else None,
            "duration_weeks": confirmation.duration_weeks
            or candidate.template.effective_duration_weeks,
            "replace_active": confirmation.replace_active,
        },
    }
    metadata["generator"] = generator
    metadata["days_per_week"] = payload.days_per_week
    metadata["representation_days"] = len(candidate.template.days)
    source_provenance = copy.deepcopy(candidate.template.provenance or {})
    provenance = {
        "source_template_id": candidate.template.id,
        "source_template_slug": candidate.template.slug,
        "source_program_name": source_provenance.get(
            "source_program_name", candidate.template.title
        ),
        "source_provenance_type": candidate.template.provenance_type,
        "source_version": source_provenance.get("source_version"),
        "canonical_source": source_provenance.get("canonical_source"),
        "selection_policy_version": SELECTION_POLICY_VERSION,
        "input_fingerprint": fingerprint,
        "adaptation_ledger": adaptations,
        "source_provenance": source_provenance,
    }
    return provenance, metadata


def confirm_generated_program(
    db: Session,
    current_user: User,
    payload: ProgramGeneratorConfirmRequest,
) -> dict[str, object]:
    db.query(User).filter(User.id == current_user.id).with_for_update().one()
    token_payload = _decode_draft_token(payload.draft_token, current_user)
    fingerprint = token_payload.get("input_fingerprint")
    if not isinstance(fingerprint, str):
        raise ProgramGeneratorError("invalid_draft", "Предпросмотр программы недействителен.", 422)

    existing = _find_confirmed_template(db, current_user, fingerprint)
    if existing is not None:
        template, program = existing
        confirmation = _confirm_options(template.program_metadata or {})
        requested_options: dict[str, object] = {
            "start_date": payload.start_date.isoformat() if payload.start_date else None,
            "duration_weeks": payload.duration_weeks,
            "replace_active": payload.replace_active,
        }
        if requested_options["duration_weeks"] is None:
            requested_options["duration_weeks"] = confirmation.get("duration_weeks")
        if requested_options["start_date"] is None:
            requested_options["start_date"] = confirmation.get("start_date")
        if requested_options != confirmation:
            raise ProgramGeneratorError(
                "idempotency_conflict",
                "Этот предпросмотр уже подтверждён с другими параметрами запуска.",
                409,
            )
        return {
            "status": "confirmed",
            "idempotent": True,
            "assigned_program_id": program.id,
            "workouts_created": 0,
            "template": build_template_response(template, db, current_user),
        }

    raw_inputs = token_payload.get("inputs")
    if not isinstance(raw_inputs, dict):
        raise ProgramGeneratorError("invalid_draft", "Предпросмотр программы недействителен.", 422)
    request = ProgramGeneratorRequest.model_validate(raw_inputs)
    source_template_id = token_payload.get("source_template_id")
    response, candidate, catalog_revision, active_state = _build_decision(
        db,
        current_user,
        request,
        expected_source_template_id=source_template_id
        if isinstance(source_template_id, int)
        else None,
    )
    if (
        response.status != "preview"
        or candidate is None
        or response.input_fingerprint != fingerprint
        or token_payload.get("catalog_revision") != catalog_revision
        or not _same_active_state(token_payload.get("active_program_state"), active_state)
    ):
        raise ProgramGeneratorError(
            "stale_draft",
            "Программа или текущая ревизия изменились. Сформируйте предпросмотр заново.",
            409,
        )
    if active_state is not None:
        assigned_by = active_state.get("assigned_by_user_id")
        if isinstance(assigned_by, int) and assigned_by != current_user.id:
            raise ProgramGeneratorError(
                "trainer_owned_program",
                "Личная подборка не может заменить программу, назначенную тренером.",
                403,
            )
        if not payload.replace_active:
            raise ProgramGeneratorError(
                "active_program_confirmation_required",
                "Текущая программа будет отправлена в архив. Подтвердите замену явно.",
                409,
            )

    duration_weeks = payload.duration_weeks or candidate.template.effective_duration_weeks
    create_payload = _template_payload(candidate, request).model_copy(
        update={"duration_weeks": duration_weeks}
    )
    template = create_template(db, current_user, create_payload, current_user, force_private=True)
    template.split_type = candidate.template.split_type
    template.default_duration_weeks = candidate.template.effective_duration_weeks
    template.provenance_type = "SOURCE_ADAPTATION"
    provenance, metadata = _generated_metadata(
        candidate,
        request,
        fingerprint=fingerprint,
        catalog_revision=catalog_revision,
        confirmation=payload,
    )
    template.provenance = provenance
    template.program_metadata = metadata
    db.flush()
    _copy_weekly_prescriptions(db, candidate, template)
    program, workouts_created = assign_template_to_user(
        db,
        template,
        current_user,
        current_user,
        start_date=payload.start_date,
        duration_weeks=duration_weeks,
        replace_active=payload.replace_active,
    )
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        action="program_generator.confirmed",
        resource_type="program_generator",
        resource_id=program.id,
        details={
            "selection_policy_version": SELECTION_POLICY_VERSION,
            "input_fingerprint": fingerprint,
            "source_template_id": candidate.template.id,
            "assigned_program_id": program.id,
            "workouts_created": workouts_created,
        },
    )
    db.commit()
    db.refresh(template)
    return {
        "status": "confirmed",
        "idempotent": False,
        "assigned_program_id": program.id,
        "workouts_created": workouts_created,
        "template": build_template_response(template, db, current_user),
    }
