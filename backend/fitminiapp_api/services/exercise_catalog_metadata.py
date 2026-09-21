from __future__ import annotations

from functools import lru_cache
from typing import Literal, NotRequired, TypedDict, cast


class ExerciseCatalogMetadata(TypedDict):
    aliases: tuple[str, ...]
    movement_pattern: str
    machine_variant_tags: tuple[str, ...]
    execution_variant_tags: tuple[str, ...]


class StructuredExerciseCatalogMetadata(ExerciseCatalogMetadata):
    primary_muscle: str
    secondary_muscles: tuple[str, ...]
    equipment: str
    difficulty_level: Literal["beginner", "intermediate", "advanced"]
    metric_type: Literal["strength", "cardio"]


class ExerciseGuideContent(TypedDict):
    steps: list[str]
    breathing: str
    mistakes: list[str]
    secondary: list[str]
    safety_notes: NotRequired[list[str]]


class ExerciseMediaState(TypedDict):
    state: Literal["repdb_phased", "repdb_single_static", "repdb_source_gap"]
    source_slug: str | None
    phases: tuple[str, ...]


UPPER_BODY_MACHINE_SLUGS = (
    "machine-incline-chest-press",
    "independent-lever-chest-press",
    "lever-high-row",
    "lever-low-row",
    "independent-lever-lat-pulldown",
    "machine-pullover",
    "independent-lever-shoulder-press",
    "machine-decline-chest-press",
    "machine-triceps-extension",
    "chest-supported-dumbbell-row",
)

LOWER_BODY_MACHINE_SLUGS = (
    "pendulum-squat",
    "plate-loaded-leg-press",
    "unilateral-leg-press",
    "machine-hip-thrust",
    "smith-split-squat",
    "machine-glute-kickback",
    "v-squat-machine",
    "reverse-hyperextension",
)

REMAINING_COVERAGE_SLUGS = (
    "bodyweight-squat",
    "bodyweight-glute-bridge",
    "barbell-wrist-curl",
    "barbell-wrist-extension",
    "dead-hang",
    "recumbent-bike",
)

# The old row remains in storage for program/workout history. Search consumers
# group it into the canonical record instead of deleting or rewriting references.
CANONICAL_EXERCISE_REDIRECTS = {
    "kettlebell-goblet-squat": "goblet-squat",
}


