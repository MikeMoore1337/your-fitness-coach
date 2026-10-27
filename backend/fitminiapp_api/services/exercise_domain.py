from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.models.exercise import (
    Equipment,
    Exercise,
    ExerciseAlternative,
    ExerciseEquipment,
    ExerciseGuideMetadata,
    ExerciseMuscle,
    Muscle,
)

MUSCLE_TAXONOMY = (
    ("chest", "Грудь"),
    ("back", "Спина"),
    ("spinal_erectors", "Разгибатели спины"),
    ("quadriceps", "Квадрицепс"),
    ("hamstrings", "Бицепс бедра"),
    ("glutes", "Ягодицы"),
    ("legs", "Ноги"),
    ("posterior_chain", "Задняя цепь"),
    ("shoulders", "Плечи"),
    ("anterior_deltoid", "Передняя дельта"),
    ("middle_deltoid", "Средняя дельта"),
    ("posterior_deltoid", "Задняя дельта"),
    ("lower_trapezius", "Нижняя трапеция"),
    ("trapezius", "Трапеции"),
    ("biceps", "Бицепс"),
    ("triceps", "Трицепс"),
    ("forearms", "Предплечья"),
    ("grip", "Хват"),
    ("calves", "Икры"),
    ("abs", "Пресс"),
    ("core", "Кор"),
    ("obliques", "Косые мышцы"),
    ("adductors", "Приводящие"),
    ("full_body", "Все тело"),
    ("cardio", "Кардио"),
    ("conditioning", "Кондиция"),
)

# Non-anatomical catalog categories remain valid exercise metadata, but they
# cannot be selected as an individual muscle-development priority.
BODY_PRIORITY_EXCLUDED_MUSCLE_IDS = frozenset({"cardio", "conditioning", "full_body"})
BODY_PRIORITY_TAXONOMY = tuple(
    item for item in MUSCLE_TAXONOMY if item[0] not in BODY_PRIORITY_EXCLUDED_MUSCLE_IDS
)

EQUIPMENT_TAXONOMY = (
    ("bodyweight", "Собственный вес"),
    ("dumbbell", "Гантели"),
    ("barbell", "Штанга"),
    ("bench", "Скамья"),
    ("cable", "Тросовый блок"),
    ("machine", "Тренажёр"),
    ("kettlebell", "Гиря"),
    ("cardio", "Кардиооборудование"),
    ("other", "Другое"),
)

EQUIPMENT_IDENTIFIER_BY_LEGACY_VALUE = {
    "Без оборудования": "bodyweight",
    "Брусья": "bodyweight",
    "Собственный вес": "bodyweight",
    "Турник": "bodyweight",
    "Гантели": "dumbbell",
    "Гантель": "dumbbell",
    "EZ-штанга": "barbell",
    "Штанга": "barbell",
    "Скамья": "bench",
    "Скамья Скотта": "bench",
    "Блок": "cable",
    "Кроссовер": "cable",
    "Машина Смита": "machine",
    "Тренажер": "machine",
    "Тренажёр": "machine",
    "Гиря": "kettlebell",
    "Бассейн": "cardio",
    "Беговая дорожка": "cardio",
    "Гребной тренажёр": "cardio",
    "Воздушный велотренажёр": "cardio",
    "Горизонтальный велотренажёр": "cardio",
    "Велосипед": "cardio",
    "Велотренажёр": "cardio",
    "Лыжный эргометр": "cardio",
    "Скакалка": "cardio",
    "Степпер": "cardio",
    "Эллиптический тренажёр": "cardio",
    "Канаты": "other",
    "Медбол": "other",
    "Ролик": "other",
    "Сани": "other",
    "Тумба": "other",
}

