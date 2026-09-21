from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.models.exercise import Exercise, ExerciseEquipment
from fitminiapp_api.models.program import (
    HiddenProgramTemplate,
    ProgramTemplate,
    ProgramTemplateDay,
    ProgramTemplateExercise,
)
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.program import ProgramRecommendationRequest
from fitminiapp_api.services.exercise_domain import EQUIPMENT_NAME_BY_IDENTIFIER
from fitminiapp_api.services.programs import LEGACY_DEMO_TEMPLATE_SLUG
from fitminiapp_api.services.training_preferences import (
    avoided_exercise_ids,
    equipment_for_location,
    preferred_exercise_ids,
    single_training_location,
)

GOAL_ORDER = {
    "fat_loss": ("fat_loss", "recomposition", "maintenance"),
    "recomposition": ("recomposition", "muscle_gain", "maintenance"),
    "maintenance": ("maintenance", "recomposition", "muscle_gain"),
    "muscle_gain": ("muscle_gain", "recomposition"),
    # Strength is deliberately strict: a general hypertrophy template must not
    # be relabelled as strength-oriented without reviewed template metadata.
    "strength": ("strength",),
}
LEVEL_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}
SPLIT_LABELS = {
    "full_body": "всё тело за тренировку",
    "upper_lower": "верх/низ",
    "push_pull_legs": "тяни/толкай/ноги",
    "body_part": "по группам мышц",
    "hybrid": "комбинированный сплит",
}
SPLIT_PREFERENCES = {
    ("beginner", "2_3"): ("full_body", "upper_lower", "hybrid"),
    ("beginner", "4"): ("full_body", "upper_lower", "hybrid"),
    ("beginner", "5_plus"): ("full_body", "upper_lower", "hybrid"),
    ("intermediate", "2_3"): ("full_body", "upper_lower", "hybrid", "body_part"),
    ("intermediate", "4"): ("upper_lower", "hybrid", "full_body", "body_part"),
    ("intermediate", "5_plus"): (
        "body_part",
        "push_pull_legs",
        "upper_lower",
        "hybrid",
        "full_body",
    ),
    ("advanced", "2_3"): ("full_body", "upper_lower", "hybrid"),
    ("advanced", "4"): ("upper_lower", "hybrid", "body_part", "full_body"),
    ("advanced", "5_plus"): (
        "push_pull_legs",
        "body_part",
        "hybrid",
        "upper_lower",
        "full_body",
    ),
}


@dataclass(frozen=True)
class RecommendationCriteria:
    goal: str | None
    experience: str | None
    workouts_per_week: int | None
    training_location: str | None
    available_equipment_ids: frozenset[str] | None
    preferred_exercise_ids: frozenset[int] = field(default_factory=frozenset)
    avoided_exercise_ids: frozenset[int] = field(default_factory=frozenset)
    profile_fields_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProgramCandidate:
    template: ProgramTemplate
    required_equipment_ids: frozenset[str]
    equipment_metadata_complete: bool
    exercise_ids: frozenset[int] = field(default_factory=frozenset)

    @property
    def training_days(self) -> int:
        return len(self.template.days)


@dataclass(frozen=True)
class RankedProgramCandidate:
    candidate: ProgramCandidate
    rank: tuple[int, int, int, int, int, str, int]
    reason: str
    fit_facts: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ProgramRecommendationDecision:
    status: str
    criteria: RecommendationCriteria
    missing_fields: tuple[str, ...]
    message: str
    ranked_candidates: tuple[RankedProgramCandidate, ...] = ()


def _frequency_bucket(workouts_per_week: int) -> str:
    if workouts_per_week <= 3:
        return "2_3"
    if workouts_per_week == 4:
        return "4"
    return "5_plus"


def _resolve_criteria(
    profile: UserProfile | None,
    payload: ProgramRecommendationRequest,
) -> RecommendationCriteria:
    profile_fields_used: list[str] = []

    goal: str | None = payload.goal
    if goal is None and profile and profile.goal in GOAL_ORDER:
        goal = profile.goal
        profile_fields_used.append("goal")

    experience: str | None = payload.experience
    if experience is None and profile and profile.level in LEVEL_RANK:
        experience = profile.level
        profile_fields_used.append("experience")

    workouts_per_week = payload.workouts_per_week
    if workouts_per_week is None and profile and profile.workouts_per_week is not None:
        workouts_per_week = profile.workouts_per_week
        profile_fields_used.append("workouts_per_week")

    training_location = payload.training_location or single_training_location(profile)
    equipment = (
        frozenset(payload.available_equipment_ids)
        if payload.available_equipment_ids is not None
        else equipment_for_location(profile, training_location)
    )
    preferred_ids = preferred_exercise_ids(profile)
    avoided_ids = avoided_exercise_ids(profile)
    if payload.training_location is None and training_location is not None:
        profile_fields_used.append("training_location")
    if payload.available_equipment_ids is None and equipment is not None:
        profile_fields_used.append("available_equipment")
    if preferred_ids:
        profile_fields_used.append("preferred_exercises")
    if avoided_ids:
        profile_fields_used.append("avoided_exercises")

    return RecommendationCriteria(
        goal=goal,
        experience=experience,
        workouts_per_week=workouts_per_week,
        training_location=training_location,
        available_equipment_ids=equipment,
        preferred_exercise_ids=preferred_ids,
        avoided_exercise_ids=avoided_ids,
        profile_fields_used=tuple(profile_fields_used),
    )