CATALOG_METADATA: dict[str, ExerciseCatalogMetadata] = {
    "cable-fly": {
        "aliases": (
            "cable crossover",
            "сведение рук сверху вниз в кроссовере",
            "high to low cable fly",
        ),
        "movement_pattern": "chest_fly",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "goblet-squat": {
        "aliases": (
            "гоблет",
            "goblet squat",
            "kettlebell goblet squat",
            "гоблет присед",
        ),
        "movement_pattern": "squat",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "bodyweight-squat": {
        "aliases": (
            "приседания без веса",
            "воздушные приседания",
            "air squat",
            "bodyweight squat",
        ),
        "movement_pattern": "squat",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "hip-thrust": {
        "aliases": (
            "hip thrust",
            "хип траст",
            "ягодичный мост на скамье",
        ),
        "movement_pattern": "glute",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "bodyweight-glute-bridge": {
        "aliases": (
            "ягодичный мост без веса",
            "glute bridge",
            "bodyweight glute bridge",
        ),
        "movement_pattern": "glute",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "barbell-wrist-curl": {
        "aliases": (
            "сгибание запястий со штангой",
            "barbell wrist curl",
            "wrist curl",
        ),
        "movement_pattern": "wrist",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "barbell-wrist-extension": {
        "aliases": (
            "разгибание запястий со штангой",
            "обратные сгибания кистей",
            "barbell wrist extension",
            "reverse wrist curl",
        ),
        "movement_pattern": "wrist",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "dead-hang": {
        "aliases": (
            "вис на турнике",
            "пассивный вис",
            "dead hang",
        ),
        "movement_pattern": "grip",
        "machine_variant_tags": (),
        "execution_variant_tags": ("isometric",),
    },
    "rowing-machine": {
        "aliases": (
            "гребля тренажер",
            "гребля на тренажере",
            "гребной эргометр",
            "rowing machine",
            "row erg",
        ),
        "movement_pattern": "cardio_row",
        "machine_variant_tags": (),
        "execution_variant_tags": ("cyclic",),
    },
    "machine-row": {
        "aliases": (
            "гребная тяга",
            "горизонтальная тяга",
            "machine row",
            "горизонтальная тяга в тренажере",
        ),
        "movement_pattern": "row",
        "machine_variant_tags": ("selectorized",),
        "execution_variant_tags": ("bilateral",),
    },
    "treadmill-run": {
        "aliases": ("бег на дорожке", "treadmill run"),
        "movement_pattern": "running",
        "machine_variant_tags": (),
        "execution_variant_tags": ("cyclic",),
    },
    "assault-bike": {
        "aliases": (
            "аэробайк",
            "air bike",
            "assault bike",
            "воздушный велосипед",
        ),
        "movement_pattern": "cycling",
        "machine_variant_tags": (),
        "execution_variant_tags": ("cyclic",),
    },
    "recumbent-bike": {
        "aliases": (
            "велотренажер с горизонтальной посадкой",
            "лежачий велотренажер",
            "recumbent bike",
        ),
        "movement_pattern": "cycling",
        "machine_variant_tags": (),
        "execution_variant_tags": ("cyclic",),
    },
    "leg-press": {
        "aliases": (
            "leg press",
            "жим ногами широкая постановка",
            "жим ногами узкая постановка",
            "жим ногами стопы выше",
            "жим ногами стопы ниже",
        ),
        "movement_pattern": "squat",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "hack-squat": {
        "aliases": ("гакк", "hack squat", "гакк машина"),
        "movement_pattern": "squat",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "smith-squat": {
        "aliases": ("смит присед", "smith squat", "присед в машине смита"),
        "movement_pattern": "squat",
        "machine_variant_tags": ("smith",),
        "execution_variant_tags": ("bilateral",),
    },
    "leg-extension": {
        "aliases": ("разгибание ног в тренажере", "leg extension"),
        "movement_pattern": "leg_isolation",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "leg-curl": {
        "aliases": ("сгибание ног лежа", "lying leg curl"),
        "movement_pattern": "leg_isolation",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "seated-leg-curl": {
        "aliases": ("сгибание ног сидя", "seated leg curl"),
        "movement_pattern": "leg_isolation",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "standing-leg-curl": {
        "aliases": ("сгибание ног стоя", "standing leg curl"),
        "movement_pattern": "leg_isolation",
        "machine_variant_tags": (),
        "execution_variant_tags": ("unilateral",),
    },
    "hip-abduction": {
        "aliases": ("разведение ног в тренажере", "отведение бедер", "hip abduction machine"),
        "movement_pattern": "leg_isolation",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "hip-adduction": {
        "aliases": ("сведение ног в тренажере", "сведение бедер", "hip adduction machine"),
        "movement_pattern": "leg_isolation",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "standing-calf-raise": {
        "aliases": ("подъемы на носки в тренажере стоя", "standing calf raise machine"),
        "movement_pattern": "calf",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "seated-calf-raise": {
        "aliases": ("подъемы на носки в тренажере сидя", "seated calf raise machine"),
        "movement_pattern": "calf",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "calf-press": {
        "aliases": ("жим носками", "calf press machine"),
        "movement_pattern": "calf",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "pendulum-squat": {
        "aliases": (
            "маятниковый присед",
            "маятник в тренажере",
            "pendulum squat",
            "pendulum machine squat",
        ),
        "movement_pattern": "squat",
        "machine_variant_tags": ("plate_loaded", "lever"),
        "execution_variant_tags": ("bilateral",),
    },
    "plate-loaded-leg-press": {
        "aliases": (
            "жим ногами на блинах",
            "жим ногами с дисками",
            "plate loaded leg press",
            "рычажный жим ногами",
        ),
        "movement_pattern": "squat",
        "machine_variant_tags": ("plate_loaded",),
        "execution_variant_tags": ("bilateral",),
    },
    "unilateral-leg-press": {
        "aliases": (
            "жим одной ногой",
            "жим ногами одной ногой",
            "single leg press",
            "unilateral leg press",
        ),
        "movement_pattern": "squat",
        "machine_variant_tags": ("selectorized", "plate_loaded"),
        "execution_variant_tags": ("unilateral",),
    },
    "machine-hip-thrust": {
        "aliases": (
            "ягодичный тренажер",
            "glute drive",
            "machine hip thrust",
            "рычажный ягодичный мост",
        ),
        "movement_pattern": "glute",
        "machine_variant_tags": ("plate_loaded", "lever"),
        "execution_variant_tags": ("bilateral",),
    },
    "smith-split-squat": {
        "aliases": (
            "смит сплит",
            "сплит присед в смите",
            "smith split squat",
            "smith lunge",
            "выпады в смите",
        ),
        "movement_pattern": "lunge",
        "machine_variant_tags": ("smith",),
        "execution_variant_tags": ("unilateral",),
    },
    "machine-glute-kickback": {
        "aliases": (
            "разгибание бедра в тренажере",
            "ягодичный кикбэк в тренажере",
            "machine glute kickback",
            "glute kickback machine",
        ),
        "movement_pattern": "leg_isolation",
        "machine_variant_tags": ("selectorized", "lever"),
        "execution_variant_tags": ("unilateral",),
    },
    "v-squat-machine": {
        "aliases": (
            "v присед в тренажере",
            "рычажный v присед",
            "v squat",
            "v squat machine",
        ),
        "movement_pattern": "squat",
        "machine_variant_tags": ("plate_loaded", "lever"),
        "execution_variant_tags": ("bilateral",),
    },
    "reverse-hyperextension": {
        "aliases": (
            "обратная гиперэкстензия",
            "обратная гиперэкстензия в тренажере",
            "reverse hyper",
            "reverse hyperextension",
        ),
        "movement_pattern": "hinge",
        "machine_variant_tags": ("lever",),
        "execution_variant_tags": ("bilateral",),
    },
    "machine-incline-chest-press": {
        "aliases": (
            "наклонный жим в тренажере",
            "жим в тренажере на верх груди",
            "incline machine press",
            "incline chest press machine",
            "селекторный жим вверх",
        ),
        "movement_pattern": "chest_press",
        "machine_variant_tags": ("selectorized",),
        "execution_variant_tags": ("bilateral",),
    },
    "independent-lever-chest-press": {
        "aliases": (
            "жим в хаммере",
            "hammer press",
            "рычажный жим",
            "рычажный жим грудь",
            "на блинах грудь",
            "plate loaded chest press",
            "конвергентный жим",
            "iso lateral chest press",
        ),
        "movement_pattern": "chest_press",
        "machine_variant_tags": ("plate_loaded", "lever", "independent", "converging"),
        "execution_variant_tags": ("bilateral", "unilateral"),
    },
    "lever-high-row": {
        "aliases": (
            "верхняя рычажная тяга",
            "верхняя тяга хаммер",
            "high row",
            "high row hammer",
            "рычажная тяга сверху",
        ),
        "movement_pattern": "row",
        "machine_variant_tags": ("plate_loaded", "lever", "independent"),
        "execution_variant_tags": ("bilateral", "unilateral"),
    },
    "lever-low-row": {
        "aliases": (
            "нижняя рычажная тяга",
            "нижняя тяга хаммер",
            "low row",
            "low row hammer",
            "тяга на блинах снизу",
        ),
        "movement_pattern": "row",
        "machine_variant_tags": ("plate_loaded", "lever", "independent"),
        "execution_variant_tags": ("bilateral", "unilateral"),
    },
    "independent-lever-lat-pulldown": {
        "aliases": (
            "вертикальная рычажная тяга",
            "вертикальная тяга хаммер",
            "lever lat pulldown",
            "iso lateral pulldown",
            "рычажная тяга сверху вниз",
        ),
        "movement_pattern": "vertical_pull",
        "machine_variant_tags": ("plate_loaded", "lever", "independent"),
        "execution_variant_tags": ("bilateral", "unilateral"),
    },
    "machine-pullover": {
        "aliases": (
            "пуловер в тренажере",
            "machine pullover",
            "рычажный пуловер",
            "пуловер на блинах",
        ),
        "movement_pattern": "pullover",
        "machine_variant_tags": ("selectorized", "lever"),
        "execution_variant_tags": ("bilateral",),
    },
    "independent-lever-shoulder-press": {
        "aliases": (
            "жим плечами в хаммере",
            "рычажный жим плечами",
            "plate loaded shoulder press",
            "lever shoulder press",
            "iso lateral shoulder press",
            "жим над головой на блинах",
        ),
        "movement_pattern": "shoulder_press",
        "machine_variant_tags": ("plate_loaded", "lever", "independent"),
        "execution_variant_tags": ("bilateral", "unilateral"),
    },
    "machine-decline-chest-press": {
        "aliases": (
            "жим вниз в тренажере",
            "рычажный жим вниз",
            "decline machine press",
            "decline chest press machine",
        ),
        "movement_pattern": "chest_press",
        "machine_variant_tags": ("selectorized",),
        "execution_variant_tags": ("bilateral",),
    },
    "machine-triceps-extension": {
        "aliases": (
            "трицепс в тренажере",
            "разгибание локтей в тренажере",
            "machine triceps extension",
        ),
        "movement_pattern": "triceps",
        "machine_variant_tags": ("selectorized",),
        "execution_variant_tags": ("bilateral",),
    },
    "chest-supported-dumbbell-row": {
        "aliases": (
            "тяга гантелей лежа на наклонной скамье",
            "chest supported dumbbell row",
            "dumbbell incline row",
        ),
        "movement_pattern": "row",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "machine-biceps-curl": {
        "aliases": (
            "сгибание на скамье Скотта в тренажере",
            "сгибание рук на скамье Скотта в тренажере",
            "machine preacher curl",
        ),
        "movement_pattern": "arm_curl",
        "machine_variant_tags": ("selectorized",),
        "execution_variant_tags": ("bilateral",),
    },
    "floor-press": {
        "aliases": ("жим с пола", "floor press", "barbell floor press"),
        "movement_pattern": "chest_press",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "push-press": {
        "aliases": ("пуш пресс", "push press", "жим с толчком ногами"),
        "movement_pattern": "shoulder_press",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral", "multi_stage"),
    },
    "assisted-pull-ups": {
        "aliases": (
            "подтягивания с противовесом",
            "assisted pull up",
            "подтягивания в гравитроне",
            "гравитрон подтягивания",
        ),
        "movement_pattern": "vertical_pull",
        "machine_variant_tags": ("selectorized",),
        "execution_variant_tags": ("bilateral",),
    },
    "decline-crunch": {
        "aliases": (
            "скручивания на наклонной",
            "decline crunch",
            "decline bench crunch",
            "наклонные скручивания",
        ),
        "movement_pattern": "trunk_flexion",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "pistol-squat": {
        "aliases": ("пистолетик", "pistol squat", "one leg squat"),
        "movement_pattern": "squat",
        "machine_variant_tags": (),
        "execution_variant_tags": ("unilateral",),
    },
    "overhead-squat": {
        "aliases": ("присед над головой", "overhead squat", "оверхед сквот"),
        "movement_pattern": "squat",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "cable-external-rotation": {
        "aliases": (
            "внешняя ротация плеча",
            "cable external rotation",
            "ротация плеча в кроссовере",
            "наружная ротация",
        ),
        "movement_pattern": "shoulder_rotation",
        "machine_variant_tags": (),
        "execution_variant_tags": ("unilateral",),
    },
    "hanging-knee-raise": {
        "aliases": (
            "подъем коленей в висе",
            "hanging knee raise",
            "hanging knee raises",
            "подъем колен в висе",
        ),
        "movement_pattern": "trunk_flexion",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "trap-bar-deadlift": {
        "aliases": (
            "тяга трэп-гриф",
            "тяга трап-гриф",
            "trap bar deadlift",
            "hex bar deadlift",
        ),
        "movement_pattern": "hinge",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "safety-bar-squat": {
        "aliases": (
            "safety bar squat",
            "safety squat",
            "приседания с safety-грифом",
            "присед в safety bar",
        ),
        "movement_pattern": "squat",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "negative-pull-ups": {
        "aliases": (
            "негативные подтягивания",
            "negative pull up",
            "negative pull-ups",
            "эксцентрические подтягивания",
        ),
        "movement_pattern": "vertical_pull",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "scapular-pull-ups": {
        "aliases": (
            "лопаточные подтягивания",
            "scapular pull up",
            "scap pull ups",
        ),
        "movement_pattern": "vertical_pull",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "muscle-ups": {
        "aliases": (
            "выход силой",
            "muscle up",
            "muscle ups",
            "подтягивание с выходом",
        ),
        "movement_pattern": "vertical_pull",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral", "multi_stage"),
    },
    "assisted-dips": {
        "aliases": (
            "отжимания с противовесом",
            "assisted dip",
            "гравитрон брусья",
            "брусья с противовесом",
        ),
        "movement_pattern": "chest_press",
        "machine_variant_tags": ("selectorized",),
        "execution_variant_tags": ("bilateral",),
    },
    "machine-seated-crunch": {
        "aliases": (
            "скручивания в тренажере",
            "machine crunch",
            "seated machine crunch",
            "пресс в тренажере сидя",
        ),
        "movement_pattern": "trunk_flexion",
        "machine_variant_tags": ("selectorized",),
        "execution_variant_tags": ("bilateral",),
    },
    "band-pull-apart": {
        "aliases": (
            "разведения резинки",
            "band pull apart",
            "разведение эспандера",
        ),
        "movement_pattern": "shoulder_rotation",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "db-squat": {
        "aliases": ("приседания с гантелями", "dumbbell squat", "db squat"),
        "movement_pattern": "squat",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "kettlebell-overhead-carry": {
        "aliases": (
            "переноска гири над головой",
            "kettlebell overhead carry",
            "overhead kettlebell carry",
            "марш над головой с гирей",
        ),
        "movement_pattern": "carry",
        "machine_variant_tags": (),
        "execution_variant_tags": ("cyclic",),
    },
    "dragon-flag": {
        "aliases": ("драконий флаг", "dragon flag", "dragon flags"),
        "movement_pattern": "anti_extension",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "jackknife-sit-up": {
        "aliases": ("складка лежа", "jackknife sit up", "jackknife", "v-up"),
        "movement_pattern": "trunk_flexion",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "l-sit": {
        "aliases": ("l-sit", "уголок на брусьях", "уголок"),
        "movement_pattern": "anti_extension",
        "machine_variant_tags": (),
        "execution_variant_tags": ("isometric",),
    },
    "clean-and-jerk": {
        "aliases": (
            "взятие на грудь и толчок",
            "clean and jerk",
            "clean & jerk",
            "взятие штанги и толчок",
        ),
        "movement_pattern": "olympic_lift",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral", "multi_stage"),
    },
    "hang-power-clean": {
        "aliases": (
            "взятие с виса",
            "hang power clean",
            "power clean from hang",
            "взятие штанги с виса",
        ),
        "movement_pattern": "olympic_lift",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral", "multi_stage"),
    },
    "wrist-roller": {
        "aliases": (
            "ролик для предплечий",
            "wrist roller",
            "forearm roller",
            "ролик кистевой",
        ),
        "movement_pattern": "wrist",
        "machine_variant_tags": (),
        "execution_variant_tags": ("bilateral",),
    },
    "rope-climb": {
        "aliases": (
            "лазание по канату",
            "rope climb",
            "подъем по канату",
            "канат лазание",
        ),
        "movement_pattern": "vertical_pull",
        "machine_variant_tags": (),
        "execution_variant_tags": ("cyclic",),
    },
}


# Reviewed movement vocabulary for every canonical row. The seed remains the
# source of identity, muscles, equipment, difficulty and metric; this map only
# records the normalized movement axis used by search, alternatives and future
# catalog filters.
REVIEWED_MOVEMENT_PATTERN_SLUGS: dict[str, tuple[str, ...]] = {
    "chest_press": (
        "bench-press",
        "incline-bench-press",
        "decline-bench-press",
        "close-grip-bench-press",
        "dumbbell-bench-press",
        "incline-dumbbell-press",
        "decline-dumbbell-press",
        "machine-chest-press",
        "machine-incline-chest-press",
        "independent-lever-chest-press",
        "machine-decline-chest-press",
        "smith-bench-press",
        "push-up",
        "weighted-dip",
        "chest-dip",
        "floor-press",
        "assisted-dips",
    ),
    "chest_fly": (
        "dumbbell-fly",
        "incline-dumbbell-fly",
        "cable-fly",
        "low-to-high-cable-fly",
        "pec-deck",
    ),
    "pullover": ("dumbbell-pullover", "straight-arm-pulldown", "machine-pullover"),
    "vertical_pull": (
        "pull-up",
        "chin-up",
        "lat-pulldown",
        "reverse-grip-lat-pulldown",
        "close-grip-lat-pulldown",
        "independent-lever-lat-pulldown",
        "assisted-pull-ups",
        "negative-pull-ups",
        "scapular-pull-ups",
        "muscle-ups",
        "rope-climb",
    ),
    "row": (
        "barbell-row",
        "pendlay-row",
        "t-bar-row",
        "one-arm-dumbbell-row",
        "chest-supported-row",
        "seated-cable-row",
        "machine-row",
        "lever-high-row",
        "lever-low-row",
        "chest-supported-dumbbell-row",
        "inverted-row",
        "meadows-row",
        "cable-row-one-arm",
        "face-pull",
        "upright-row",
        "renegade-row",
    ),
    "hinge": (
        "deadlift",
        "rack-pull",
        "hyperextension",
        "good-morning",
        "romanian-deadlift",
        "stiff-leg-deadlift",
        "single-leg-rdl",
        "glute-ham-raise",
        "reverse-hyperextension",
        "cable-pull-through",
        "kettlebell-swing",
        "sumo-deadlift",
        "trap-bar-deadlift",
    ),
    "squat": (
        "squat",
        "front-squat",
        "hack-squat",
        "smith-squat",
        "goblet-squat",
        "bodyweight-squat",
        "belt-squat",
        "leg-press",
        "pendulum-squat",
        "plate-loaded-leg-press",
        "unilateral-leg-press",
        "v-squat-machine",
        "sissy-squat",
        "wall-sit",
        "kettlebell-goblet-squat",
        "pistol-squat",
        "overhead-squat",
        "safety-bar-squat",
        "db-squat",
    ),
    "lunge": (
        "lunge",
        "walking-lunge",
        "reverse-lunge",
        "bulgarian-split-squat",
        "split-squat",
        "smith-split-squat",
        "step-up",
    ),
    "leg_isolation": (
        "leg-extension",
        "leg-curl",
        "seated-leg-curl",
        "standing-leg-curl",
        "nordic-curl",
        "hip-abduction",
        "hip-adduction",
        "cable-kickback",
        "machine-glute-kickback",
    ),
    "glute": (
        "hip-thrust",
        "single-leg-hip-thrust",
        "bodyweight-glute-bridge",
        "barbell-glute-bridge",
        "machine-hip-thrust",
    ),
    "shoulder_press": (
        "overhead-press",
        "seated-dumbbell-press",
        "arnold-press",
        "machine-shoulder-press",
        "independent-lever-shoulder-press",
        "smith-shoulder-press",
        "landmine-press",
        "push-press",
    ),
    "shoulder_raise": (
        "dumbbell-lateral-raise",
        "cable-lateral-raise",
        "machine-lateral-raise",
        "dumbbell-front-raise",
        "rear-delt-fly",
        "reverse-pec-deck",
        "barbell-shrug",
        "dumbbell-shrug",
        "y-raise",
    ),
    "shoulder_rotation": ("cable-external-rotation", "band-pull-apart"),
    "arm_curl": (
        "barbell-curl",
        "ez-bar-curl",
        "dumbbell-curl",
        "hammer-curl",
        "incline-dumbbell-curl",
        "preacher-curl",
        "cable-curl",
        "concentration-curl",
        "reverse-curl",
        "spider-curl",
        "machine-biceps-curl",
    ),
    "triceps": (
        "skull-crusher",
        "rope-pushdown",
        "cable-pushdown",
        "overhead-triceps-extension",
        "dumbbell-overhead-extension",
        "lying-dumbbell-triceps-extension",
        "bench-dip",
        "triceps-kickback",
        "machine-dip",
        "machine-triceps-extension",
        "single-arm-cable-triceps-extension",
    ),
    "calf": (
        "standing-calf-raise",
        "seated-calf-raise",
        "donkey-calf-raise",
        "calf-press",
        "single-leg-calf-raise",
    ),
    "wrist": ("barbell-wrist-curl", "barbell-wrist-extension", "wrist-roller"),
    "grip": ("dead-hang",),
    "trunk_flexion": (
        "crunch",
        "reverse-crunch",
        "cable-crunch",
        "hanging-leg-raise",
        "captain-chair-leg-raise",
        "decline-crunch",
        "hanging-knee-raise",
        "machine-seated-crunch",
        "jackknife-sit-up",
    ),
    "anti_extension": (
        "plank",
        "hollow-hold",
        "dead-bug",
        "bird-dog",
        "ab-wheel",
        "dragon-flag",
        "l-sit",
    ),
    "anti_rotation": ("side-plank", "pallof-press"),
    "trunk_rotation": ("russian-twist", "woodchopper"),
    "conditioning": (
        "mountain-climber",
        "burpee",
        "box-jump",
        "jump-rope",
        "elliptical-trainer",
        "outdoor-walk",
        "treadmill-walk",
        "stair-climber",
        "swimming",
        "ski-erg",
        "battle-rope",
        "sled-push",
        "sled-pull",
        "medicine-ball-slam",
        "wall-ball",
        "turkish-get-up",
        "bear-crawl",
    ),
    "olympic_lift": (
        "thruster",
        "kettlebell-clean",
        "kettlebell-snatch",
        "clean-and-jerk",
        "hang-power-clean",
    ),
    "carry": ("farmer-walk", "suitcase-carry", "kettlebell-overhead-carry"),
    "cardio_row": ("rowing-machine",),
    "running": ("treadmill-run", "outdoor-run"),
    "cycling": ("assault-bike", "outdoor-cycling", "stationary-bike", "recumbent-bike"),
}
REVIEWED_MOVEMENT_PATTERN_BY_SLUG = {
    slug: movement_pattern
    for movement_pattern, slugs in REVIEWED_MOVEMENT_PATTERN_SLUGS.items()
    for slug in slugs
}


MEDIA_STATE_BY_SLUG: dict[str, ExerciseMediaState] = {
    **{
        slug: {
            "state": "repdb_phased",
            "source_slug": slug,
            "phases": ("start", "peak"),
        }
        for slug in (
            "floor-press",
            "push-press",
            "assisted-pull-ups",
            "decline-crunch",
            "pistol-squat",
            "overhead-squat",
            "cable-external-rotation",
            "hanging-knee-raise",
            "negative-pull-ups",
            "scapular-pull-ups",
            "muscle-ups",
            "assisted-dips",
            "machine-seated-crunch",
            "band-pull-apart",
            "db-squat",
            "dragon-flag",
            "jackknife-sit-up",
            "clean-and-jerk",
            "hang-power-clean",
            "wrist-roller",
        )
    },
    "trap-bar-deadlift": {
        "state": "repdb_phased",
        "source_slug": "hex-bar-deadlift",
        "phases": ("start", "peak"),
    },
    **{
        slug: {
            "state": "repdb_single_static",
            "source_slug": slug,
            "phases": ("main",),
        }
        for slug in ("kettlebell-overhead-carry", "l-sit", "rope-climb")
    },
    "safety-bar-squat": {
        "state": "repdb_source_gap",
        "source_slug": None,
        "phases": (),
    },
}


ITEM_GUIDE_CONTENT: dict[str, ExerciseGuideContent] = {
    "pendulum-squat": {
        "steps": [
            "Встань на платформу, расположи плечи под упорами и выбери устойчивую постановку стоп, предусмотренную тренажёром.",
            "Сними рычаг со стопоров и плавно согни тазобедренные и коленные суставы до глубины, на которой стопы и корпус сохраняют опору.",
            "Надави всей стопой на платформу и поднимись по дуге тренажёра без резкого выпрямления коленей.",
        ],
        "breathing": "Вдох перед опусканием, выдох после прохождения тяжёлой части подъёма.",
        "mistakes": [
            "Пятки отрываются от платформы",
            "Колени заметно смещаются внутрь относительно стоп",
            "Отскок из нижнего положения вместо контролируемого разворота",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Икры"],
    },
    "plate-loaded-leg-press": {
        "steps": [
            "Настрой спинку и сядь так, чтобы таз и спина оставались на опоре, затем поставь стопы на платформу.",
            "Сними платформу со стопоров и опусти её до доступной амплитуды без отрыва таза; положение стоп можно менять только сохраняя устойчивую опору.",
            "Выжми платформу всей стопой и остановись до жёсткой блокировки коленей, затем верни стопоры после последнего повтора.",
        ],
        "breathing": "Вдох при контролируемом опускании платформы, выдох после прохождения тяжёлой части жима.",
        "mistakes": [
            "Таз отрывается от спинки в нижней точке",
            "Пятки теряют контакт с платформой",
            "Платформа резко опускается на ограничители",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Икры"],
    },
    "unilateral-leg-press": {
        "steps": [
            "Сядь по центру спинки, поставь одну стопу на платформу, а свободную ногу убери в предусмотренное тренажёром устойчивое положение.",
            "Опусти платформу рабочей ногой без поворота таза, направляя колено по линии стопы.",
            "Выжми платформу всей стопой без резкой блокировки колена и повтори тот же setup для другой стороны.",
        ],
        "breathing": "Вдох при опускании платформы, выдох после прохождения тяжёлой части жима.",
        "mistakes": [
            "Таз разворачивается или смещается на сиденье",
            "Колено уходит в сторону от линии стопы",
            "Свободная нога помогает двигать платформу",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Икры"],
    },
    "machine-hip-thrust": {
        "steps": [
            "Настрой опору и ремень или подушку по инструкции тренажёра, зафиксируй таз и поставь стопы устойчиво.",
            "Разогни тазобедренные суставы и подними рычаг до положения, где корпус и бёдра образуют почти прямую линию без прогиба поясницы.",
            "Плавно опусти таз, сохраняя контакт с опорами и натяжение ремня или подушки.",
        ],
        "breathing": "Вдох при опускании таза, выдох во время разгибания бёдер.",
        "mistakes": [
            "Движение завершается прогибом поясницы вместо разгибания бёдер",
            "Стопы сдвигаются или теряют полный контакт с опорой",
            "Рычаг резко опускается на ограничитель",
        ],
        "secondary": ["Бицепс бедра", "Кор"],
    },
    "smith-split-squat": {
        "steps": [
            "Установи страховочные упоры, расположи гриф на верхней части спины и прими устойчивую разножку под направляющими.",
            "Опустись вниз, сгибая обе ноги и сохраняя переднюю стопу полностью на полу, а корпус — устойчивым под грифом.",
            "Оттолкнись передней ногой и поднимись без поворота таза; перед сменой стороны надёжно верни гриф на фиксаторы.",
        ],
        "breathing": "Вдох перед опусканием, выдох после прохождения тяжёлой части подъёма.",
        "mistakes": [
            "Слишком узкая разножка не даёт устойчивой опоры",
            "Пятка передней ноги отрывается от пола",
            "Корпус смещается вперёд или в сторону относительно грифа",
        ],
        "secondary": ["Квадрицепс", "Ягодицы", "Бицепс бедра", "Кор"],
    },
    "machine-glute-kickback": {
        "steps": [
            "Настрой подушку и опоры так, чтобы рабочее бедро двигалось свободно, а таз и корпус оставались зафиксированы.",
            "Отведи бедро назад по траектории тренажёра без разворота таза и без дополнительного прогиба поясницы.",
            "Плавно верни рычаг до исходного положения, сохраняя опору корпуса.",
        ],
        "breathing": "Выдох при отведении бедра назад, вдох при контролируемом возврате.",
        "mistakes": [
            "Раскачивание корпусом для разгона рычага",
            "Разворот таза вслед за рабочей ногой",
            "Слишком большая амплитуда за счёт прогиба поясницы",
        ],
        "secondary": ["Бицепс бедра", "Кор"],
    },
    "v-squat-machine": {
        "steps": [
            "Расположи плечи под упорами, прижми таз и спину к наклонной опоре и поставь стопы устойчиво на платформу.",
            "Сними рычаг со стопоров и опустись по заданной траектории, сохраняя контакт корпуса с опорой и колени по линии стоп.",
            "Надави всей стопой и поднимись без резкой блокировки коленей, затем верни стопоры после подхода.",
        ],
        "breathing": "Вдох перед опусканием, выдох после прохождения тяжёлой части подъёма.",
        "mistakes": [
            "Таз отрывается от наклонной опоры",
            "Колени смещаются внутрь относительно стоп",
            "Резкий разворот движения на ограничителях",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Икры"],
    },
    "reverse-hyperextension": {
        "steps": [
            "Расположи таз у края опоры, зафиксируй корпус и возьмись за рукояти, оставив ноги свободно опущенными.",
            "Подними ноги разгибанием в тазобедренных суставах примерно до линии корпуса без резкого маха и чрезмерного прогиба поясницы.",
            "Плавно опусти ноги, сохраняя таз и верх тела на опоре.",
        ],
        "breathing": "Выдох при подъёме ног, вдох при контролируемом опускании.",
        "mistakes": [
            "Разгон ног раскачиванием",
            "Подъём выше доступной амплитуды за счёт прогиба поясницы",
            "Таз или корпус теряют устойчивый контакт с опорой",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Разгибатели спины", "Кор"],
    },
    "machine-incline-chest-press": {
        "steps": [
            "Настрой сиденье так, чтобы рукояти начинали движение у верхней части груди, и прижми спину к опоре.",
            "Выжми рукояти вперёд и немного вверх, сохраняя запястья над локтями и плечи опущенными.",
            "Плавно верни рычаги до комфортного положения локтей, не ударяя весовым стеком.",
        ],
        "breathing": "Вдох при возврате рукоятей, выдох после прохождения тяжёлой части жима.",
        "mistakes": [
            "Сиденье настроено слишком высоко или низко",
            "Плечи отрываются от спинки",
            "Весовой стек ударяется между повторами",
        ],
        "secondary": ["Трицепс", "Передняя дельта"],
    },
    "independent-lever-chest-press": {
        "steps": [
            "Настрой сиденье, прижми спину и лопатки к опоре и возьмись за независимые рукояти на уровне середины груди.",
            "Выжми оба рычага вперёд; при одностороннем варианте не разворачивай корпус вслед за рабочей рукой.",
            "Верни рукояти под контролем, сохраняя одинаковую амплитуду справа и слева.",
        ],
        "breathing": "Вдох при возврате рычагов, выдох после прохождения тяжёлой части жима.",
        "mistakes": [
            "Поворот корпуса при независимой работе рук",
            "Неравная амплитуда справа и слева",
            "Резкое опускание дисков на упоры",
        ],
        "secondary": ["Трицепс", "Передняя дельта"],
    },
    "lever-high-row": {
        "steps": [
            "Настрой сиденье и грудной упор так, чтобы дотянуться до верхних рукоятей без отрыва груди.",
            "Потяни локти вниз и назад, сохраняя грудь на опоре и запястья нейтральными.",
            "Плавно выпрями руки вверх-вперёд, не позволяя плечам резко тянуться к ушам.",
        ],
        "breathing": "Выдох во время тяги, вдох при контролируемом возврате рычагов.",
        "mistakes": [
            "Отрыв груди от опоры",
            "Рывок корпусом вместо тяги локтями",
            "Неравная траектория независимых рычагов",
        ],
        "secondary": ["Бицепс", "Задняя дельта", "Предплечья"],
    },
    "lever-low-row": {
        "steps": [
            "Настрой грудной упор и возьмись за нижние рукояти, сохраняя нейтральную спину и почти прямые руки.",
            "Потяни локти назад к талии, не отрывая грудь от опоры и не поднимая плечи.",
            "Верни рычаги вперёд-вниз под контролем, сохраняя устойчивое положение корпуса.",
        ],
        "breathing": "Выдох во время тяги к корпусу, вдох при возвращении рычагов.",
        "mistakes": [
            "Отталкивание грудью от опоры",
            "Локти уходят слишком высоко",
            "Резкий бросок рычагов вперёд",
        ],
        "secondary": ["Бицепс", "Задняя дельта", "Предплечья"],
    },
    "independent-lever-lat-pulldown": {
        "steps": [
            "Настрой сиденье и упор для бёдер, затем возьмись за независимые верхние рукояти.",
            "Опусти локти к бокам, сохраняя корпус устойчивым; при работе одной рукой не наклоняйся в сторону.",
            "Плавно выпрями руки вверх, не позволяя рычагам резко уйти на упоры.",
        ],
        "breathing": "Выдох при опускании рычагов, вдох при возвращении рук вверх.",
        "mistakes": [
            "Сильный отклон корпуса назад",
            "Поворот корпуса при односторонней тяге",
            "Резкое выпрямление рук под нагрузкой",
        ],
        "secondary": ["Бицепс", "Предплечья", "Задняя дельта"],
    },
    "machine-pullover": {
        "steps": [
            "Настрой сиденье и локтевые упоры так, чтобы плечи двигались свободно, а спина оставалась на опоре.",
            "Опусти рычаг дугой к корпусу, сохраняя угол в локтях и не подавая грудную клетку вперёд.",
            "Верни рычаг вверх до комфортного растяжения без отрыва таза и прогиба поясницы.",
        ],
        "breathing": "Выдох при опускании рычага к корпусу, вдох при контролируемом возврате.",
        "mistakes": [
            "Разгибание локтей вместо движения плечом",
            "Избыточный прогиб поясницы",
            "Слишком глубокий возврат за доступную амплитуду плеч",
        ],
        "secondary": ["Грудь", "Трицепс", "Кор"],
    },
    "independent-lever-shoulder-press": {
        "steps": [
            "Настрой сиденье так, чтобы рукояти были около плеч, и прижми спину к опоре.",
            "Выжми независимые рычаги вверх; при работе одной рукой сохраняй рёбра и таз неподвижными.",
            "Опусти рукояти под контролем до комфортного положения локтей без удара дисков об упоры.",
        ],
        "breathing": "Вдох перед жимом, выдох после прохождения тяжёлой части движения.",
        "mistakes": [
            "Сильный прогиб поясницы",
            "Наклон корпуса при одностороннем жиме",
            "Неравная амплитуда независимых рычагов",
        ],
        "secondary": ["Трицепс", "Передняя дельта", "Кор"],
    },
    "machine-decline-chest-press": {
        "steps": [
            "Настрой сиденье так, чтобы рукояти начинали движение у нижней части груди, и сохрани опору спины.",
            "Выжми рукояти вперёд и немного вниз, не поднимая плечи и не отрывая корпус от спинки.",
            "Плавно верни вес до комфортного положения локтей, не ударяя стеком.",
        ],
        "breathing": "Вдох при возврате рукоятей, выдох после прохождения тяжёлой части жима.",
        "mistakes": [
            "Рукояти находятся слишком высоко относительно груди",
            "Плечи подаются вперёд в конце жима",
            "Резкий возврат веса на упоры",
        ],
        "secondary": ["Трицепс", "Передняя дельта"],
    },
    "machine-triceps-extension": {
        "steps": [
            "Настрой сиденье и локтевые упоры так, чтобы ось вращения тренажёра совпадала с локтями.",
            "Разогни локти, сохраняя плечи на опоре и запястья в нейтральном положении.",
            "Плавно согни руки до доступной амплитуды, не позволяя весовому стеку ударяться.",
        ],
        "breathing": "Выдох при разгибании рук, вдох при контролируемом сгибании локтей.",
        "mistakes": [
            "Локти смещены относительно оси тренажёра",
            "Плечи отрываются от упоров",
            "Резкое возвращение веса",
        ],
        "secondary": ["Предплечья", "Кор"],
    },
    "chest-supported-dumbbell-row": {
        "steps": [
            "Ляг грудью на наклонную скамью, упрись стопами в пол и опусти гантели на прямых руках.",
            "Потяни локти назад вдоль корпуса, сохраняя грудь на скамье и нейтральные запястья.",
            "Плавно опусти гантели до полного контролируемого выпрямления рук.",
        ],
        "breathing": "Выдох во время тяги, вдох при опускании гантелей.",
        "mistakes": [
            "Отрыв груди от скамьи",
            "Плечи тянутся к ушам",
            "Удар гантелей друг о друга или о скамью",
        ],
        "secondary": ["Бицепс", "Задняя дельта", "Предплечья"],
    },
    "bodyweight-squat": {
        "steps": [
            "Поставь стопы устойчиво, выпрямись и направь колени по линии носков.",
            "Отведи таз назад и присядь до глубины, на которой стопы остаются на полу, а корпус — под контролем.",
            "Надави всей стопой на пол и встань без рывка и жёсткой блокировки коленей.",
        ],
        "breathing": "Вдох перед опусканием, выдох после прохождения тяжёлой части подъёма.",
        "mistakes": [
            "Пятки отрываются от пола",
            "Колени заметно смещаются внутрь",
            "Падение вниз без контролируемого разворота",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Икры", "Кор"],
    },
    "bodyweight-glute-bridge": {
        "steps": [
            "Ляг на спину, согни колени и поставь стопы на пол примерно на ширине таза.",
            "Надави стопами в пол и подними таз, разгибая бёдра без чрезмерного прогиба поясницы.",
            "Задержись в верхнем положении и плавно опусти таз до пола.",
        ],
        "breathing": "Вдох при опускании таза, выдох во время подъёма.",
        "mistakes": [
            "Подъём за счёт прогиба поясницы",
            "Стопы стоят слишком далеко и скользят",
            "Колени расходятся или смещаются внутрь",
        ],
        "secondary": ["Бицепс бедра", "Кор"],
    },
    "barbell-wrist-curl": {
        "steps": [
            "Возьми лёгкую штангу ладонями вверх и положи предплечья на бёдра или скамью, оставив кисти за краем опоры.",
            "Согни кисти вверх, не отрывая предплечья и не помогая движением локтей.",
            "Плавно опусти гриф до доступного разгибания запястий, сохраняя хват.",
        ],
        "breathing": "Выдох при сгибании кистей, вдох при контролируемом опускании.",
        "mistakes": [
            "Слишком тяжёлый вес сокращает амплитуду",
            "Предплечья отрываются от опоры",
            "Гриф перекатывается к кончикам пальцев без контроля",
        ],
        "secondary": ["Хват"],
    },
    "barbell-wrist-extension": {
        "steps": [
            "Возьми лёгкую штангу ладонями вниз и положи предплечья на бёдра или скамью, оставив кисти за краем опоры.",
            "Подними тыльную сторону кистей вверх, сохраняя предплечья неподвижными.",
            "Плавно опусти гриф до доступного сгибания запястий без рывка.",
        ],
        "breathing": "Выдох при разгибании кистей, вдох при контролируемом опускании.",
        "mistakes": [
            "Движение выполняется локтями вместо запястий",
            "Резкое опускание грифа",
            "Слишком тяжёлый вес не позволяет удержать кисти ровно",
        ],
        "secondary": ["Хват"],
    },
    "dead-hang": {
        "steps": [
            "Возьмись за перекладину устойчивым хватом и убери ноги с опоры без раскачивания.",
            "Держи корпус спокойно, не подтягивайся и сохраняй контролируемое положение плеч без боли.",
            "Заверши подход до потери хвата и верни ноги на опору, а не спрыгивай с высоты.",
        ],
        "breathing": "Дыши спокойно и не задерживай дыхание во время удержания.",
        "mistakes": [
            "Раскачивание корпуса",
            "Продолжение удержания после потери контроля хвата",
            "Спрыгивание без устойчивой опоры под ногами",
        ],
        "secondary": ["Предплечья", "Спина", "Плечи", "Кор"],
    },
    "recumbent-bike": {
        "steps": [
            "Настрой сиденье так, чтобы в дальней точке педали колено оставалось слегка согнутым, а спина сохраняла опору.",
            "Поставь стопы по центру педалей и крути их плавно, удерживая колени по линии стоп.",
            "Подбирай сопротивление под контролируемый ритм и останови педали перед тем, как убрать ноги.",
        ],
        "breathing": "Дыши ровно и свободно, не задерживая дыхание при росте сопротивления.",
        "mistakes": [
            "Сиденье слишком близко или далеко от педалей",
            "Колени заваливаются внутрь",
            "Рывки педалями вместо ровного цикла",
        ],
        "secondary": ["Квадрицепс", "Ягодицы", "Бицепс бедра", "Икры"],
    },
    "floor-press": {
        "steps": [
            "Ляг на пол под штангой, поставь стопы устойчиво и сведи лопатки, оставив локти свободными от жёсткого упора в пол.",
            "Опусти гриф к нижней части груди до мягкого касания трицепсами пола, сохраняя запястья над локтями.",
            "Выжми гриф вверх по устойчивой траектории и не теряй контакт стоп и лопаток с опорой.",
        ],
        "breathing": "Вдох перед опусканием, выдох после прохождения тяжёлой части жима.",
        "mistakes": [
            "Локти резко ударяются о пол",
            "Запястья заваливаются назад",
            "Гриф опускается к шее вместо нижней части груди",
        ],
        "secondary": ["Трицепс", "Передняя дельта"],
        "safety_notes": [
            "Используй страховочные упоры или помощника, если штанга не может свободно покинуть стойки."
        ],
    },
    "push-press": {
        "steps": [
            "Положи штангу на переднюю часть плеч, поставь стопы устойчиво и сохрани вертикальный корпус.",
            "Сделай короткое сгибание коленей и резко выпрями ноги, передавая импульс штанге без наклона корпуса назад.",
            "Дожми штангу над головой, зафиксируй корпус и верни её на плечи под контролем.",
        ],
        "breathing": "Вдох перед подседом, выдох во время толчка и дожима.",
        "mistakes": [
            "Глубокий присед превращает движение в трастер",
            "Корпус отклоняется назад под штангой",
            "Штанга опускается на плечи без контроля",
        ],
        "secondary": ["Трицепс", "Квадрицепс", "Кор"],
    },
    "assisted-pull-ups": {
        "steps": [
            "Выбери противовес, проверь платформу и возьмись за перекладину хватом, который позволяет сохранить контроль.",
            "Опусти лопатки, подтяни локти вниз и подними грудь к перекладине без раскачивания.",
            "Плавно выпрями руки и вернись на платформу только после полной остановки движения.",
        ],
        "breathing": "Выдох во время тяги, вдох при контролируемом возвращении вниз.",
        "mistakes": [
            "Платформа подбрасывается из-за рывка",
            "Корпус раскачивается для набора высоты",
            "Вес сбрасывается на стек в нижней точке",
        ],
        "secondary": ["Бицепс", "Предплечья", "Задняя дельта"],
        "safety_notes": [
            "Проверь фиксацию противовеса и не спрыгивай с платформы до полной остановки тренажёра."
        ],
    },
    "decline-crunch": {
        "steps": [
            "Зафиксируй стопы на наклонной скамье и ляг так, чтобы таз и спина сохраняли устойчивый контакт с опорой.",
            "Сверни грудную клетку к тазу, поднимая лопатки без тяги руками за голову.",
            "Плавно вернись вниз до исходного положения, сохраняя напряжение корпуса.",
        ],
        "breathing": "Выдох при подъёме корпуса, вдох при контролируемом опускании.",
        "mistakes": [
            "Стопы соскальзывают с фиксаторов",
            "Корпус поднимается рывком бёдер",
            "Шея тянется руками вперёд",
        ],
        "secondary": ["Кор", "Косые мышцы"],
        "safety_notes": [
            "Перед подходом проверь фиксаторы ног и настрой наклон под контролируемую амплитуду."
        ],
    },
    "pistol-squat": {
        "steps": [
            "Перенеси вес на одну стопу, вытяни вторую ногу вперёд и найди устойчивое положение корпуса.",
            "Опустись на рабочей ноге, направляя колено по линии стопы и удерживая таз под контролем.",
            "Надави всей стопой в пол и поднимись без рывка, затем повтори на другой стороне.",
        ],
        "breathing": "Вдох перед опусканием, выдох после прохождения нижней точки подъёма.",
        "mistakes": [
            "Колено заваливается внутрь",
            "Пятка теряет контакт с полом",
            "Свободная нога или корпус раскачиваются",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Икры", "Кор"],
        "safety_notes": [
            "Начни с опоры или частичной амплитуды, если без неё теряется равновесие."
        ],
    },
    "overhead-squat": {
        "steps": [
            "Возьми штангу широким хватом над головой и зафиксируй рёбра, таз и стопы в устойчивом положении.",
            "Опустись в присед, сохраняя гриф над серединой стоп и колени по линии носков.",
            "Надави всей стопой и встань, не позволяя штанге уходить вперёд или назад.",
        ],
        "breathing": "Вдох перед опусканием, выдох после прохождения тяжёлой части подъёма.",
        "mistakes": [
            "Гриф уходит за линию стоп",
            "Локти сгибаются в нижней точке",
            "Таз и грудная клетка теряют устойчивое положение",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Плечи", "Кор"],
        "safety_notes": [
            "Начинай с пустого грифа и освободи пространство над головой до снятия штанги со стоек."
        ],
    },
    "cable-external-rotation": {
        "steps": [
            "Установи рукоять на высоте локтя, встань боком к блоку и прижми локоть к корпусу.",
            "Поверни предплечье наружу в небольшой контролируемой амплитуде, не разворачивая плечо и корпус.",
            "Плавно верни рукоять к животу, сохраняя локоть на месте.",
        ],
        "breathing": "Дыши свободно; выдох при вращении наружу, вдох при возврате.",
        "mistakes": [
            "Локоть отрывается от корпуса",
            "Корпус разворачивается вместо движения предплечья",
            "Вес тянет руку обратно рывком",
        ],
        "secondary": ["Задняя дельта", "Кор"],
        "safety_notes": [
            "Используй небольшой вес и остановись в точке, где движение остаётся плавным и без рывка."
        ],
    },
    "hanging-knee-raise": {
        "steps": [
            "Возьмись за перекладину устойчивым хватом, убери ноги с опоры и останови раскачивание.",
            "Подними колени к корпусу за счёт сгибания таза, сохраняя плечи опущенными и корпус собранным.",
            "Плавно опусти ноги до исходного положения без броска и нового замаха.",
        ],
        "breathing": "Выдох при подъёме коленей, вдох при контролируемом опускании.",
        "mistakes": [
            "Подъём выполняется махом",
            "Плечи поднимаются к ушам",
            "Ноги резко падают вниз",
        ],
        "secondary": ["Косые мышцы", "Предплечья"],
        "safety_notes": [
            "Проверь перекладину и хват, а завершай подход с устойчивой опорой под ногами."
        ],
    },
    "trap-bar-deadlift": {
        "steps": [
            "Встань внутри трэп-грифа, поставь стопы по центру рукоятей и опусти таз в устойчивую стартовую позицию.",
            "Зафиксируй корпус, надави стопами в пол и подними гриф, сохраняя плечи и таз в согласованном движении.",
            "Отведи таз назад и плавно опусти гриф на пол, не бросая его в конце повтора.",
        ],
        "breathing": "Вдох и фиксация корпуса перед подъёмом, выдох после прохождения тяжёлой части.",
        "mistakes": [
            "Таз резко поднимается раньше плеч",
            "Спина теряет нейтральное положение",
            "Гриф опускается ударом о пол",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Разгибатели спины", "Хват"],
        "safety_notes": [
            "Проверь замки и свободное пространство вокруг трэп-грифа перед каждым подходом."
        ],
    },
    "safety-bar-squat": {
        "steps": [
            "Настрой стойки и страховки, расположи padded yoke на плечах и возьмись за передние рукояти.",
            "Опустись в присед, сохраняя стопы устойчивыми, корпус собранным и колени по линии носков.",
            "Надави всей стопой и встань без рывка, затем верни гриф на стойки под контролем.",
        ],
        "breathing": "Вдох перед опусканием, выдох после прохождения тяжёлой части подъёма.",
        "mistakes": [
            "Гриф или yoke установлен несимметрично",
            "Корпус заваливается вперёд в нижней точке",
            "Возврат на стойки выполняется боком",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Кор"],
        "safety_notes": [
            "Проверь высоту стоек и страховок; используй только устойчивую safety bar без самодельных креплений."
        ],
    },
    "negative-pull-ups": {
        "steps": [
            "Встань на устойчивую платформу и займи верхнее положение подтягивания с контролируемым хватом.",
            "Медленно опускайся, удерживая лопатки собранными и сохраняя корпус без раскачивания.",
            "Коснись платформы ногами, останови движение и снова поднимись на старт без прыжка.",
        ],
        "breathing": "Вдох перед началом опускания, спокойный выдох в течение негативной фазы.",
        "mistakes": [
            "Падение из верхней точки",
            "Платформа стоит нестабильно",
            "Старт выполняется прыжком с раскачкой",
        ],
        "secondary": ["Бицепс", "Предплечья", "Кор"],
        "safety_notes": [
            "Используй устойчивую платформу и не начинай повтор, если безопасный спуск уже не контролируется."
        ],
    },
    "scapular-pull-ups": {
        "steps": [
            "Повисни на перекладине без раскачивания и оставь локти выпрямленными.",
            "Опусти и слегка сведи лопатки, поднимая грудную клетку на небольшую амплитуду без сгибания рук.",
            "Плавно отпусти лопатки и вернись в исходный вис, сохраняя хват.",
        ],
        "breathing": "Выдох при движении лопаток вниз и назад, вдох при возврате.",
        "mistakes": [
            "Движение выполняется сгибанием локтей",
            "Корпус раскачивается",
            "Плечи резко проваливаются в нижней точке",
        ],
        "secondary": ["Задняя дельта", "Нижняя трапеция", "Предплечья"],
        "safety_notes": [
            "Проверь устойчивость перекладины и прекращай подход до потери контроля плечевого пояса."
        ],
    },
    "muscle-ups": {
        "steps": [
            "Возьмись за перекладину и создай собранное положение корпуса, используя только контролируемый замах.",
            "Потяни грудь к перекладине, проведи плечи над ней и переведи корпус в верхнюю опору.",
            "Выжми себя над перекладиной и спустись по обратной траектории без падения.",
        ],
        "breathing": "Выдох при тяге и переходе, вдох при контролируемом спуске.",
        "mistakes": [
            "Переход выполняется резким броском плеч",
            "Корпус теряет собранную линию",
            "Спуск завершается падением с перекладины",
        ],
        "secondary": ["Бицепс", "Трицепс", "Кор"],
        "safety_notes": [
            "Оставь свободную зону под перекладиной и используй этот вариант только при контролируемом переходе и спуске."
        ],
    },
    "assisted-dips": {
        "steps": [
            "Выбери противовес, поставь колени или стопы на платформу и удерживай плечи ниже ушей.",
            "Согни локти и опустись до комфортной глубины, сохраняя корпус устойчивым между рукоятями.",
            "Надави на рукояти и вернись вверх, затем дождись остановки платформы перед сходом.",
        ],
        "breathing": "Вдох при опускании, выдох при разгибании локтей.",
        "mistakes": [
            "Платформа подбрасывается рывком",
            "Плечи проваливаются ниже контроля",
            "Вес сбрасывается на стек внизу",
        ],
        "secondary": ["Грудь", "Передняя дельта", "Кор"],
        "safety_notes": [
            "Проверь фиксацию платформы и противовеса, а сходи с тренажёра после полной остановки механизма."
        ],
    },
    "machine-seated-crunch": {
        "steps": [
            "Настрой сиденье и валик по инструкции тренажёра, поставь стопы устойчиво и удерживай таз на опоре.",
            "Сверни грудную клетку к тазу, двигая рукояти или валик корпусом, а не рывком рук.",
            "Плавно вернись в исходное положение и не позволяй весовому стеку ударяться.",
        ],
        "breathing": "Выдох при сгибании корпуса, вдох при контролируемом возврате.",
        "mistakes": [
            "Сиденье или валик не совпадают с ростом",
            "Вес тянется руками вместо корпуса",
            "Стек резко возвращается на ограничитель",
        ],
        "secondary": ["Кор", "Косые мышцы"],
        "safety_notes": [
            "Настрой контакт валика и ось тренажёра до начала подхода; не используй рывок для запуска стека."
        ],
    },
    "band-pull-apart": {
        "steps": [
            "Возьми резинку перед собой на уровне груди, слегка согни локти и опусти плечи.",
            "Разведи кисти в стороны, сводя лопатки без прогиба в пояснице и без подъёма плеч.",
            "Плавно верни руки вперёд, сохраняя натяжение резинки до последнего повтора.",
        ],
        "breathing": "Выдох при разведении рук, вдох при контролируемом возврате.",
        "mistakes": [
            "Руки разводятся рывком",
            "Плечи поднимаются к ушам",
            "Локти блокируются и резинка теряет контроль",
        ],
        "secondary": ["Нижняя трапеция", "Задняя дельта", "Плечи"],
        "safety_notes": [
            "Перед подходом осмотри резинку на повреждения и оставь натяжение, которое можно плавно вернуть."
        ],
    },
    "db-squat": {
        "steps": [
            "Возьми по гантели в каждую руку, опусти плечи и поставь стопы устойчиво на ширине, удобной для приседа.",
            "Отведи таз назад и согни колени, сохраняя гантели вдоль корпуса и стопы полностью на полу.",
            "Надави всей стопой и встань без раскачивания гантелей и жёсткой блокировки коленей.",
        ],
        "breathing": "Вдох перед опусканием, выдох после прохождения тяжёлой части подъёма.",
        "mistakes": [
            "Гантели тянут корпус вперёд",
            "Колени смещаются внутрь",
            "Пятки отрываются от пола",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Кор"],
    },
    "kettlebell-overhead-carry": {
        "steps": [
            "Подними гирю над головой, зафиксируй запястье и расположи снаряд над плечом.",
            "Иди короткими ровными шагами, удерживая рёбра и таз собранными, а взгляд — вперёд.",
            "Остановись, опусти гирю к плечу и верни её на пол только после устойчивой фиксации корпуса.",
        ],
        "breathing": "Дыши ровно во время ходьбы, не задерживая дыхание на всём переносе.",
        "mistakes": [
            "Гиря уходит за линию корпуса",
            "Шаги становятся широкими и шаткими",
            "Снаряд бросается на пол из верхнего положения",
        ],
        "secondary": ["Кор", "Плечи", "Предплечья"],
        "safety_notes": [
            "Проверь свободное пространство над головой и по маршруту, прежде чем поднимать гирю."
        ],
    },
    "dragon-flag": {
        "steps": [
            "Ляг на скамью, возьмись руками за край за головой и подними таз с собранным корпусом.",
            "Опускай прямую линию тела к скамье, сохраняя рёбра и таз соединёнными без рывка.",
            "Остановись до потери контроля и верни тело вверх через напряжение корпуса, а не мах ногами.",
        ],
        "breathing": "Вдох при контролируемом опускании, выдох во время возврата вверх.",
        "mistakes": [
            "Поясница прогибается и линия тела ломается",
            "Ноги падают вниз без остановки",
            "Подъём начинается махом",
        ],
        "secondary": ["Пресс", "Плечи", "Кор"],
        "safety_notes": [
            "Начинай с облегчённой амплитуды и не используй рывок, если таз уже не удерживается над скамьёй."
        ],
    },
    "jackknife-sit-up": {
        "steps": [
            "Ляг на спину, вытяни руки и ноги, прижми таз и подготовь корпус к одновременному сгибанию.",
            "Подними руки и ноги навстречу друг другу, формируя складку без броска поясницы в пол.",
            "Плавно вернись в исходное положение и останови движение до начала раскачки.",
        ],
        "breathing": "Выдох при складывании, вдох при контролируемом возвращении.",
        "mistakes": [
            "Подъём выполняется только махом ног",
            "Поясница отрывается и падает на пол",
            "Возврат происходит без контроля",
        ],
        "secondary": ["Кор", "Квадрицепс"],
    },
    "l-sit": {
        "steps": [
            "Упрись прямыми руками в устойчивые брусья или паралетсы и опусти плечи вниз.",
            "Подними таз и вытяни ноги вперёд, сохраняя корпус собранным и стопы на одной линии.",
            "Удерживай положение ровно, затем плавно опусти ноги до потери контроля хвата.",
        ],
        "breathing": "Дыши спокойно и не задерживай дыхание во время удержания.",
        "mistakes": [
            "Плечи поднимаются к ушам",
            "Таз провисает между опорами",
            "Ноги опускаются резко",
        ],
        "secondary": ["Пресс", "Трицепс", "Плечи", "Хват"],
        "safety_notes": [
            "Используй только устойчивые опоры, которые не скользят при переносе веса на руки."
        ],
    },
    "clean-and-jerk": {
        "steps": [
            "Начни со штангой у голеней, зафиксируй корпус и подними её к плечам через согласованное разгибание ног и таза.",
            "Поймай штангу на передней части плеч, собери корпус и подготовь стопы к толчку.",
            "Сделай короткий подсед, вытолкни штангу над головой и верни её на плечи под контролем.",
        ],
        "breathing": "Вдох и фиксация перед первым подъёмом, выдох после фиксации над головой.",
        "mistakes": [
            "Штанга уходит далеко от корпуса",
            "Приём на плечи выполняется жёстко и без фиксации стоп",
            "Толчок заменяется медленным жимом с потерей позиции",
        ],
        "secondary": ["Плечи", "Трапеции", "Квадрицепс", "Ягодицы"],
        "safety_notes": [
            "Проверь замки и свободное пространство над головой; используй вес, при котором обе фазы остаются контролируемыми."
        ],
    },
    "hang-power-clean": {
        "steps": [
            "Удерживай штангу у бёдер, отведи таз назад и опусти её до позиции виса с нейтральным корпусом.",
            "Резко выпрями таз и ноги, проведи штангу близко к телу и поймай её на плечах без глубокого приседа.",
            "Верни штангу к бёдрам и снова займи устойчивый вис, не бросая её между повторами.",
        ],
        "breathing": "Вдох перед стартом из виса, выдох после стабильного приёма на плечи.",
        "mistakes": [
            "Колени уходят вперёд и штанга отдаляется от тела",
            "Подъём начинается руками до разгибания таза",
            "Приём выполняется на прямые локти",
        ],
        "secondary": ["Плечи", "Трапеции", "Квадрицепс", "Ягодицы"],
        "safety_notes": [
            "Проверь замки и оставь свободную зону вокруг штанги до начала взрывной фазы."
        ],
    },
    "wrist-roller": {
        "steps": [
            "Возьми рукоять ролика обеими руками, вытяни её перед собой и закрепи груз на свободном пространстве.",
            "Поворачивай рукоять кистями, поднимая груз ровно и не раскачивая локти или плечи.",
            "Размотай груз в обратную сторону под контролем и положи ролик после полной остановки.",
        ],
        "breathing": "Дыши спокойно; выдох на подкручивании, вдох на контролируемой размотке.",
        "mistakes": [
            "Локти и плечи помогают рывком",
            "Груз падает без контролируемой размотки",
            "Ролик держится слишком тяжёлым хватом при потере позиции кистей",
        ],
        "secondary": ["Хват", "Бицепс"],
        "safety_notes": [
            "Убери людей и предметы из зоны падения груза и остановись до полной потери контроля кистей."
        ],
    },
    "rope-climb": {
        "steps": [
            "Возьмись за канат, зафиксируй его стопами или замком ног и подними тело коротким тягущим движением.",
            "Переставляй руки и ноги поочерёдно, сохраняя канат близко к корпусу и не раскачиваясь.",
            "Спускайся небольшими шагами, удерживая канат до устойчивой опоры обеих ног.",
        ],
        "breathing": "Выдыхай на каждом тяговом усилии и дыши ровно во время спуска.",
        "mistakes": [
            "Подъём выполняется только руками без фиксации ног",
            "Корпус раскачивается вокруг каната",
            "Спуск завершается прыжком с высоты",
        ],
        "secondary": ["Бицепс", "Предплечья", "Кор"],
        "safety_notes": [
            "Проверь крепление каната и маты под ним; спускайся контролируемо и не прыгай с высоты."
        ],
    },
}


MEDIA_ALT_BY_PHASE: dict[str, dict[str, str]] = {
    "pendulum-squat": {
        "eccentric_end": "Маятниковый присед: нижнее положение на дуге тренажёра, стопы устойчивы на платформе",
        "concentric_end": "Маятниковый присед: верхнее положение, плечи под упорами и колени без жёсткой блокировки",
    },
    "plate-loaded-leg-press": {
        "eccentric_end": "Жим ногами с дисками: нижнее положение, платформа приближена к корпусу без отрыва таза",
        "concentric_end": "Жим ногами с дисками: платформа выжата, стопы полностью сохраняют опору",
    },
    "unilateral-leg-press": {
        "eccentric_end": "Жим одной ногой: нижнее положение, рабочее колено согнуто по линии стопы",
        "concentric_end": "Жим одной ногой: платформа выжата рабочей ногой, таз остаётся по центру спинки",
    },
    "machine-hip-thrust": {
        "eccentric_end": "Ягодичный мост в рычажном тренажёре: таз опущен, стопы и верх спины на опорах",
        "concentric_end": "Ягодичный мост в рычажном тренажёре: бёдра разогнуты, корпус и бёдра образуют линию",
    },
    "smith-split-squat": {
        "eccentric_end": "Сплит-присед в Смите: нижнее положение в разножке, передняя стопа полностью на полу",
        "concentric_end": "Сплит-присед в Смите: верхнее положение под грифом, таз направлен вперёд",
    },
    "machine-glute-kickback": {
        "eccentric_end": "Разгибание бедра в тренажёре: исходное положение, рабочая стопа на рычажной площадке у корпуса",
        "concentric_end": "Разгибание бедра в тренажёре: конечное положение, площадка отведена назад без поворота таза",
    },
    "v-squat-machine": {
        "eccentric_end": "V-присед в тренажёре: нижнее положение, спина и таз сохраняют контакт с наклонной опорой",
        "concentric_end": "V-присед в тренажёре: верхнее положение, плечи под упорами и стопы на платформе",
    },
    "reverse-hyperextension": {
        "eccentric_end": "Обратная гиперэкстензия: ноги опущены, таз и корпус зафиксированы на опоре",
        "concentric_end": "Обратная гиперэкстензия: ноги подняты примерно до линии корпуса без чрезмерного прогиба",
    },
    "machine-incline-chest-press": {
        "eccentric_end": "Жим от груди вверх в тренажёре: исходное положение, рукояти у верхней части груди",
        "concentric_end": "Жим от груди вверх в тренажёре: конечное положение, руки выпрямлены по диагонали вверх",
    },
    "independent-lever-chest-press": {
        "eccentric_end": "Независимый рычажный жим от груди: исходное положение, рукояти у груди",
        "concentric_end": "Независимый рычажный жим от груди: конечное положение, оба рычага выжаты вперёд",
    },
    "lever-high-row": {
        "eccentric_end": "Верхняя рычажная тяга: исходное положение, грудь на опоре и руки направлены вверх-вперёд",
        "concentric_end": "Верхняя рычажная тяга: конечное положение, локти отведены вниз и назад",
    },
    "lever-low-row": {
        "eccentric_end": "Нижняя рычажная тяга: исходное положение, грудь на опоре и руки направлены вперёд-вниз",
        "concentric_end": "Нижняя рычажная тяга: конечное положение, локти отведены назад к талии",
    },
    "independent-lever-lat-pulldown": {
        "eccentric_end": "Вертикальная рычажная тяга: исходное положение, независимые рукояти над головой",
        "concentric_end": "Вертикальная рычажная тяга: конечное положение, локти опущены к бокам",
    },
    "machine-pullover": {
        "eccentric_end": "Пуловер в тренажёре: исходное положение, рычаг над головой и спина на опоре",
        "concentric_end": "Пуловер в тренажёре: конечное положение, рычаг опущен дугой к корпусу",
    },
    "independent-lever-shoulder-press": {
        "eccentric_end": "Независимый рычажный жим над головой: исходное положение, рукояти около плеч",
        "concentric_end": "Независимый рычажный жим над головой: конечное положение, рычаги выжаты вверх",
    },
    "machine-decline-chest-press": {
        "eccentric_end": "Жим от груди вниз в тренажёре: исходное положение, рукояти у нижней части груди",
        "concentric_end": "Жим от груди вниз в тренажёре: конечное положение, руки выпрямлены вперёд-вниз",
    },
    "machine-triceps-extension": {
        "eccentric_end": "Разгибание рук в тренажёре: исходное положение, локти на опоре и руки согнуты",
        "concentric_end": "Разгибание рук в тренажёре: конечное положение, локти разогнуты под контролем",
    },
    "chest-supported-dumbbell-row": {
        "eccentric_end": "Тяга гантелей с упором грудью: исходное положение, руки опущены под скамьёй",
        "concentric_end": "Тяга гантелей с упором грудью: конечное положение, локти отведены назад",
    },
    "bodyweight-squat": {
        "eccentric_end": "Приседания с собственным весом: нижнее положение с устойчивыми стопами",
        "concentric_end": "Приседания с собственным весом: верхнее положение без жёсткой блокировки коленей",
    },
    "bodyweight-glute-bridge": {
        "technique": "Ягодичный мост с собственным весом: исходное и верхнее положения с опорой стоп и плеч",
    },
    "barbell-wrist-curl": {
        "eccentric_end": "Сгибание кистей со штангой: запястья опущены за краем опоры",
        "concentric_end": "Сгибание кистей со штангой: кисти подняты, предплечья остаются на опоре",
    },
    "barbell-wrist-extension": {
        "eccentric_end": "Разгибание кистей со штангой: кисти опущены ладонями вниз",
        "concentric_end": "Разгибание кистей со штангой: тыльная сторона кистей поднята, предплечья неподвижны",
    },
    "dead-hang": {
        "technique": "Вис на перекладине: устойчивый хват, спокойный корпус и безопасная опора для завершения",
    },
    "recumbent-bike": {
        "cycle_one": "Горизонтальный велотренажёр: одна педаль в ближней точке, спина на опоре",
        "cycle_two": "Горизонтальный велотренажёр: та же нога в дальней точке с мягко согнутым коленом",
    },
    "pendlay-row": {
        "technique": "Тяга Пендлея: старт штанги с пола и верхняя точка у нижней части груди",
    },
    "weighted-dip": {
        "technique": "Отжимания на брусьях с весом: внешнее отягощение на поясе и две контролируемые позиции",
    },
    "single-leg-calf-raise": {
        "technique": "Подъём на носок одной ногой: нижняя и верхняя позиции рабочей стопы на краю опоры",
    },
    "hollow-hold": {
        "technique": "Холлоу-холд: подготовка лёжа и удержание дуги с прижатой поясницей",
    },
    "meadows-row": {
        "eccentric_end": "Тяга Медоуза: рука выпрямлена к свободному концу штанги, корпус устойчив",
        "concentric_end": "Тяга Медоуза: локоть отведён назад, свободный конец штанги у корпуса",
    },
    "captain-chair-leg-raise": {
        "eccentric_end": "Подъём ног в упоре: корпус на предплечьях и спинке, ноги опущены",
        "concentric_end": "Подъём ног в упоре: колени подняты без раскачивания корпуса",
    },
    "belt-squat": {
        "technique": "Поясной присед: груз закреплён на поясе, показаны верхняя и нижняя позиции",
    },
    "wall-sit": {
        "technique": "Статический присед у стены: контролируемый вход и удержание с опорой спины",
    },
}


@lru_cache(maxsize=1)
def structured_catalog_metadata() -> dict[str, StructuredExerciseCatalogMetadata]:
    """Materialize one reviewed metadata record for every canonical seed row."""

    from fitminiapp_api.services.exercise_guides import PROFILES, SLUG_TO_PROFILE
    from fitminiapp_api.services.program_seed_data import (
        EXERCISE_CATALOG,
        exercise_difficulty_level,
    )

    records: dict[str, StructuredExerciseCatalogMetadata] = {}
    for slug, _title, primary_muscle, equipment in EXERCISE_CATALOG:
        canonical = CANONICAL_EXERCISE_REDIRECTS.get(slug, slug)
        if canonical in records:
            continue
        movement_pattern = REVIEWED_MOVEMENT_PATTERN_BY_SLUG.get(canonical)
        if movement_pattern is None:
            raise ValueError(f"Reviewed movement pattern is missing: {canonical}")
        profile_name = SLUG_TO_PROFILE.get(canonical)
        if profile_name is None:
            raise ValueError(f"Reviewed guide profile is missing: {canonical}")
        profile = ITEM_GUIDE_CONTENT.get(canonical, PROFILES[profile_name])
        difficulty_level = exercise_difficulty_level(canonical)
        optional = CATALOG_METADATA.get(
            canonical,
            {
                "aliases": (),
                "movement_pattern": movement_pattern,
                "machine_variant_tags": (),
                "execution_variant_tags": (),
            },
        )
        records[canonical] = {
            "primary_muscle": primary_muscle,
            "secondary_muscles": tuple(profile["secondary"]),
            "equipment": equipment,
            "movement_pattern": movement_pattern,
            "difficulty_level": cast(
                Literal["beginner", "intermediate", "advanced"], difficulty_level
            ),
            "metric_type": "cardio" if primary_muscle == "Кардио" else "strength",
            "aliases": tuple(optional["aliases"]),
            "machine_variant_tags": tuple(optional["machine_variant_tags"]),
            "execution_variant_tags": tuple(optional["execution_variant_tags"]),
        }
    return records


def base_exercise_slug(slug: str) -> str:
    return slug.split("-u-", maxsplit=1)[0]


def exercise_catalog_metadata(slug: str) -> StructuredExerciseCatalogMetadata | None:
    base_slug = base_exercise_slug(slug)
    canonical = CANONICAL_EXERCISE_REDIRECTS.get(base_slug, base_slug)
    return structured_catalog_metadata().get(canonical)