# These are intentionally explicit substitutions between similar movement patterns.
# Sharing a primary muscle is not enough to create an alternative.
CURATED_ALTERNATIVE_SLUG_PAIRS = (
    ("bench-press", "dumbbell-bench-press"),
    ("bench-press", "machine-chest-press"),
    ("incline-bench-press", "incline-dumbbell-press"),
    ("incline-bench-press", "machine-incline-chest-press"),
    ("decline-bench-press", "decline-dumbbell-press"),
    ("decline-bench-press", "machine-decline-chest-press"),
    ("dumbbell-fly", "cable-fly"),
    ("incline-dumbbell-fly", "low-to-high-cable-fly"),
    ("push-up", "machine-chest-press"),
    ("machine-chest-press", "independent-lever-chest-press"),
    ("pull-up", "lat-pulldown"),
    ("lat-pulldown", "independent-lever-lat-pulldown"),
    ("chin-up", "reverse-grip-lat-pulldown"),
    ("barbell-row", "chest-supported-row"),
    ("seated-cable-row", "machine-row"),
    ("chest-supported-row", "lever-high-row"),
    ("chest-supported-row", "lever-low-row"),
    ("chest-supported-row", "chest-supported-dumbbell-row"),
    ("one-arm-dumbbell-row", "cable-row-one-arm"),
    ("dumbbell-pullover", "straight-arm-pulldown"),
    ("dumbbell-pullover", "machine-pullover"),
    ("squat", "goblet-squat"),
    ("squat", "bodyweight-squat"),
    ("squat", "leg-press"),
    ("front-squat", "hack-squat"),
    ("hack-squat", "pendulum-squat"),
    ("hack-squat", "v-squat-machine"),
    ("leg-press", "plate-loaded-leg-press"),
    ("leg-press", "unilateral-leg-press"),
    ("lunge", "reverse-lunge"),
    ("bulgarian-split-squat", "split-squat"),
    ("split-squat", "smith-split-squat"),
    ("romanian-deadlift", "stiff-leg-deadlift"),
    ("leg-curl", "seated-leg-curl"),
    ("hip-thrust", "barbell-glute-bridge"),
    ("barbell-glute-bridge", "bodyweight-glute-bridge"),
    ("hip-thrust", "machine-hip-thrust"),
    ("cable-kickback", "machine-glute-kickback"),
    ("hyperextension", "reverse-hyperextension"),
    ("overhead-press", "seated-dumbbell-press"),
    ("machine-shoulder-press", "smith-shoulder-press"),
    ("machine-shoulder-press", "independent-lever-shoulder-press"),
    ("dumbbell-lateral-raise", "cable-lateral-raise"),
    ("cable-lateral-raise", "machine-lateral-raise"),
    ("rear-delt-fly", "reverse-pec-deck"),
    ("barbell-shrug", "dumbbell-shrug"),
    ("barbell-curl", "ez-bar-curl"),
    ("dumbbell-curl", "cable-curl"),
    ("rope-pushdown", "cable-pushdown"),
    ("cable-pushdown", "machine-triceps-extension"),
    ("overhead-triceps-extension", "dumbbell-overhead-extension"),
    ("standing-calf-raise", "single-leg-calf-raise"),
    ("crunch", "cable-crunch"),
    ("hanging-leg-raise", "captain-chair-leg-raise"),
    ("outdoor-run", "treadmill-run"),
    ("outdoor-walk", "treadmill-walk"),
    ("outdoor-cycling", "stationary-bike"),
    ("stationary-bike", "recumbent-bike"),
    ("floor-press", "bench-press"),
    ("push-press", "overhead-press"),
    ("assisted-pull-ups", "pull-up"),
    ("decline-crunch", "crunch"),
    ("overhead-squat", "front-squat"),
    ("trap-bar-deadlift", "deadlift"),
    ("safety-bar-squat", "squat"),
    ("negative-pull-ups", "pull-up"),
    ("assisted-dips", "machine-dip"),
    ("machine-seated-crunch", "cable-crunch"),
    ("db-squat", "goblet-squat"),
    ("hang-power-clean", "kettlebell-clean"),
)

DEFAULT_SAFETY_NOTES = [
    "Используй нагрузку и амплитуду, при которых сохраняется описанная техника; "
    "при острой боли останови подход."
]
SOURCE_LICENSE_URL = "https://github.com/yuhonas/free-exercise-db/blob/main/LICENSE.md"

MUSCLE_IDENTIFIER_BY_NAME = {name: identifier for identifier, name in MUSCLE_TAXONOMY}
MUSCLE_NAME_BY_IDENTIFIER = dict(MUSCLE_TAXONOMY)
EQUIPMENT_NAME_BY_IDENTIFIER = dict(EQUIPMENT_TAXONOMY)


def _normalized_lookup(value: str) -> str:
    return " ".join(value.strip().casefold().split())


_MUSCLE_IDENTIFIER_BY_INPUT = {
    _normalized_lookup(value): identifier
    for identifier, name in MUSCLE_TAXONOMY
    for value in (identifier, name)
}
_EQUIPMENT_IDENTIFIER_BY_INPUT = {
    _normalized_lookup(value): identifier
    for identifier, name in EQUIPMENT_TAXONOMY
    for value in (identifier, name)
}
_EQUIPMENT_IDENTIFIER_BY_INPUT.update(
    {
        _normalized_lookup(value): identifier
        for value, identifier in EQUIPMENT_IDENTIFIER_BY_LEGACY_VALUE.items()
    }
)


def canonical_muscle_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return _MUSCLE_IDENTIFIER_BY_INPUT.get(_normalized_lookup(value))