def _candidate_from_template(template: ProgramTemplate) -> ProgramCandidate:
    required_equipment: set[str] = set()
    metadata_complete = True
    exercise_ids: set[int] = set()
    for day in template.days:
        for template_exercise in day.exercises:
            exercise = template_exercise.exercise
            exercise_ids.add(exercise.source_exercise_id or exercise.id)
            links = exercise.equipment_links
            if exercise.equipment and not links:
                metadata_complete = False
            for link in links:
                identifier = link.equipment.identifier
                if identifier != "bodyweight":
                    required_equipment.add(identifier)
    return ProgramCandidate(
        template=template,
        required_equipment_ids=frozenset(required_equipment),
        equipment_metadata_complete=metadata_complete,
        exercise_ids=frozenset(exercise_ids),
    )


def _goal_label(goal: str) -> str:
    return {
        "fat_loss": "снижение веса",
        "recomposition": "улучшение композиции тела",
        "maintenance": "поддержание формы",
        "muscle_gain": "набор мышечной массы",
        "strength": "развитие силы",
    }[goal]


def _level_label(level: str) -> str:
    return {
        "beginner": "начальный",
        "intermediate": "средний",
        "advanced": "продвинутый",
    }[level]


def _rank_candidate(
    candidate: ProgramCandidate,
    criteria: RecommendationCriteria,
) -> RankedProgramCandidate | None:
    assert criteria.goal is not None
    assert criteria.experience is not None
    assert criteria.workouts_per_week is not None

    template = candidate.template
    if template.split_type not in SPLIT_LABELS:
        return None

    goal_order = GOAL_ORDER[criteria.goal]
    if template.goal not in goal_order:
        return None
    goal_rank = goal_order.index(template.goal)

    requested_level_rank = LEVEL_RANK[criteria.experience]
    template_level_rank = LEVEL_RANK.get(template.level)
    if template_level_rank is None or template_level_rank > requested_level_rank:
        return None
    level_gap = requested_level_rank - template_level_rank

    frequency_distance = abs(candidate.training_days - criteria.workouts_per_week)
    if frequency_distance > 1:
        return None
    if candidate.training_days == 8 and criteria.workouts_per_week != 8:
        return None

    if criteria.available_equipment_ids is not None:
        if not candidate.equipment_metadata_complete:
            return None
        if not candidate.required_equipment_ids.issubset(criteria.available_equipment_ids):
            return None
    if candidate.exercise_ids & criteria.avoided_exercise_ids:
        return None

    preferences = SPLIT_PREFERENCES[
        (criteria.experience, _frequency_bucket(criteria.workouts_per_week))
    ]
    split_rank = (
        preferences.index(template.split_type)
        if template.split_type in preferences
        else len(preferences)
    )

    fit_facts = [
        f"Цель подбора: {_goal_label(criteria.goal)}.",
        f"Уровень: {_level_label(criteria.experience)}.",
        f"Формат: {SPLIT_LABELS[template.split_type]}.",
        f"В шаблоне {candidate.training_days} тренировок за цикл.",
    ]
    limitations: list[str] = []
    if goal_rank:
        limitations.append(
            f"Вместо точного совпадения по цели используется совместимый шаблон для "
            f"«{_goal_label(template.goal)}».",
        )
    if level_gap:
        limitations.append(
            f"Шаблон рассчитан на {_level_label(template.level)} уровень; "
            "его можно усложнить в личной копии.",
        )
    if frequency_distance:
        limitations.append(
            f"Желаемая частота — {criteria.workouts_per_week}, а в шаблоне "
            f"{candidate.training_days} тренировок за цикл.",
        )
    if criteria.available_equipment_ids is None:
        limitations.append("Доступное оборудование не указано и не участвовало в проверке.")
    elif candidate.required_equipment_ids:
        names = [
            EQUIPMENT_NAME_BY_IDENTIFIER[identifier]
            for identifier in sorted(candidate.required_equipment_ids)
        ]
        fit_facts.append(f"Доступное оборудование подходит: {', '.join(names)}.")
    else:
        fit_facts.append("Для шаблона не требуется отдельное оборудование.")
    if criteria.training_location:
        location = {"gym": "зал", "home": "дом", "other": "другое место"}[
            criteria.training_location
        ]
        fit_facts.append(f"Указанное место тренировок: {location}.")
    preferred_matches = candidate.exercise_ids & criteria.preferred_exercise_ids
    if preferred_matches:
        fit_facts.append(f"В составе есть предпочитаемые упражнения: {len(preferred_matches)}.")
    if criteria.avoided_exercise_ids:
        fit_facts.append("Упражнения из списка «избегать» исключены.")
    if candidate.training_days == 8:
        limitations.append(
            "Это восьмидневный последовательный цикл, а не восемь тренировок в календарную неделю."
        )

    if frequency_distance == 0 and goal_rank == 0 and level_gap == 0:
        reason = (
            "Шаблон точно совпадает с целью, уровнем и выбранным числом тренировок; "
            "формат выбран по таблице решений."
        )
    else:
        reason = (
            "Это ближайший совместимый шаблон по цели, частоте, уровню и формату "
            "с учётом указанных ограничений."
        )

    return RankedProgramCandidate(
        candidate=candidate,
        rank=(
            goal_rank,
            frequency_distance,
            split_rank,
            level_gap,
            len(criteria.preferred_exercise_ids - candidate.exercise_ids),
            template.slug,
            template.id,
        ),
        reason=reason,
        fit_facts=tuple(fit_facts),
        limitations=tuple(limitations),
    )


def rank_program_candidates(
    candidates: list[ProgramCandidate],
    criteria: RecommendationCriteria,
) -> ProgramRecommendationDecision:
    missing_fields = tuple(
        field
        for field, value in (
            ("goal", criteria.goal),
            ("experience", criteria.experience),
            ("workouts_per_week", criteria.workouts_per_week),
        )
        if value is None
    )
    if missing_fields:
        return ProgramRecommendationDecision(
            status="needs_input",
            criteria=criteria,
            missing_fields=missing_fields,
            message="Заполните недостающие параметры, чтобы подобрать программу.",
        )

    if criteria.workouts_per_week is None or not 1 <= criteria.workouts_per_week <= 8:
        return ProgramRecommendationDecision(
            status="no_match",
            criteria=criteria,
            missing_fields=(),
            message=(
                "Готовые шаблоны поддерживают от одной до восьми тренировок за цикл. "
                "Выберите программу вручную или создайте свою."
            ),
        )

    ranked = [
        ranked_candidate
        for candidate in candidates
        if (ranked_candidate := _rank_candidate(candidate, criteria)) is not None
    ]
    ranked.sort(key=lambda item: item.rank)

    if not ranked:
        if criteria.goal == "strength":
            message = (
                "В каталоге пока нет проверенного шаблона с целью «развитие силы». "
                "Выберите программу вручную или создайте свою."
            )
        elif criteria.available_equipment_ids is not None:
            message = (
                "Нет шаблона, совместимого со всеми выбранными параметрами и оборудованием. "
                "Измените фильтры, выберите программу вручную или создайте свою."
            )
        else:
            message = (
                "Нет шаблона, совместимого со всеми выбранными параметрами. "
                "Выберите программу вручную или создайте свою."
            )
        return ProgramRecommendationDecision(
            status="no_match",
            criteria=criteria,
            missing_fields=(),
            message=message,
        )

    return ProgramRecommendationDecision(
        status="recommended",
        criteria=criteria,
        missing_fields=(),
        message="Сначала посмотрите состав программы. Запуск выполняется отдельным действием.",
        ranked_candidates=tuple(ranked),
    )


def recommend_program_templates(
    db: Session,
    current_user: User,
    payload: ProgramRecommendationRequest,
) -> ProgramRecommendationDecision:
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).one_or_none()
    criteria = _resolve_criteria(profile, payload)
    missing = any(
        value is None for value in (criteria.goal, criteria.experience, criteria.workouts_per_week)
    )
    if missing:
        return rank_program_candidates([], criteria)

    hidden_template_ids = {
        template_id
        for (template_id,) in db.query(HiddenProgramTemplate.template_id)
        .filter(HiddenProgramTemplate.user_id == current_user.id)
        .all()
    }
    exercise_loader = (
        selectinload(ProgramTemplate.days)
        .selectinload(ProgramTemplateDay.exercises)
        .selectinload(ProgramTemplateExercise.exercise)
    )
    templates = (
        db.query(ProgramTemplate)
        .options(
            exercise_loader.selectinload(Exercise.equipment_links).selectinload(
                ExerciseEquipment.equipment
            )
        )
        .filter(
            ProgramTemplate.is_public.is_(True),
            ProgramTemplate.owner_user_id.is_(None),
            ProgramTemplate.created_by_user_id.is_(None),
            # Source-backed library additions remain explicitly selectable until
            # the approved discovery/filter surface owns their recommendation rules.
            ProgramTemplate.provenance_type == "YFC_GENERIC",
            ProgramTemplate.slug != LEGACY_DEMO_TEMPLATE_SLUG,
        )
        .order_by(ProgramTemplate.slug.asc(), ProgramTemplate.id.asc())
        .all()
    )
    candidates = [
        _candidate_from_template(template)
        for template in templates
        if template.id not in hidden_template_ids
    ]
    return rank_program_candidates(candidates, criteria)