def canonical_equipment_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return _EQUIPMENT_IDENTIFIER_BY_INPUT.get(_normalized_lookup(value))


def exercise_metadata_load_options():
    return (
        selectinload(Exercise.muscle_links).selectinload(ExerciseMuscle.muscle),
        selectinload(Exercise.equipment_links).selectinload(ExerciseEquipment.equipment),
        selectinload(Exercise.guide_metadata),
    )


def _ensure_taxonomies(db: Session) -> tuple[dict[str, Muscle], dict[str, Equipment]]:
    muscles = {row.identifier: row for row in db.query(Muscle).all()}
    for identifier, name in MUSCLE_TAXONOMY:
        muscle_row = muscles.get(identifier)
        if muscle_row is None:
            muscle_row = Muscle(identifier=identifier, name=name)
            db.add(muscle_row)
            muscles[identifier] = muscle_row
        else:
            muscle_row.name = name

    equipment = {row.identifier: row for row in db.query(Equipment).all()}
    for identifier, name in EQUIPMENT_TAXONOMY:
        equipment_row = equipment.get(identifier)
        if equipment_row is None:
            equipment_row = Equipment(identifier=identifier, name=name)
            db.add(equipment_row)
            equipment[identifier] = equipment_row
        else:
            equipment_row.name = name

    db.flush()
    return muscles, equipment


def _base_slug(exercise: Exercise) -> str:
    return exercise.slug.split("-u-", maxsplit=1)[0]


def _profile_secondary_names(exercise: Exercise) -> list[str] | None:
    from fitminiapp_api.services.exercise_catalog_metadata import ITEM_GUIDE_CONTENT
    from fitminiapp_api.services.exercise_guides import PROFILES, SLUG_TO_PROFILE

    slug = _base_slug(exercise)
    profile_name = SLUG_TO_PROFILE.get(slug)
    if profile_name is None:
        return None
    return list(ITEM_GUIDE_CONTENT.get(slug, PROFILES[profile_name])["secondary"])


def _replace_muscle_links(
    db: Session,
    exercise: Exercise,
    muscles: dict[str, Muscle],
    secondary_names: Iterable[str],
) -> None:
    primary_identifier = canonical_muscle_identifier(exercise.primary_muscle)
    used: set[str] = set()
    desired: list[tuple[int, str, int]] = []
    if primary_identifier is not None:
        desired.append((muscles[primary_identifier].id, "primary", 0))
        used.add(primary_identifier)

    position = 0
    for name in secondary_names:
        identifier = canonical_muscle_identifier(name)
        if identifier is None or identifier in used:
            continue
        desired.append((muscles[identifier].id, "secondary", position))
        used.add(identifier)
        position += 1

    existing = {link.muscle_id: link for link in exercise.muscle_links}
    desired_ids = {muscle_id for muscle_id, _, _ in desired}
    removed = False
    for muscle_id, link in existing.items():
        if muscle_id not in desired_ids:
            db.delete(link)
            removed = True
    if removed:
        db.flush()
    for muscle_id, role, desired_position in desired:
        existing_link = existing.get(muscle_id)
        if existing_link is None:
            db.add(
                ExerciseMuscle(
                    exercise_id=exercise.id,
                    muscle_id=muscle_id,
                    role=role,
                    position=desired_position,
                )
            )
        else:
            existing_link.role = role
            existing_link.position = desired_position


def _replace_equipment_links(
    db: Session,
    exercise: Exercise,
    equipment: dict[str, Equipment],
) -> None:
    identifier = canonical_equipment_identifier(exercise.equipment)
    desired_id = equipment[identifier].id if identifier is not None else None
    existing = {link.equipment_id: link for link in exercise.equipment_links}
    if desired_id is not None and desired_id in existing and len(existing) == 1:
        existing[desired_id].position = 0
        return
    for link in existing.values():
        db.delete(link)
    if existing:
        db.flush()
    if desired_id is not None:
        db.add(
            ExerciseEquipment(
                exercise_id=exercise.id,
                equipment_id=desired_id,
                position=0,
            )
        )


def _sync_guide_metadata(db: Session, exercise: Exercise, *, has_guide: bool) -> None:
    existing = db.get(ExerciseGuideMetadata, exercise.id)
    if not has_guide:
        if existing is not None:
            db.delete(existing)
        return

    from fitminiapp_api.services.exercise_catalog_metadata import MEDIA_STATE_BY_SLUG
    from fitminiapp_api.services.exercise_guides import (
        SOURCE_LICENSE,
        SOURCE_NAME,
        SOURCE_URL,
        YFC_ORIGINAL_VECTOR_SLUGS,
        YFC_SINGLE_IMAGE_SLUGS,
    )

    slug = _base_slug(exercise)
    generated = slug in YFC_SINGLE_IMAGE_SLUGS or slug in YFC_ORIGINAL_VECTOR_SLUGS
    content_only = slug in MEDIA_STATE_BY_SLUG
    values = {
        "safety_notes": list(DEFAULT_SAFETY_NOTES),
        "source_name": "Your Fitness Coach" if generated or content_only else SOURCE_NAME,
        "source_url": "/" if generated or content_only else SOURCE_URL,
        "source_license": (
            "Техника написана для приложения"
            if content_only
            else "Иллюстрация создана для приложения"
            if generated
            else SOURCE_LICENSE
        ),
        "source_license_url": None if generated or content_only else SOURCE_LICENSE_URL,
        "media_reference": f"exercise-guides:{slug}",
    }
    if existing is None:
        db.add(ExerciseGuideMetadata(exercise_id=exercise.id, **values))
        return
    for field, value in values.items():
        setattr(existing, field, value)


def sync_exercise_domain_metadata(db: Session, exercise: Exercise) -> None:
    db.flush()
    muscles, equipment = _ensure_taxonomies(db)
    secondary_names = _profile_secondary_names(exercise)
    _replace_muscle_links(db, exercise, muscles, secondary_names or ())
    _replace_equipment_links(db, exercise, equipment)
    _sync_guide_metadata(db, exercise, has_guide=secondary_names is not None)
    db.flush()
    db.expire(exercise, ["muscle_links", "equipment_links", "guide_metadata"])


def sync_catalog_exercise_domain_metadata(db: Session, exercises: Iterable[Exercise]) -> None:
    rows = list(exercises)
    muscles, equipment = _ensure_taxonomies(db)
    for exercise in rows:
        secondary_names = _profile_secondary_names(exercise)
        _replace_muscle_links(db, exercise, muscles, secondary_names or ())
        _replace_equipment_links(db, exercise, equipment)
        _sync_guide_metadata(db, exercise, has_guide=secondary_names is not None)

    db.flush()
    db.query(ExerciseAlternative).delete(synchronize_session=False)
    db.flush()
    by_slug = {exercise.slug: exercise for exercise in rows}
    for left_slug, right_slug in CURATED_ALTERNATIVE_SLUG_PAIRS:
        left = by_slug.get(left_slug)
        right = by_slug.get(right_slug)
        if left is None or right is None:
            continue
        first_id, second_id = sorted((left.id, right.id))
        db.add(
            ExerciseAlternative(
                exercise_id=first_id,
                alternative_exercise_id=second_id,
            )
        )
    db.flush()
    for exercise in rows:
        db.expire(exercise, ["muscle_links", "equipment_links", "guide_metadata"])


def exercise_muscle_payload(exercise: Exercise) -> list[dict[str, str]]:
    return [
        {
            "identifier": link.muscle.identifier,
            "name": link.muscle.name,
            "role": link.role,
        }
        for link in exercise.muscle_links
    ]


def exercise_equipment_payload(exercise: Exercise) -> list[dict[str, str]]:
    return [
        {
            "identifier": link.equipment.identifier,
            "name": link.equipment.name,
        }
        for link in exercise.equipment_links
    ]


def alternative_payloads_by_exercise_id(
    db: Session,
    exercises: Iterable[Exercise],
) -> dict[int, list[dict[str, int | str]]]:
    rows = list(exercises)
    visible_by_effective_id: dict[int, Exercise] = {}
    for row in rows:
        visible_by_effective_id.setdefault(row.source_exercise_id or row.id, row)
    exercise_ids = set(visible_by_effective_id)
    result: dict[int, list[dict[str, int | str]]] = {
        exercise_id: [] for exercise_id in exercise_ids
    }
    if not exercise_ids:
        return result

    pairs = (
        db.query(ExerciseAlternative)
        .filter(
            or_(
                ExerciseAlternative.exercise_id.in_(exercise_ids),
                ExerciseAlternative.alternative_exercise_id.in_(exercise_ids),
            )
        )
        .all()
    )
    for pair in pairs:
        for exercise_id, alternative_id in (
            (pair.exercise_id, pair.alternative_exercise_id),
            (pair.alternative_exercise_id, pair.exercise_id),
        ):
            exercise = visible_by_effective_id.get(exercise_id)
            alternative = visible_by_effective_id.get(alternative_id)
            if exercise is None or alternative is None:
                continue
            result[exercise_id].append(
                {
                    "id": alternative_id,
                    "slug": _base_slug(alternative),
                    "title": alternative.title,
                }
            )
    for alternatives in result.values():
        alternatives.sort(key=lambda item: str(item["title"]).casefold())
    return result
