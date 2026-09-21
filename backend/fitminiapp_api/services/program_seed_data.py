from __future__ import annotations

type ExerciseSeed = tuple[str, str, str, str]
type TemplateExerciseMetadata = dict[str, object]
type TemplateExerciseSeed = (
    tuple[str, int, str, int] | tuple[str, int, str, int, TemplateExerciseMetadata]
)
type TemplateDaySeed = tuple[str, list[TemplateExerciseSeed]]

LEGACY_TEMPLATE_SLUGS = {"upper-lower-4x"}

# Difficulty is intentionally catalog metadata rather than a property of a
# particular program. Keep the technically demanding movements explicit; the
# remaining exercises form the intermediate tier unless listed as approachable
# beginner variants below.
BEGINNER_EXERCISE_SLUGS = {
    "machine-chest-press",
    "machine-incline-chest-press",
    "independent-lever-chest-press",
    "machine-decline-chest-press",
    "smith-bench-press",
    "push-up",
    "pec-deck",
    "lat-pulldown",
    "reverse-grip-lat-pulldown",
    "close-grip-lat-pulldown",
    "straight-arm-pulldown",
    "chest-supported-row",
    "seated-cable-row",
    "machine-row",
    "lever-high-row",
    "lever-low-row",
    "independent-lever-lat-pulldown",
    "machine-pullover",
    "chest-supported-dumbbell-row",
    "inverted-row",
    "hyperextension",
    "pendulum-squat",
    "plate-loaded-leg-press",
    "machine-hip-thrust",
    "machine-glute-kickback",
    "v-squat-machine",
    "goblet-squat",
    "bodyweight-squat",
    "smith-squat",
    "belt-squat",
    "leg-press",
    "reverse-lunge",
    "step-up",
    "leg-extension",
    "wall-sit",
    "leg-curl",
    "seated-leg-curl",
    "standing-leg-curl",
    "single-leg-hip-thrust",
    "bodyweight-glute-bridge",
    "hip-abduction",
    "hip-adduction",
    "cable-kickback",
    "machine-shoulder-press",
    "independent-lever-shoulder-press",
    "smith-shoulder-press",
    "dumbbell-lateral-raise",
    "cable-lateral-raise",
    "machine-lateral-raise",
    "dumbbell-front-raise",
    "reverse-pec-deck",
    "face-pull",
    "dumbbell-shrug",
    "dumbbell-curl",
    "hammer-curl",
    "cable-curl",
    "concentration-curl",
    "machine-biceps-curl",
    "rope-pushdown",
    "cable-pushdown",
    "bench-dip",
    "triceps-kickback",
    "machine-dip",
    "machine-triceps-extension",
    "single-arm-cable-triceps-extension",
    "standing-calf-raise",
    "seated-calf-raise",
    "calf-press",
    "plank",
    "crunch",
    "reverse-crunch",
    "captain-chair-leg-raise",
    "dead-hang",
    "dead-bug",
    "bird-dog",
    "jump-rope",
    "rowing-machine",
    "treadmill-run",
    "assault-bike",
    "elliptical-trainer",
    "stationary-bike",
    "recumbent-bike",
    "outdoor-walk",
    "treadmill-walk",
    "stair-climber",
    "assisted-pull-ups",
    "assisted-dips",
    "scapular-pull-ups",
    "cable-external-rotation",
    "band-pull-apart",
    "db-squat",
    "machine-seated-crunch",
}

ADVANCED_EXERCISE_SLUGS = {
    "weighted-dip",
    "chest-dip",
    "deadlift",
    "rack-pull",
    "pull-up",
    "chin-up",
    "pendlay-row",
    "meadows-row",
    "good-morning",
    "front-squat",
    "walking-lunge",
    "bulgarian-split-squat",
    "sissy-squat",
    "single-leg-rdl",
    "nordic-curl",
    "glute-ham-raise",
    "kettlebell-swing",
    "sumo-deadlift",
    "overhead-press",
    "arnold-press",
    "landmine-press",
    "upright-row",
    "skull-crusher",
    "hanging-leg-raise",
    "ab-wheel",
    "burpee",
    "box-jump",
    "battle-rope",
    "sled-push",
    "sled-pull",
    "farmer-walk",
    "medicine-ball-slam",
    "wall-ball",
    "thruster",
    "kettlebell-clean",
    "kettlebell-snatch",
    "turkish-get-up",
    "renegade-row",
    "push-press",
    "pistol-squat",
    "overhead-squat",
    "trap-bar-deadlift",
    "safety-bar-squat",
    "negative-pull-ups",
    "muscle-ups",
    "dragon-flag",
    "l-sit",
    "clean-and-jerk",
    "hang-power-clean",
    "rope-climb",
}


def exercise_difficulty_level(slug: str) -> str:
    if slug in BEGINNER_EXERCISE_SLUGS:
        return "beginner"
    if slug in ADVANCED_EXERCISE_SLUGS:
        return "advanced"
    return "intermediate"


EXERCISE_CATALOG: list[ExerciseSeed] = [
    ("bench-press", "Жим лежа", "Грудь", "Штанга"),
    ("incline-bench-press", "Жим штанги на наклонной скамье", "Грудь", "Штанга"),
    ("decline-bench-press", "Жим штанги вниз головой", "Грудь", "Штанга"),
    ("close-grip-bench-press", "Жим лежа узким хватом", "Трицепс", "Штанга"),
    ("dumbbell-bench-press", "Жим гантелей лежа", "Грудь", "Гантели"),
    ("incline-dumbbell-press", "Жим гантелей на наклонной скамье", "Грудь", "Гантели"),
    ("decline-dumbbell-press", "Жим гантелей вниз головой", "Грудь", "Гантели"),
    ("dumbbell-fly", "Разведение гантелей лежа", "Грудь", "Гантели"),
    ("incline-dumbbell-fly", "Разведение гантелей на наклонной скамье", "Грудь", "Гантели"),
    ("cable-fly", "Сведение рук в кроссовере", "Грудь", "Кроссовер"),
    ("low-to-high-cable-fly", "Сведение снизу вверх в кроссовере", "Грудь", "Кроссовер"),
    ("pec-deck", "Сведение рук в тренажере", "Грудь", "Тренажер"),
    ("machine-chest-press", "Жим от груди в тренажере", "Грудь", "Тренажер"),
    (
        "machine-incline-chest-press",
        "Жим от груди вверх в тренажёре",
        "Грудь",
        "Тренажёр",
    ),
    (
        "independent-lever-chest-press",
        "Жим от груди в независимом рычажном тренажёре",
        "Грудь",
        "Тренажёр",
    ),
    (
        "machine-decline-chest-press",
        "Жим от груди вниз в тренажёре",
        "Грудь",
        "Тренажёр",
    ),
    ("smith-bench-press", "Жим лежа в Смите", "Грудь", "Машина Смита"),
    ("push-up", "Отжимания", "Грудь", "Собственный вес"),
    ("weighted-dip", "Отжимания на брусьях с весом", "Грудь", "Брусья"),
    ("chest-dip", "Отжимания на брусьях с наклоном", "Грудь", "Брусья"),
    ("dumbbell-pullover", "Пуловер с гантелью", "Грудь", "Гантели"),
    ("deadlift", "Становая тяга", "Спина", "Штанга"),
    ("rack-pull", "Тяга с плинтов", "Спина", "Штанга"),
    ("pull-up", "Подтягивания", "Спина", "Турник"),
    ("chin-up", "Подтягивания обратным хватом", "Спина", "Турник"),
    ("lat-pulldown", "Вертикальная тяга", "Спина", "Тренажер"),
    ("reverse-grip-lat-pulldown", "Вертикальная тяга обратным хватом", "Спина", "Тренажер"),
    ("close-grip-lat-pulldown", "Вертикальная тяга узким хватом", "Спина", "Тренажер"),
    ("straight-arm-pulldown", "Пуловер в кроссовере прямыми руками", "Спина", "Кроссовер"),
    ("barbell-row", "Тяга штанги в наклоне", "Спина", "Штанга"),
    ("pendlay-row", "Тяга Пендлея", "Спина", "Штанга"),
    ("t-bar-row", "Тяга Т-грифа", "Спина", "Тренажер"),
    ("one-arm-dumbbell-row", "Тяга гантели одной рукой", "Спина", "Гантели"),
    ("chest-supported-row", "Тяга с упором грудью", "Спина", "Тренажер"),
    ("seated-cable-row", "Горизонтальная тяга блока", "Спина", "Блок"),
    ("machine-row", "Горизонтальная тяга в тренажёре", "Спина", "Тренажёр"),
    (
        "lever-high-row",
        "Верхняя рычажная тяга с упором грудью",
        "Спина",
        "Тренажёр",
    ),
    (
        "lever-low-row",
        "Нижняя рычажная тяга с упором грудью",
        "Спина",
        "Тренажёр",
    ),
    (
        "independent-lever-lat-pulldown",
        "Вертикальная рычажная тяга независимыми руками",
        "Спина",
        "Тренажёр",
    ),
    ("machine-pullover", "Пуловер в тренажёре", "Спина", "Тренажёр"),
    (
        "chest-supported-dumbbell-row",
        "Тяга гантелей с упором грудью",
        "Спина",
        "Гантели",
    ),
    ("inverted-row", "Австралийские подтягивания", "Спина", "Собственный вес"),
    ("meadows-row", "Тяга Медоуза", "Спина", "Штанга"),
    ("cable-row-one-arm", "Тяга блока одной рукой", "Спина", "Блок"),
    ("hyperextension", "Гиперэкстензия", "Разгибатели спины", "Тренажер"),
    ("good-morning", "Наклоны со штангой", "Задняя цепь", "Штанга"),
    ("squat", "Приседания", "Квадрицепс", "Штанга"),
    ("front-squat", "Фронтальные приседания", "Квадрицепс", "Штанга"),
    ("hack-squat", "Гакк-присед", "Квадрицепс", "Тренажер"),
    ("smith-squat", "Приседания в Смите", "Квадрицепс", "Машина Смита"),
    ("goblet-squat", "Гоблет-присед с гирей", "Квадрицепс", "Гиря"),
    (
        "bodyweight-squat",
        "Приседания с собственным весом",
        "Квадрицепс",
        "Собственный вес",
    ),
    ("belt-squat", "Поясной присед", "Квадрицепс", "Тренажер"),
    ("leg-press", "Жим ногами", "Квадрицепс", "Тренажер"),
    (
        "pendulum-squat",
        "Маятниковый присед в тренажёре",
        "Квадрицепс",
        "Тренажёр",
    ),
    (
        "plate-loaded-leg-press",
        "Жим ногами в тренажёре с дисками",
        "Квадрицепс",
        "Тренажёр",
    ),
    (
        "unilateral-leg-press",
        "Жим одной ногой в тренажёре",
        "Квадрицепс",
        "Тренажёр",
    ),
    ("v-squat-machine", "V-присед в рычажном тренажёре", "Квадрицепс", "Тренажёр"),
    ("lunge", "Выпады", "Ноги", "Гантели"),
    ("walking-lunge", "Выпады в ходьбе", "Ноги", "Гантели"),
    ("reverse-lunge", "Обратные выпады", "Ноги", "Гантели"),
    ("bulgarian-split-squat", "Болгарские сплит-приседания", "Ноги", "Гантели"),
    ("split-squat", "Сплит-присед", "Ноги", "Гантели"),
    ("smith-split-squat", "Сплит-присед в машине Смита", "Ноги", "Машина Смита"),
    ("step-up", "Зашагивания на тумбу", "Ноги", "Гантели"),
    ("leg-extension", "Разгибание ног", "Квадрицепс", "Тренажер"),
    ("sissy-squat", "Сисси-присед", "Квадрицепс", "Собственный вес"),
    ("wall-sit", "Стульчик у стены", "Квадрицепс", "Собственный вес"),
    ("romanian-deadlift", "Румынская тяга", "Бицепс бедра", "Штанга"),
    ("stiff-leg-deadlift", "Тяга на прямых ногах", "Бицепс бедра", "Штанга"),
    ("single-leg-rdl", "Румынская тяга на одной ноге", "Бицепс бедра", "Гантели"),
    ("leg-curl", "Сгибание ног лежа", "Бицепс бедра", "Тренажер"),
    ("seated-leg-curl", "Сгибание ног сидя", "Бицепс бедра", "Тренажер"),
    ("standing-leg-curl", "Сгибание ноги стоя", "Бицепс бедра", "Тренажер"),
    ("nordic-curl", "Нордические сгибания", "Бицепс бедра", "Собственный вес"),
    ("glute-ham-raise", "Подъем корпуса GHD", "Бицепс бедра", "Тренажер"),
    (
        "reverse-hyperextension",
        "Обратная гиперэкстензия",
        "Задняя цепь",
        "Тренажёр",
    ),
    (
        "hip-thrust",
        "Ягодичный мост со штангой с опорой на скамью",
        "Ягодицы",
        "Штанга",
    ),
    ("single-leg-hip-thrust", "Ягодичный мост на одной ноге", "Ягодицы", "Собственный вес"),
    (
        "bodyweight-glute-bridge",
        "Ягодичный мост с собственным весом",
        "Ягодицы",
        "Собственный вес",
    ),
    ("barbell-glute-bridge", "Ягодичный мост со штангой с пола", "Ягодицы", "Штанга"),
    (
        "machine-hip-thrust",
        "Ягодичный мост в рычажном тренажёре",
        "Ягодицы",
        "Тренажёр",
    ),
    ("cable-pull-through", "Протяжка между ног в кроссовере", "Ягодицы", "Кроссовер"),
    ("kettlebell-swing", "Махи гирей", "Задняя цепь", "Гиря"),
    ("hip-abduction", "Отведение бедра в тренажере", "Ягодицы", "Тренажер"),
    ("hip-adduction", "Сведение бедер в тренажере", "Приводящие", "Тренажер"),
    ("cable-kickback", "Отведение ноги назад в кроссовере", "Ягодицы", "Кроссовер"),
    (
        "machine-glute-kickback",
        "Разгибание бедра назад в тренажёре",
        "Ягодицы",
        "Тренажёр",
    ),
    ("sumo-deadlift", "Становая тяга сумо", "Ноги", "Штанга"),
    ("overhead-press", "Жим стоя", "Плечи", "Штанга"),
    ("seated-dumbbell-press", "Жим гантелей сидя", "Плечи", "Гантели"),
    ("arnold-press", "Жим Арнольда", "Плечи", "Гантели"),
    ("machine-shoulder-press", "Жим плечами в тренажере", "Плечи", "Тренажер"),
    (
        "independent-lever-shoulder-press",
        "Жим над головой в независимом рычажном тренажёре",
        "Плечи",
        "Тренажёр",
    ),
    ("smith-shoulder-press", "Жим сидя в Смите", "Плечи", "Машина Смита"),
    ("landmine-press", "Жим штанги в упоре", "Плечи", "Штанга"),
    ("dumbbell-lateral-raise", "Подъем гантелей через стороны", "Средняя дельта", "Гантели"),
    (
        "cable-lateral-raise",
        "Подъем руки через сторону в кроссовере",
        "Средняя дельта",
        "Кроссовер",
    ),
    ("machine-lateral-raise", "Подъем через стороны в тренажере", "Средняя дельта", "Тренажер"),
    ("dumbbell-front-raise", "Подъем гантелей перед собой", "Передняя дельта", "Гантели"),
    ("rear-delt-fly", "Разведение гантелей в наклоне", "Задняя дельта", "Гантели"),
    ("reverse-pec-deck", "Обратная бабочка", "Задняя дельта", "Тренажер"),
    ("face-pull", "Тяга каната к лицу", "Задняя дельта", "Кроссовер"),
    ("upright-row", "Тяга к подбородку", "Плечи", "Штанга"),
    ("barbell-shrug", "Шраги со штангой", "Трапеции", "Штанга"),
    ("dumbbell-shrug", "Шраги с гантелями", "Трапеции", "Гантели"),
    ("y-raise", "Y-подъемы", "Нижняя трапеция", "Гантели"),
    ("barbell-curl", "Подъем штанги на бицепс", "Бицепс", "Штанга"),
    ("ez-bar-curl", "Подъем EZ-штанги на бицепс", "Бицепс", "EZ-штанга"),
    ("dumbbell-curl", "Подъем гантелей на бицепс", "Бицепс", "Гантели"),
    ("hammer-curl", "Молотковые сгибания", "Бицепс", "Гантели"),
    ("incline-dumbbell-curl", "Сгибания гантелей на наклонной скамье", "Бицепс", "Гантели"),
    ("preacher-curl", "Сгибания на скамье Скотта", "Бицепс", "Скамья Скотта"),
    ("cable-curl", "Сгибания рук в кроссовере", "Бицепс", "Кроссовер"),
    ("concentration-curl", "Концентрированные сгибания", "Бицепс", "Гантели"),
    ("reverse-curl", "Подъем штанги обратным хватом", "Предплечья", "Штанга"),
    ("barbell-wrist-curl", "Сгибание кистей со штангой", "Предплечья", "Штанга"),
    (
        "barbell-wrist-extension",
        "Разгибание кистей со штангой",
        "Предплечья",
        "Штанга",
    ),
    ("spider-curl", "Паучьи сгибания", "Бицепс", "Скамья"),
    ("machine-biceps-curl", "Сгибание рук в тренажере", "Бицепс", "Тренажер"),
    ("skull-crusher", "Французский жим лежа", "Трицепс", "EZ-штанга"),
    ("rope-pushdown", "Разгибание рук с канатом", "Трицепс", "Кроссовер"),
    ("cable-pushdown", "Разгибание рук на блоке", "Трицепс", "Блок"),
    (
        "overhead-triceps-extension",
        "Разгибание рук из-за головы в кроссовере",
        "Трицепс",
        "Кроссовер",
    ),
    ("dumbbell-overhead-extension", "Французский жим гантели сидя", "Трицепс", "Гантель"),
    ("lying-dumbbell-triceps-extension", "Разгибание гантелей лежа", "Трицепс", "Гантели"),
    ("bench-dip", "Обратные отжимания от скамьи", "Трицепс", "Собственный вес"),
    ("triceps-kickback", "Разгибание руки назад с гантелью", "Трицепс", "Гантель"),
    ("machine-dip", "Отжимания в тренажере", "Трицепс", "Тренажер"),
    ("machine-triceps-extension", "Разгибание рук в тренажёре", "Трицепс", "Тренажёр"),
    ("single-arm-cable-triceps-extension", "Разгибание одной руки на блоке", "Трицепс", "Блок"),
    ("standing-calf-raise", "Подъемы на носки стоя", "Икры", "Тренажер"),
    ("seated-calf-raise", "Подъемы на носки сидя", "Икры", "Тренажер"),
    ("donkey-calf-raise", "Ослиные подъемы на носки", "Икры", "Тренажер"),
    ("calf-press", "Жим носками в тренажере", "Икры", "Тренажер"),
    ("single-leg-calf-raise", "Подъем на носок одной ногой", "Икры", "Собственный вес"),
    ("plank", "Планка", "Кор", "Собственный вес"),
    ("side-plank", "Боковая планка", "Кор", "Собственный вес"),
    ("crunch", "Скручивания", "Пресс", "Собственный вес"),
    ("reverse-crunch", "Обратные скручивания", "Пресс", "Собственный вес"),
    ("cable-crunch", "Скручивания на блоке", "Пресс", "Блок"),
    ("hanging-leg-raise", "Подъем ног в висе", "Пресс", "Турник"),
    ("dead-hang", "Вис на перекладине", "Хват", "Турник"),
    ("captain-chair-leg-raise", "Подъем ног в упоре", "Пресс", "Тренажер"),
    ("ab-wheel", "Ролик для пресса", "Кор", "Ролик"),
    ("russian-twist", "Русские повороты", "Косые мышцы", "Медбол"),
    ("pallof-press", "Жим Палофа", "Кор", "Кроссовер"),
    ("woodchopper", "Дровосек в кроссовере", "Косые мышцы", "Кроссовер"),
    ("mountain-climber", "Альпинист", "Кор", "Собственный вес"),
    ("hollow-hold", "Холлоу-холд", "Кор", "Собственный вес"),
    ("dead-bug", "Мертвый жук", "Кор", "Собственный вес"),
    ("bird-dog", "Берд-дог", "Кор", "Собственный вес"),
    ("burpee", "Берпи", "Все тело", "Собственный вес"),
    ("box-jump", "Запрыгивания на тумбу", "Ноги", "Тумба"),
    ("jump-rope", "Скакалка", "Кардио", "Скакалка"),
    ("rowing-machine", "Гребля на кардиотренажёре", "Кардио", "Гребной тренажёр"),
    ("treadmill-run", "Беговая дорожка", "Кардио", "Беговая дорожка"),
    ("assault-bike", "Воздушный велотренажёр", "Кардио", "Воздушный велотренажёр"),
    ("outdoor-run", "Бег на улице", "Кардио", "Без оборудования"),
    ("elliptical-trainer", "Эллиптический тренажёр", "Кардио", "Эллиптический тренажёр"),
    ("outdoor-cycling", "Велосипед", "Кардио", "Велосипед"),
    ("stationary-bike", "Велотренажёр", "Кардио", "Велотренажёр"),
    (
        "recumbent-bike",
        "Горизонтальный велотренажёр",
        "Кардио",
        "Горизонтальный велотренажёр",
    ),
    ("outdoor-walk", "Ходьба", "Кардио", "Без оборудования"),
    ("treadmill-walk", "Ходьба на дорожке", "Кардио", "Беговая дорожка"),
    ("stair-climber", "Степпер / лестница", "Кардио", "Степпер"),
    ("swimming", "Плавание", "Кардио", "Бассейн"),
    ("ski-erg", "Лыжный тренажёр", "Кардио", "Лыжный эргометр"),
    ("battle-rope", "Канаты", "Кондиция", "Канаты"),
    ("sled-push", "Толкание саней", "Ноги", "Сани"),
    ("sled-pull", "Тяга саней", "Задняя цепь", "Сани"),
    ("farmer-walk", "Прогулка фермера", "Хват", "Гантели"),
    ("suitcase-carry", "Чемоданная переноска", "Кор", "Гиря"),
    ("medicine-ball-slam", "Броски медбола в пол", "Все тело", "Медбол"),
    ("wall-ball", "Броски мяча в стену", "Все тело", "Медбол"),
    ("thruster", "Трастер", "Все тело", "Штанга"),
    ("kettlebell-clean", "Взятие гири на грудь", "Все тело", "Гиря"),
    ("kettlebell-snatch", "Рывок гири", "Все тело", "Гиря"),
    ("kettlebell-goblet-squat", "Гоблет-присед с гирей", "Ноги", "Гиря"),
    ("turkish-get-up", "Турецкий подъем", "Все тело", "Гиря"),
    ("renegade-row", "Ренегатская тяга", "Спина", "Гантели"),
    ("bear-crawl", "Медвежья проходка", "Все тело", "Собственный вес"),
    ("floor-press", "Жим с пола", "Грудь", "Штанга"),
    ("push-press", "Пуш-пресс", "Плечи", "Штанга"),
    ("assisted-pull-ups", "Подтягивания с противовесом", "Спина", "Тренажёр"),
    ("decline-crunch", "Скручивания на наклонной скамье", "Пресс", "Скамья"),
    ("pistol-squat", "Приседания на одной ноге", "Квадрицепс", "Собственный вес"),
    ("overhead-squat", "Приседания со штангой над головой", "Квадрицепс", "Штанга"),
    ("cable-external-rotation", "Внешняя ротация плеча в кроссовере", "Плечи", "Кроссовер"),
    ("hanging-knee-raise", "Подъём коленей в висе", "Пресс", "Турник"),
    ("trap-bar-deadlift", "Тяга с трэп-грифом", "Задняя цепь", "Штанга"),
    ("safety-bar-squat", "Приседания с safety bar", "Квадрицепс", "Штанга"),
    ("negative-pull-ups", "Негативные подтягивания", "Спина", "Турник"),
    ("scapular-pull-ups", "Лопаточные подтягивания", "Спина", "Турник"),
    ("muscle-ups", "Выходы силой", "Спина", "Турник"),
    ("assisted-dips", "Отжимания на брусьях с противовесом", "Трицепс", "Тренажёр"),
    ("machine-seated-crunch", "Скручивания в тренажёре сидя", "Пресс", "Тренажёр"),
    ("band-pull-apart", "Разведения резинки перед собой", "Задняя дельта", "Другое"),
    ("db-squat", "Приседания с гантелями", "Квадрицепс", "Гантели"),
    ("kettlebell-overhead-carry", "Переноска гири над головой", "Хват", "Гиря"),
    ("dragon-flag", "Драконий флаг", "Кор", "Собственный вес"),
    ("jackknife-sit-up", "Складка лёжа", "Пресс", "Собственный вес"),
    ("l-sit", "L-сит", "Кор", "Брусья"),
    ("clean-and-jerk", "Взятие штанги на грудь и толчок", "Все тело", "Штанга"),
    ("hang-power-clean", "Взятие штанги на грудь с виса", "Все тело", "Штанга"),
    ("wrist-roller", "Ролик для предплечий", "Предплечья", "Ролик"),
    ("rope-climb", "Лазание по канату", "Спина", "Канаты"),
]

PPLF_4_DAYS: list[TemplateDaySeed] = [
    (
        "Тяни",
        [
            ("pull-up", 4, "6-10", 120),
            ("barbell-row", 4, "6-8", 150),
            ("lat-pulldown", 3, "10-12", 90),
            ("barbell-curl", 3, "8-10", 90),
        ],
    ),
    (
        "Толкай",
        [
            ("bench-press", 4, "5-8", 150),
            ("incline-dumbbell-press", 3, "8-10", 120),
            ("overhead-press", 3, "6-8", 150),
            ("rope-pushdown", 3, "10-12", 75),
        ],
    ),
    (
        "Ноги",
        [
            ("squat", 4, "5-8", 180),
            ("leg-press", 3, "10-12", 150),
            ("romanian-deadlift", 3, "8-10", 150),
            ("standing-calf-raise", 4, "12-15", 60),
        ],
    ),
    (
        "Фуллбади",
        [
            ("front-squat", 3, "6-8", 150),
            ("dumbbell-bench-press", 3, "8-10", 120),
            ("seated-cable-row", 3, "10-12", 90),
            ("hip-thrust", 3, "8-10", 120),
        ],
    ),
]

PPLF_8_DAYS: list[TemplateDaySeed] = [
    *PPLF_4_DAYS,
    (
        "Тяни B",
        [
            ("deadlift", 3, "3-5", 180),
            ("chest-supported-row", 4, "8-10", 120),
            ("close-grip-lat-pulldown", 3, "10-12", 90),
            ("hammer-curl", 3, "10-12", 75),
        ],
    ),
    (
        "Толкай B",
        [
            ("incline-bench-press", 4, "6-8", 150),
            ("machine-chest-press", 3, "10-12", 90),
            ("seated-dumbbell-press", 3, "8-10", 120),
            ("overhead-triceps-extension", 3, "10-12", 75),
        ],
    ),
    (
        "Ноги B",
        [
            ("front-squat", 4, "6-8", 150),
            ("bulgarian-split-squat", 3, "8-10", 120),
            ("hip-thrust", 4, "8-10", 120),
            ("seated-calf-raise", 4, "12-15", 60),
        ],
    ),
    (
        "Фуллбади B",
        [
            ("goblet-squat", 3, "10-12", 90),
            ("machine-chest-press", 3, "10-12", 90),
            ("machine-row", 3, "10-12", 90),
            ("plank", 3, "30-60 сек", 60),
        ],
    ),
]

PLPL_4_DAYS: list[TemplateDaySeed] = [
    (
        "Тяни",
        [
            ("pull-up", 4, "6-10", 120),
            ("barbell-row", 4, "6-8", 150),
            ("lat-pulldown", 3, "10-12", 90),
            ("barbell-curl", 3, "8-10", 90),
        ],
    ),
    (
        "Ноги A · акцент на квадрицепс",
        [
            ("squat", 4, "5-8", 180),
            ("leg-press", 3, "10-12", 150),
            ("leg-extension", 3, "12-15", 75),
            ("standing-calf-raise", 4, "12-15", 60),
        ],
    ),
    (
        "Толкай",
        [
            ("bench-press", 4, "5-8", 150),
            ("incline-dumbbell-press", 3, "8-10", 120),
            ("overhead-press", 3, "6-8", 150),
            ("rope-pushdown", 3, "10-12", 75),
        ],
    ),
    (
        "Ноги B · акцент на заднюю цепь",
        [
            ("romanian-deadlift", 4, "6-8", 180),
            ("hip-thrust", 4, "8-10", 120),
            ("seated-leg-curl", 3, "10-12", 90),
            ("seated-calf-raise", 4, "12-15", 60),
        ],
    ),
]

PLPL_8_DAYS: list[TemplateDaySeed] = [
    *PLPL_4_DAYS,
    (
        "Тяни B",
        [
            ("deadlift", 3, "3-5", 180),
            ("chest-supported-row", 4, "8-10", 120),
            ("close-grip-lat-pulldown", 3, "10-12", 90),
            ("hammer-curl", 3, "10-12", 75),
        ],
    ),
    (
        "Ноги C · односторонняя работа",
        [
            ("front-squat", 4, "6-8", 150),
            ("bulgarian-split-squat", 3, "8-10", 120),
            ("step-up", 3, "10-12", 90),
            ("single-leg-calf-raise", 3, "12-15", 60),
        ],
    ),
    (
        "Толкай B",
        [
            ("incline-bench-press", 4, "6-8", 150),
            ("machine-chest-press", 3, "10-12", 90),
            ("seated-dumbbell-press", 3, "8-10", 120),
            ("overhead-triceps-extension", 3, "10-12", 75),
        ],
    ),
    (
        "Ноги D · ягодицы и бицепс бедра",
        [
            ("sumo-deadlift", 4, "5-8", 180),
            ("single-leg-rdl", 3, "8-10", 120),
            ("single-leg-hip-thrust", 3, "10-12", 90),
            ("leg-curl", 3, "10-12", 90),
        ],
    ),
]

STRENGTH_TEMPLATE_SPECS: list[dict[str, object]] = [
    {
        "slug": "strength-pplf-4d",
        "title": "Тяни/Толкай/Ноги/Фуллбади · 4 дня",
        "goal": "recomposition",
        "level": "intermediate",
        "split_type": "hybrid",
        "days": PPLF_4_DAYS,
    },
    {
        "slug": "strength-pplf-8d",
        "title": "Тяни/Толкай/Ноги/Фуллбади · 8 дней",
        "goal": "muscle_gain",
        "level": "advanced",
        "split_type": "hybrid",
        "days": PPLF_8_DAYS,
    },
    {
        "slug": "strength-pull-legs-push-legs-4d",
        "title": "Тяни/Ноги/Толкай/Ноги · 4 дня",
        "goal": "recomposition",
        "level": "intermediate",
        "split_type": "hybrid",
        "days": PLPL_4_DAYS,
    },
    {
        "slug": "strength-pull-legs-push-legs-8d",
        "title": "Тяни/Ноги/Толкай/Ноги · 8 дней",
        "goal": "muscle_gain",
        "level": "advanced",
        "split_type": "hybrid",
        "days": PLPL_8_DAYS,
    },
    {
        "slug": "strength-split-5d",
        "title": "Силовой сплит 5 дней",
        "goal": "muscle_gain",
        "level": "intermediate",
        "split_type": "body_part",
        "days": [
            (
                "Грудь",
                [
                    ("bench-press", 4, "6-8", 150),
                    ("incline-dumbbell-press", 4, "8-10", 120),
                    ("machine-chest-press", 3, "10-12", 90),
                    ("cable-fly", 3, "12-15", 75),
                    ("weighted-dip", 3, "8-10", 120),
                ],
            ),
            (
                "Спина",
                [
                    ("pull-up", 4, "6-10", 120),
                    ("barbell-row", 4, "6-8", 150),
                    ("seated-cable-row", 3, "10-12", 90),
                    ("lat-pulldown", 3, "10-12", 90),
                    ("straight-arm-pulldown", 3, "12-15", 75),
                ],
            ),
            (
                "Ноги",
                [
                    ("squat", 4, "5-8", 180),
                    ("leg-press", 4, "10-12", 150),
                    ("romanian-deadlift", 3, "8-10", 150),
                    ("leg-curl", 3, "10-12", 90),
                    ("standing-calf-raise", 4, "12-15", 60),
                ],
            ),
            (
                "Плечи",
                [
                    ("overhead-press", 4, "6-8", 150),
                    ("dumbbell-lateral-raise", 4, "12-15", 60),
                    ("reverse-pec-deck", 3, "12-15", 75),
                    ("face-pull", 3, "12-15", 75),
                    ("dumbbell-shrug", 3, "10-12", 90),
                ],
            ),
            (
                "Руки",
                [
                    ("close-grip-bench-press", 4, "6-8", 150),
                    ("barbell-curl", 4, "8-10", 90),
                    ("rope-pushdown", 3, "10-12", 75),
                    ("hammer-curl", 3, "10-12", 75),
                    ("overhead-triceps-extension", 3, "12-15", 75),
                ],
            ),
        ],
    },
    {
        "slug": "strength-push-pull-legs-6d",
        "title": "Тяни-толкай-ноги 6 дней",
        "goal": "muscle_gain",
        "level": "advanced",
        "split_type": "push_pull_legs",
        "days": [
            (
                "Толкай A",
                [
                    ("bench-press", 4, "5-8", 150),
                    ("incline-dumbbell-press", 3, "8-10", 120),
                    ("overhead-press", 3, "6-8", 150),
                    ("dumbbell-lateral-raise", 3, "12-15", 60),
                    ("rope-pushdown", 3, "10-12", 75),
                ],
            ),
            (
                "Тяни A",
                [
                    ("pull-up", 4, "6-10", 120),
                    ("barbell-row", 4, "6-8", 150),
                    ("lat-pulldown", 3, "10-12", 90),
                    ("face-pull", 3, "12-15", 75),
                    ("barbell-curl", 3, "8-10", 90),
                ],
            ),
            (
                "Ноги A",
                [
                    ("squat", 4, "5-8", 180),
                    ("leg-press", 3, "10-12", 150),
                    ("romanian-deadlift", 3, "8-10", 150),
                    ("leg-curl", 3, "10-12", 90),
                    ("standing-calf-raise", 4, "12-15", 60),
                ],
            ),
            (
                "Толкай B",
                [
                    ("incline-bench-press", 4, "6-8", 150),
                    ("machine-chest-press", 3, "10-12", 90),
                    ("seated-dumbbell-press", 3, "8-10", 120),
                    ("cable-lateral-raise", 3, "12-15", 60),
                    ("overhead-triceps-extension", 3, "10-12", 75),
                ],
            ),
            (
                "Тяни B",
                [
                    ("deadlift", 3, "3-5", 180),
                    ("chest-supported-row", 4, "8-10", 120),
                    ("close-grip-lat-pulldown", 3, "10-12", 90),
                    ("rear-delt-fly", 3, "12-15", 75),
                    ("hammer-curl", 3, "10-12", 75),
                ],
            ),
            (
                "Ноги B",
                [
                    ("front-squat", 4, "6-8", 150),
                    ("bulgarian-split-squat", 3, "8-10", 120),
                    ("hip-thrust", 4, "8-10", 120),
                    ("leg-extension", 3, "12-15", 75),
                    ("seated-calf-raise", 4, "12-15", 60),
                ],
            ),
        ],
    },
    {
        "slug": "strength-upper-lower-4d",
        "title": "Верх-низ 4 дня",
        "goal": "recomposition",
        "level": "intermediate",
        "split_type": "upper_lower",
        "days": [
            (
                "Верх A",
                [
                    ("bench-press", 4, "5-8", 150),
                    ("barbell-row", 4, "6-8", 150),
                    ("overhead-press", 3, "6-8", 120),
                    ("lat-pulldown", 3, "10-12", 90),
                    ("rope-pushdown", 3, "10-12", 75),
                    ("barbell-curl", 3, "10-12", 75),
                ],
            ),
            (
                "Низ A",
                [
                    ("squat", 4, "5-8", 180),
                    ("romanian-deadlift", 4, "8-10", 150),
                    ("leg-press", 3, "10-12", 120),
                    ("leg-curl", 3, "10-12", 90),
                    ("standing-calf-raise", 4, "12-15", 60),
                ],
            ),
            (
                "Верх B",
                [
                    ("incline-dumbbell-press", 4, "8-10", 120),
                    ("pull-up", 4, "6-10", 120),
                    ("seated-dumbbell-press", 3, "8-10", 120),
                    ("seated-cable-row", 3, "10-12", 90),
                    ("dumbbell-lateral-raise", 3, "12-15", 60),
                    ("face-pull", 3, "12-15", 60),
                ],
            ),
            (
                "Низ B",
                [
                    ("front-squat", 4, "6-8", 150),
                    ("hip-thrust", 4, "8-10", 120),
                    ("bulgarian-split-squat", 3, "8-10", 120),
                    ("seated-leg-curl", 3, "10-12", 90),
                    ("seated-calf-raise", 4, "12-15", 60),
                ],
            ),
        ],
    },
    {
        "slug": "strength-fullbody-3d",
        "title": "Фуллбади 3 дня",
        "goal": "recomposition",
        "level": "beginner",
        "split_type": "full_body",
        "days": [
            (
                "Фуллбади A",
                [
                    ("squat", 4, "6-8", 150),
                    ("bench-press", 4, "6-8", 150),
                    ("seated-cable-row", 3, "10-12", 90),
                    ("romanian-deadlift", 3, "8-10", 120),
                    ("plank", 3, "30-60 сек", 60),
                ],
            ),
            (
                "Фуллбади B",
                [
                    ("deadlift", 3, "3-5", 180),
                    ("overhead-press", 4, "6-8", 150),
                    ("lat-pulldown", 3, "10-12", 90),
                    ("leg-press", 3, "10-12", 120),
                    ("hanging-leg-raise", 3, "10-15", 60),
                ],
            ),
            (
                "Фуллбади C",
                [
                    ("front-squat", 4, "6-8", 150),
                    ("incline-dumbbell-press", 3, "8-10", 120),
                    ("barbell-row", 4, "6-8", 150),
                    ("hip-thrust", 3, "8-10", 120),
                    ("face-pull", 3, "12-15", 60),
                ],
            ),
        ],
    },
]


def _exact_reps(value: int) -> dict[str, object]:
    return {"kind": "exact", "value": value}


def _range_reps(min_reps: int, max_reps: int) -> dict[str, object]:
    return {"kind": "range", "min_reps": min_reps, "max_reps": max_reps}


def _amrap_reps(cap_reps: int | None = None) -> dict[str, object]:
    result: dict[str, object] = {"kind": "amrap"}
    if cap_reps is not None:
        result["cap_reps"] = cap_reps
    return result


def _load_target(kind: str = "user_selected", value: float | None = None) -> dict[str, object]:
    result: dict[str, object] = {"kind": kind}
    if value is not None:
        result["value"] = value
    return result


def _strength_plan(
    rep_targets: list[dict[str, object]],
    rest_seconds: int,
    *,
    roles: list[str] | None = None,
    loads: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    segments: list[dict[str, object]] = []
    for position, rep_target in enumerate(rep_targets, start=1):
        segment: dict[str, object] = {
            "position": position,
            "role": roles[position - 1] if roles else "working",
            "rep_target": rep_target,
            "load_target": loads[position - 1] if loads else _load_target(),
            "effort_target": {"kind": "none"},
            "rest_after_seconds": rest_seconds,
        }
        segments.append(segment)
    return {"version": 1, "metric_type": "strength", "segments": segments, "groups": []}


def _straight_plan(
    sets: int,
    reps: str,
    rest_seconds: int,
    *,
    load_kind: str = "user_selected",
    load_value: float | None = None,
) -> dict[str, object]:
    if "-" in reps:
        minimum, maximum = (int(value) for value in reps.split("-", maxsplit=1))
        target = _range_reps(minimum, maximum)
    else:
        target = _exact_reps(int(reps))
    return _strength_plan(
        [target for _ in range(sets)],
        rest_seconds,
        loads=[_load_target(load_kind, load_value) for _ in range(sets)],
    )


def _amrap_last_plan(
    sets: int,
    reps: int,
    rest_seconds: int,
    *,
    load_kind: str = "user_selected",
    load_value: float | None = None,
) -> dict[str, object]:
    targets = [_exact_reps(reps) for _ in range(max(sets - 1, 0))]
    targets.append(_amrap_reps())
    return _strength_plan(
        targets,
        rest_seconds,
        loads=[_load_target(load_kind, load_value) for _ in range(sets)],
    )


def _capped_amrap_plan(sets: int, cap_reps: int, rest_seconds: int) -> dict[str, object]:
    return _strength_plan(
        [_amrap_reps(cap_reps) for _ in range(sets)],
        rest_seconds,
    )


def _training_max_plan(
    percentages: list[float],
    reps: list[int | None],
    rest_seconds: int,
) -> dict[str, object]:
    targets = [_amrap_reps() if value is None else _exact_reps(value) for value in reps]
    return _strength_plan(
        targets,
        rest_seconds,
        loads=[_load_target("percent_training_max", value) for value in percentages],
    )


def _seed_exercise(
    slug: str,
    sets: int,
    reps: str,
    rest_seconds: int,
    *,
    plan: dict[str, object] | None = None,
    group_id: int | None = None,
    group_kind: str | None = None,
    group_order: int | None = None,
    notes: str | None = None,
    weekly_plans: list[dict[str, object]] | None = None,
) -> TemplateExerciseSeed:
    metadata: TemplateExerciseMetadata = {}
    if plan is not None:
        metadata["prescription"] = plan
    if group_id is not None:
        metadata["group_id"] = group_id
        metadata["group_kind"] = group_kind
        metadata["group_order"] = group_order
    if notes is not None:
        metadata["notes"] = notes
    if weekly_plans is not None:
        metadata["weekly_plans"] = weekly_plans
    return (slug, sets, reps, rest_seconds, metadata)


def _source_provenance(
    *,
    source_program_name: str,
    creator: str,
    community: str | None,
    canonical_source: str,
    source_version: str,
    adaptation_notes: str,
    adaptation_ledger: list[dict[str, object]],
    exercise_mapping: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "source_program_name": source_program_name,
        "creator": creator,
        "community": community,
        "canonical_source": canonical_source,
        "source_version": source_version,
        "retrieved_date": "2026-09-21",
        "provenance_type": "SOURCE_ADAPTATION",
        "reference_reuse_status": "PUBLIC_REFERENCE_ONLY_NO_REDISTRIBUTION_LICENSE_VERIFIED",
        "adaptation_status": "ADAPTED",
        "adaptation_notes": adaptation_notes,
        "representability_status": "WITH_DECLARED_ADAPTATION",
        "source_revision_evidence": canonical_source,
        "mapping_gate": {
            "stages": [
                "source_exercise",
                "canonical_slug",
                "alias",
                "variant",
                "exercise_metadata",
                "movement_equipment_validation",
            ],
            "known_false_gaps": [
                "single-leg-rdl",
                "skull-crusher",
                "glute-ham-raise",
                "chest-dip",
                "weighted-dip",
                "rear-delt-fly",
            ],
            "genuine_gaps": ["power-clean", "dumbbell-floor-press"],
        },
        "deferred_library_ledger": [
            {"program": "Starting Strength", "status": "DEFERRED"},
            {"program": "PHAT", "status": "DEFERRED"},
            {"program": "Dumbbell Stopgap", "status": "DEFERRED"},
            {"program": "r/Fitness Basic Beginner", "status": "DEFERRED"},
            {"program": "Greyskull LP", "status": "DEFERRED"},
            {"program": "Frankoman DB Only", "status": "DEFERRED"},
            {"program": "SBS / Greg Nuckols collections", "status": "DEFERRED"},
            {"program": "Strong Curves", "status": "DEFERRED"},
            {"program": "WS4SB", "status": "DEFERRED"},
            {"program": "Arnold-style", "status": "DEFERRED"},
            {"program": "Deep Water", "status": "DEFERRED"},
        ],
        "adaptation_ledger": adaptation_ledger,
        "exercise_mapping": exercise_mapping,
    }


def _product_metadata(
    *,
    level: str,
    goal: str,
    days_per_week: int,
    representation_days: int,
    split: str,
    equipment: list[str],
    progression_style: str,
    cycle_length_weeks: int | None,
    advanced_methods: list[str],
    frequency_model: str,
    expected_duration_minutes: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "level": level,
        "goal": goal,
        "days_per_week": days_per_week,
        "representation_days": representation_days,
        "split": split,
        "equipment": equipment,
        "progression_style": progression_style,
        "cycle_length_weeks": cycle_length_weeks,
        "advanced_method_flags": advanced_methods,
        "frequency_model": frequency_model,
        "expected_duration_minutes": expected_duration_minutes,
    }


def _five_three_one_week(
    percentages: list[float],
    reps: list[int | None],
) -> dict[str, object]:
    return _training_max_plan(percentages, reps, 180)


def _repeat_plan(plan: dict[str, object], weeks: int) -> list[dict[str, object]]:
    return [plan for _ in range(weeks)]


_SOURCE_TEMPLATE_SPECS: list[dict[str, object]] = [
    {
        "slug": "stronglifts-5x5",
        "title": "StrongLifts 5x5",
        "goal": "strength",
        "level": "beginner",
        "split_type": "full_body",
        "default_duration_weeks": 1,
        "provenance": _source_provenance(
            source_program_name="StrongLifts 5x5",
            creator="Mehdi",
            community="StrongLifts",
            canonical_source="https://stronglifts.com/stronglifts-5x5/",
            source_version="official guide accessed 2026-09-21",
            adaptation_notes="Standard A/B 3-session presentation; progression is a manual rule.",
            adaptation_ledger=[
                {"field": "workout_structure", "status": "EXACT"},
                {"field": "session_load_progression", "status": "MANUAL_RULE"},
                {"field": "source_terms", "status": "ADAPTED", "note": "Stored as provenance only"},
            ],
            exercise_mapping={
                "squat": {"canonical_slug": "squat", "status": "EXACT"},
                "bench_press": {"canonical_slug": "bench-press", "status": "EXACT"},
                "barbell_row": {"canonical_slug": "barbell-row", "status": "EXACT"},
                "overhead_press": {"canonical_slug": "overhead-press", "status": "EXACT"},
                "deadlift": {"canonical_slug": "deadlift", "status": "EXACT"},
            },
        ),
        "program_metadata": _product_metadata(
            level="beginner",
            goal="strength",
            days_per_week=3,
            representation_days=2,
            split="full_body",
            equipment=["barbell", "bench", "rack"],
            progression_style="session_to_session_linear",
            cycle_length_weeks=None,
            advanced_methods=[],
            frequency_model="A/B alternating, three sessions per week",
        ),
        "days": [
            (
                "Workout A",
                [
                    _seed_exercise("squat", 5, "5", 150, plan=_straight_plan(5, "5", 150)),
                    _seed_exercise("bench-press", 5, "5", 150, plan=_straight_plan(5, "5", 150)),
                    _seed_exercise("barbell-row", 5, "5", 150, plan=_straight_plan(5, "5", 150)),
                ],
            ),
            (
                "Workout B",
                [
                    _seed_exercise("squat", 5, "5", 150, plan=_straight_plan(5, "5", 150)),
                    _seed_exercise("overhead-press", 5, "5", 150, plan=_straight_plan(5, "5", 150)),
                    _seed_exercise("deadlift", 1, "1", 180, plan=_straight_plan(1, "1", 180)),
                ],
            ),
        ],
    },
    {
        "slug": "gzclp",
        "title": "GZCLP",
        "goal": "strength",
        "level": "beginner",
        "split_type": "full_body",
        "default_duration_weeks": 1,
        "provenance": _source_provenance(
            source_program_name="GZCLP",
            creator="Cody LeFever",
            community="u/gz / Fitness Wiki",
            canonical_source="https://thefitness.wiki/routines/gzclp/",
            source_version="frozen four-workout rotation accessed 2026-09-21",
            adaptation_notes="One deterministic four-workout rotation; stage and stall transitions remain manual.",
            adaptation_ledger=[
                {"field": "tier_roles", "status": "EXACT"},
                {"field": "amrap_sets", "status": "EXACT"},
                {"field": "stage_reset", "status": "MANUAL_RULE"},
            ],
            exercise_mapping={
                "squat": {"canonical_slug": "squat", "status": "EXACT"},
                "bench_press": {"canonical_slug": "bench-press", "status": "EXACT"},
                "overhead_press": {"canonical_slug": "overhead-press", "status": "EXACT"},
                "deadlift": {"canonical_slug": "deadlift", "status": "EXACT"},
                "lat_pulldown": {"canonical_slug": "lat-pulldown", "status": "EXACT"},
                "one_arm_dumbbell_row": {
                    "canonical_slug": "one-arm-dumbbell-row",
                    "status": "ADAPTED",
                    "note": "DB row variant selected for the T3 row slot.",
                },
            },
        ),
        "program_metadata": _product_metadata(
            level="beginner",
            goal="strength",
            days_per_week=3,
            representation_days=4,
            split="full_body",
            equipment=["barbell", "bench", "cable", "dumbbell"],
            progression_style="tiered_t1_t2_t3_amrap",
            cycle_length_weeks=None,
            advanced_methods=["amrap"],
            frequency_model="three sessions per week rotating through four workouts",
        ),
        "days": [
            (
                "Workout 1",
                [
                    _seed_exercise(
                        "squat",
                        5,
                        "3+",
                        180,
                        plan=_amrap_last_plan(5, 3, 180),
                        notes="T1; last set AMRAP",
                    ),
                    _seed_exercise(
                        "bench-press",
                        3,
                        "10",
                        120,
                        plan=_straight_plan(3, "10", 120),
                        notes="T2",
                    ),
                    _seed_exercise(
                        "lat-pulldown",
                        3,
                        "15+",
                        75,
                        plan=_amrap_last_plan(3, 15, 75),
                        notes="T3; last set AMRAP",
                    ),
                ],
            ),
            (
                "Workout 2",
                [
                    _seed_exercise(
                        "overhead-press",
                        5,
                        "3+",
                        180,
                        plan=_amrap_last_plan(5, 3, 180),
                        notes="T1; last set AMRAP",
                    ),
                    _seed_exercise(
                        "deadlift",
                        3,
                        "10",
                        150,
                        plan=_straight_plan(3, "10", 150),
                        notes="T2",
                    ),
                    _seed_exercise(
                        "one-arm-dumbbell-row",
                        3,
                        "15+",
                        75,
                        plan=_amrap_last_plan(3, 15, 75),
                        notes="T3; selected DB row variant; last set AMRAP",
                    ),
                ],
            ),
            (
                "Workout 3",
                [
                    _seed_exercise(
                        "bench-press",
                        5,
                        "3+",
                        180,
                        plan=_amrap_last_plan(5, 3, 180),
                        notes="T1; last set AMRAP",
                    ),
                    _seed_exercise(
                        "squat",
                        3,
                        "10",
                        120,
                        plan=_straight_plan(3, "10", 120),
                        notes="T2",
                    ),
                    _seed_exercise(
                        "lat-pulldown",
                        3,
                        "15+",
                        75,
                        plan=_amrap_last_plan(3, 15, 75),
                        notes="T3; last set AMRAP",
                    ),
                ],
            ),
            (
                "Workout 4",
                [
                    _seed_exercise(
                        "deadlift",
                        5,
                        "3+",
                        210,
                        plan=_amrap_last_plan(5, 3, 210),
                        notes="T1; last set AMRAP",
                    ),
                    _seed_exercise(
                        "overhead-press",
                        3,
                        "10",
                        120,
                        plan=_straight_plan(3, "10", 120),
                        notes="T2",
                    ),
                    _seed_exercise(
                        "one-arm-dumbbell-row",
                        3,
                        "15+",
                        75,
                        plan=_amrap_last_plan(3, 15, 75),
                        notes="T3; selected DB row variant; last set AMRAP",
                    ),
                ],
            ),
        ],
    },
    {
        "slug": "531-for-beginners",
        "title": "5/3/1 for Beginners",
        "goal": "strength",
        "level": "beginner",
        "split_type": "full_body",
        "default_duration_weeks": 4,
        "provenance": _source_provenance(
            source_program_name="5/3/1 for Beginners",
            creator="Jim Wendler",
            community=None,
            canonical_source="https://www.jimwendler.com/blogs/jimwendler-com/101065094-5-3-1-for-a-beginner",
            source_version="official article accessed 2026-09-21",
            adaptation_notes="Four-week fixed YFC block; Training Max is explicit and updates remain manual.",
            adaptation_ledger=[
                {"field": "three_training_days", "status": "EXACT"},
                {"field": "two_main_lifts_per_day", "status": "EXACT"},
                {"field": "training_max_basis", "status": "EXACT"},
                {"field": "first_set_last", "status": "EXACT"},
                {"field": "training_max_update", "status": "MANUAL_RULE"},
                {"field": "assistance_selection", "status": "ADAPTED"},
            ],
            exercise_mapping={
                "squat": {"canonical_slug": "squat", "status": "EXACT"},
                "bench_press": {"canonical_slug": "bench-press", "status": "EXACT"},
                "deadlift": {"canonical_slug": "deadlift", "status": "EXACT"},
                "overhead_press": {"canonical_slug": "overhead-press", "status": "EXACT"},
                "barbell_row": {"canonical_slug": "barbell-row", "status": "ADAPTED"},
                "pull_up": {"canonical_slug": "pull-up", "status": "EXACT"},
            },
        ),
        "program_metadata": _product_metadata(
            level="beginner",
            goal="strength",
            days_per_week=3,
            representation_days=3,
            split="full_body",
            equipment=["barbell", "bench", "rack", "bodyweight"],
            progression_style="531_training_max_fsl",
            cycle_length_weeks=4,
            advanced_methods=[],
            frequency_model="three training days",
        ),
        "days": [
            (
                "Day 1 · Squat + Bench",
                [
                    _seed_exercise(
                        "squat",
                        3,
                        "5/3/1",
                        180,
                        plan=_five_three_one_week([65, 75, 85], [5, 5, None]),
                        weekly_plans=[
                            _five_three_one_week([65, 75, 85], [5, 5, None]),
                            _five_three_one_week([70, 80, 90], [3, 3, None]),
                            _five_three_one_week([75, 85, 95], [5, 3, None]),
                            _five_three_one_week([40, 50, 60], [5, 5, 5]),
                        ],
                        notes="Main lift; percentage basis is TRAINING_MAX",
                    ),
                    _seed_exercise(
                        "squat",
                        5,
                        "5",
                        90,
                        plan=_straight_plan(
                            5, "5", 90, load_kind="percent_training_max", load_value=65
                        ),
                        weekly_plans=[
                            _straight_plan(
                                5, "5", 90, load_kind="percent_training_max", load_value=65
                            ),
                            _straight_plan(
                                5, "5", 90, load_kind="percent_training_max", load_value=70
                            ),
                            _straight_plan(
                                5, "5", 90, load_kind="percent_training_max", load_value=75
                            ),
                            _straight_plan(
                                5, "5", 90, load_kind="percent_training_max", load_value=40
                            ),
                        ],
                        notes="FSL; first-set Training Max load",
                    ),
                    _seed_exercise(
                        "bench-press",
                        3,
                        "5/3/1",
                        180,
                        plan=_five_three_one_week([65, 75, 85], [5, 5, None]),
                        weekly_plans=[
                            _five_three_one_week([65, 75, 85], [5, 5, None]),
                            _five_three_one_week([70, 80, 90], [3, 3, None]),
                            _five_three_one_week([75, 85, 95], [5, 3, None]),
                            _five_three_one_week([40, 50, 60], [5, 5, 5]),
                        ],
                        notes="Main lift; percentage basis is TRAINING_MAX",
                    ),
                ],
            ),
            (
                "Day 2 · Deadlift + Overhead Press",
                [
                    _seed_exercise(
                        "deadlift",
                        3,
                        "5/3/1",
                        210,
                        plan=_five_three_one_week([65, 75, 85], [5, 5, None]),
                        weekly_plans=[
                            _five_three_one_week([65, 75, 85], [5, 5, None]),
                            _five_three_one_week([70, 80, 90], [3, 3, None]),
                            _five_three_one_week([75, 85, 95], [5, 3, None]),
                            _five_three_one_week([40, 50, 60], [5, 5, 5]),
                        ],
                        notes="Main lift; percentage basis is TRAINING_MAX",
                    ),
                    _seed_exercise(
                        "overhead-press",
                        3,
                        "5/3/1",
                        180,
                        plan=_five_three_one_week([65, 75, 85], [5, 5, None]),
                        weekly_plans=[
                            _five_three_one_week([65, 75, 85], [5, 5, None]),
                            _five_three_one_week([70, 80, 90], [3, 3, None]),
                            _five_three_one_week([75, 85, 95], [5, 3, None]),
                            _five_three_one_week([40, 50, 60], [5, 5, 5]),
                        ],
                        notes="Main lift; percentage basis is TRAINING_MAX",
                    ),
                    _seed_exercise(
                        "pull-up",
                        3,
                        "6-10",
                        90,
                        plan=_straight_plan(3, "6-10", 90),
                        notes="Assistance boundary",
                    ),
                ],
            ),
            (
                "Day 3 · Bench + Squat",
                [
                    _seed_exercise(
                        "bench-press",
                        3,
                        "5/3/1",
                        180,
                        plan=_five_three_one_week([65, 75, 85], [5, 5, None]),
                        weekly_plans=[
                            _five_three_one_week([65, 75, 85], [5, 5, None]),
                            _five_three_one_week([70, 80, 90], [3, 3, None]),
                            _five_three_one_week([75, 85, 95], [5, 3, None]),
                            _five_three_one_week([40, 50, 60], [5, 5, 5]),
                        ],
                        notes="Main lift; percentage basis is TRAINING_MAX",
                    ),
                    _seed_exercise(
                        "squat",
                        3,
                        "5/3/1",
                        180,
                        plan=_five_three_one_week([65, 75, 85], [5, 5, None]),
                        weekly_plans=[
                            _five_three_one_week([65, 75, 85], [5, 5, None]),
                            _five_three_one_week([70, 80, 90], [3, 3, None]),
                            _five_three_one_week([75, 85, 95], [5, 3, None]),
                            _five_three_one_week([40, 50, 60], [5, 5, 5]),
                        ],
                        notes="Main lift; percentage basis is TRAINING_MAX",
                    ),
                    _seed_exercise(
                        "barbell-row",
                        3,
                        "8-12",
                        90,
                        plan=_straight_plan(3, "8-12", 90),
                        notes="Assistance boundary",
                    ),
                ],
            ),
        ],
    },
    {
        "slug": "phul",
        "title": "PHUL",
        "goal": "muscle_gain",
        "level": "intermediate",
        "split_type": "upper_lower",
        "default_duration_weeks": 12,
        "provenance": _source_provenance(
            source_program_name="Power Hypertrophy Upper Lower",
            creator="Brandon Campbell",
            community="Muscle & Strength",
            canonical_source="https://www.muscleandstrength.com/workouts/phul-workout",
            source_version="published 2013-02-15; updated 2021-05-26; accessed 2026-09-21",
            adaptation_notes="Source set ranges are retained in typed plans; lower bound is selected deterministically for stored set count.",
            adaptation_ledger=[
                {"field": "four_day_split", "status": "EXACT"},
                {"field": "twelve_week_duration", "status": "EXACT"},
                {
                    "field": "set_range_materialization",
                    "status": "ADAPTED",
                    "decision": "lower bound",
                },
                {"field": "source_terms", "status": "ADAPTED", "note": "Stored as provenance only"},
            ],
            exercise_mapping={
                "skull_crusher": {"canonical_slug": "skull-crusher", "status": "EXACT"},
                "rear_delt_fly": {"canonical_slug": "rear-delt-fly", "status": "EXACT"},
                "standing_calf_raise": {"canonical_slug": "standing-calf-raise", "status": "EXACT"},
                "remaining_source_rows": {
                    "status": "ADAPTED",
                    "note": "Every stored row is validated against the canonical catalog before seeding",
                },
            },
        ),
        "program_metadata": _product_metadata(
            level="intermediate",
            goal="muscle_gain",
            days_per_week=4,
            representation_days=4,
            split="upper_lower",
            equipment=["barbell", "dumbbell", "bench", "cable", "machine"],
            progression_style="power_hypertrophy_fixed_ranges",
            cycle_length_weeks=12,
            advanced_methods=[],
            frequency_model="four training days",
            expected_duration_minutes={"min": 45, "max": 60},
        ),
        "days": [
            (
                "Upper Power",
                [
                    _seed_exercise(
                        "bench-press",
                        4,
                        "4-6",
                        150,
                        plan=_straight_plan(4, "4-6", 150),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "incline-bench-press",
                        4,
                        "6-8",
                        120,
                        plan=_straight_plan(4, "6-8", 120),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "barbell-row",
                        4,
                        "4-6",
                        150,
                        plan=_straight_plan(4, "4-6", 150),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "overhead-press",
                        3,
                        "6-8",
                        120,
                        plan=_straight_plan(3, "6-8", 120),
                        notes="Source range; 3 sets selected",
                    ),
                    _seed_exercise(
                        "barbell-curl",
                        3,
                        "8-10",
                        90,
                        plan=_straight_plan(3, "8-10", 90),
                        notes="Source range; 3 sets selected",
                    ),
                    _seed_exercise(
                        "skull-crusher",
                        3,
                        "8-10",
                        90,
                        plan=_straight_plan(3, "8-10", 90),
                        notes="Source range; 3 sets selected",
                    ),
                ],
            ),
            (
                "Lower Power",
                [
                    _seed_exercise(
                        "squat",
                        4,
                        "4-6",
                        180,
                        plan=_straight_plan(4, "4-6", 180),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "deadlift",
                        3,
                        "3-5",
                        210,
                        plan=_straight_plan(3, "3-5", 210),
                        notes="Source range; 3 sets selected",
                    ),
                    _seed_exercise(
                        "leg-press",
                        4,
                        "8-10",
                        120,
                        plan=_straight_plan(4, "8-10", 120),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "leg-curl",
                        3,
                        "8-10",
                        90,
                        plan=_straight_plan(3, "8-10", 90),
                        notes="Source range; 3 sets selected",
                    ),
                    _seed_exercise(
                        "standing-calf-raise",
                        4,
                        "10-15",
                        60,
                        plan=_straight_plan(4, "10-15", 60),
                        notes="Source range; 4 sets selected",
                    ),
                ],
            ),
            (
                "Upper Hypertrophy",
                [
                    _seed_exercise(
                        "incline-dumbbell-press",
                        4,
                        "8-12",
                        120,
                        plan=_straight_plan(4, "8-12", 120),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "dumbbell-bench-press",
                        4,
                        "8-12",
                        120,
                        plan=_straight_plan(4, "8-12", 120),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "machine-row",
                        4,
                        "8-12",
                        90,
                        plan=_straight_plan(4, "8-12", 90),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "lat-pulldown",
                        4,
                        "8-12",
                        90,
                        plan=_straight_plan(4, "8-12", 90),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "dumbbell-lateral-raise",
                        3,
                        "10-15",
                        60,
                        plan=_straight_plan(3, "10-15", 60),
                        notes="Source range; 3 sets selected",
                    ),
                    _seed_exercise(
                        "rope-pushdown",
                        3,
                        "10-15",
                        75,
                        plan=_straight_plan(3, "10-15", 75),
                        notes="Source range; 3 sets selected",
                    ),
                ],
            ),
            (
                "Lower Hypertrophy",
                [
                    _seed_exercise(
                        "front-squat",
                        4,
                        "8-12",
                        150,
                        plan=_straight_plan(4, "8-12", 150),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "romanian-deadlift",
                        4,
                        "8-12",
                        120,
                        plan=_straight_plan(4, "8-12", 120),
                        notes="Source range; 4 sets selected",
                    ),
                    _seed_exercise(
                        "bulgarian-split-squat",
                        3,
                        "8-12",
                        120,
                        plan=_straight_plan(3, "8-12", 120),
                        notes="Source range; 3 sets selected",
                    ),
                    _seed_exercise(
                        "leg-extension",
                        3,
                        "10-15",
                        75,
                        plan=_straight_plan(3, "10-15", 75),
                        notes="Source range; 3 sets selected",
                    ),
                    _seed_exercise(
                        "seated-leg-curl",
                        3,
                        "10-15",
                        75,
                        plan=_straight_plan(3, "10-15", 75),
                        notes="Source range; 3 sets selected",
                    ),
                    _seed_exercise(
                        "seated-calf-raise",
                        4,
                        "10-15",
                        60,
                        plan=_straight_plan(4, "10-15", 60),
                        notes="Source range; 4 sets selected",
                    ),
                ],
            ),
        ],
    },
    {
        "slug": "nsuns-4d",
        "title": "nSuns 4-day",
        "goal": "strength",
        "level": "intermediate",
        "split_type": "hybrid",
        "default_duration_weeks": 1,
        "provenance": _source_provenance(
            source_program_name="nSuns Linear Progression 4-day",
            creator="u/nSuns",
            community="public Fitness Wiki archive",
            canonical_source="https://thefitness.wiki/routines/nsuns-lp/",
            source_version="frozen 4-day YFC variant from public archive accessed 2026-09-21",
            adaptation_notes="One frozen ordered percentage/AMRAP representation; optional accessories are intentionally omitted.",
            adaptation_ledger=[
                {"field": "two_programmed_lifts_per_day", "status": "EXACT"},
                {"field": "ordered_percentage_prescriptions", "status": "ADAPTED"},
                {"field": "training_max_basis", "status": "EXACT"},
                {"field": "amrap_progression", "status": "MANUAL_RULE"},
                {
                    "field": "optional_accessories",
                    "status": "UNSUPPORTED",
                    "blocking": False,
                    "note": "Not presented as official rows",
                },
            ],
            exercise_mapping={
                "bench_press": {"canonical_slug": "bench-press", "status": "EXACT"},
                "overhead_press": {"canonical_slug": "overhead-press", "status": "EXACT"},
                "squat": {"canonical_slug": "squat", "status": "EXACT"},
                "deadlift": {"canonical_slug": "deadlift", "status": "EXACT"},
                "sumo_deadlift": {"canonical_slug": "sumo-deadlift", "status": "EXACT"},
            },
        ),
        "program_metadata": _product_metadata(
            level="intermediate",
            goal="strength",
            days_per_week=4,
            representation_days=4,
            split="hybrid",
            equipment=["barbell", "bench", "rack"],
            progression_style="ordered_percentage_training_max_amrap",
            cycle_length_weeks=None,
            advanced_methods=["amrap"],
            frequency_model="four training days",
        ),
        "days": [
            (
                "Day 1 · Bench + OHP",
                [
                    _seed_exercise(
                        "bench-press",
                        7,
                        "5+",
                        180,
                        plan=_training_max_plan(
                            [75, 80, 85, 75, 80, 85, 90], [5, 5, 5, 5, 5, 5, None], 180
                        ),
                        notes="T1; ordered TRAINING_MAX loads; final AMRAP",
                    ),
                    _seed_exercise(
                        "overhead-press",
                        6,
                        "8-4",
                        120,
                        plan=_strength_plan(
                            [
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _amrap_reps(),
                            ],
                            120,
                            loads=[
                                _load_target("percent_training_max", value)
                                for value in [65, 70, 75, 65, 70, 75]
                            ],
                        ),
                        notes="T2; ordered TRAINING_MAX loads; final AMRAP",
                    ),
                ],
            ),
            (
                "Day 2 · Squat + Sumo Deadlift",
                [
                    _seed_exercise(
                        "squat",
                        7,
                        "5+",
                        180,
                        plan=_training_max_plan(
                            [75, 80, 85, 75, 80, 85, 90], [5, 5, 5, 5, 5, 5, None], 180
                        ),
                        notes="T1; ordered TRAINING_MAX loads; final AMRAP",
                    ),
                    _seed_exercise(
                        "sumo-deadlift",
                        6,
                        "8-4",
                        150,
                        plan=_strength_plan(
                            [
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _amrap_reps(),
                            ],
                            150,
                            loads=[
                                _load_target("percent_training_max", value)
                                for value in [65, 70, 75, 65, 70, 75]
                            ],
                        ),
                        notes="T2; ordered TRAINING_MAX loads; final AMRAP",
                    ),
                ],
            ),
            (
                "Day 3 · OHP + Bench",
                [
                    _seed_exercise(
                        "overhead-press",
                        7,
                        "5+",
                        150,
                        plan=_training_max_plan(
                            [75, 80, 85, 75, 80, 85, 90], [5, 5, 5, 5, 5, 5, None], 150
                        ),
                        notes="T1; ordered TRAINING_MAX loads; final AMRAP",
                    ),
                    _seed_exercise(
                        "bench-press",
                        6,
                        "8-4",
                        120,
                        plan=_strength_plan(
                            [
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _amrap_reps(),
                            ],
                            120,
                            loads=[
                                _load_target("percent_training_max", value)
                                for value in [65, 70, 75, 65, 70, 75]
                            ],
                        ),
                        notes="T2; ordered TRAINING_MAX loads; final AMRAP",
                    ),
                ],
            ),
            (
                "Day 4 · Deadlift + Squat",
                [
                    _seed_exercise(
                        "deadlift",
                        7,
                        "5+",
                        210,
                        plan=_training_max_plan(
                            [75, 80, 85, 75, 80, 85, 90], [5, 5, 5, 5, 5, 5, None], 210
                        ),
                        notes="T1; ordered TRAINING_MAX loads; final AMRAP",
                    ),
                    _seed_exercise(
                        "squat",
                        6,
                        "8-4",
                        150,
                        plan=_strength_plan(
                            [
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _range_reps(4, 8),
                                _amrap_reps(),
                            ],
                            150,
                            loads=[
                                _load_target("percent_training_max", value)
                                for value in [65, 70, 75, 65, 70, 75]
                            ],
                        ),
                        notes="T2; ordered TRAINING_MAX loads; final AMRAP",
                    ),
                ],
            ),
        ],
    },
    {
        "slug": "metallicdpa-linear-progression-ppl",
        "title": "Metallicdpa Linear Progression PPL",
        "goal": "muscle_gain",
        "level": "beginner",
        "split_type": "push_pull_legs",
        "default_duration_weeks": 1,
        "provenance": _source_provenance(
            source_program_name="A Linear Progression Based PPL Program for Beginners",
            creator="u/Metallicdpa",
            community="r/Fitness public archive",
            canonical_source="https://thefitness.wiki/reddit-archive/a-linear-progression-based-ppl-program-for-beginners/",
            source_version="public archive accessed 2026-09-21",
            adaptation_notes="Six-day PPL representation; source deload remains a manual rule.",
            adaptation_ledger=[
                {"field": "six_day_ppl", "status": "EXACT"},
                {"field": "alternating_main_lifts", "status": "ADAPTED"},
                {"field": "final_set_amrap", "status": "EXACT"},
                {"field": "linear_progression", "status": "MANUAL_RULE"},
                {"field": "deload", "status": "MANUAL_RULE"},
            ],
            exercise_mapping={
                "bench_press": {"canonical_slug": "bench-press", "status": "EXACT"},
                "barbell_row": {"canonical_slug": "barbell-row", "status": "EXACT"},
                "squat": {"canonical_slug": "squat", "status": "EXACT"},
                "deadlift": {"canonical_slug": "deadlift", "status": "EXACT"},
                "pull_up": {"canonical_slug": "pull-up", "status": "EXACT"},
            },
        ),
        "program_metadata": _product_metadata(
            level="beginner",
            goal="muscle_gain",
            days_per_week=6,
            representation_days=6,
            split="push_pull_legs",
            equipment=["barbell", "dumbbell", "bench", "cable"],
            progression_style="linear_main_lift_amrap",
            cycle_length_weeks=None,
            advanced_methods=["amrap"],
            frequency_model="six training days",
        ),
        "days": [
            (
                "Pull A",
                [
                    _seed_exercise(
                        "deadlift",
                        3,
                        "5+",
                        180,
                        plan=_amrap_last_plan(3, 5, 180),
                        notes="Main lift; final set AMRAP",
                    ),
                    _seed_exercise(
                        "barbell-row", 3, "8-12", 120, plan=_straight_plan(3, "8-12", 120)
                    ),
                    _seed_exercise("pull-up", 3, "6-10", 120, plan=_straight_plan(3, "6-10", 120)),
                    _seed_exercise(
                        "barbell-curl", 3, "8-12", 90, plan=_straight_plan(3, "8-12", 90)
                    ),
                ],
            ),
            (
                "Push A",
                [
                    _seed_exercise(
                        "bench-press",
                        3,
                        "5+",
                        150,
                        plan=_amrap_last_plan(3, 5, 150),
                        notes="Main lift; final set AMRAP",
                    ),
                    _seed_exercise(
                        "overhead-press", 3, "6-10", 120, plan=_straight_plan(3, "6-10", 120)
                    ),
                    _seed_exercise(
                        "incline-bench-press", 3, "8-12", 120, plan=_straight_plan(3, "8-12", 120)
                    ),
                    _seed_exercise(
                        "rope-pushdown", 3, "10-15", 75, plan=_straight_plan(3, "10-15", 75)
                    ),
                ],
            ),
            (
                "Legs A",
                [
                    _seed_exercise(
                        "squat",
                        3,
                        "5+",
                        180,
                        plan=_amrap_last_plan(3, 5, 180),
                        notes="Main lift; final set AMRAP",
                    ),
                    _seed_exercise(
                        "romanian-deadlift", 3, "8-12", 120, plan=_straight_plan(3, "8-12", 120)
                    ),
                    _seed_exercise(
                        "leg-press", 3, "10-15", 120, plan=_straight_plan(3, "10-15", 120)
                    ),
                    _seed_exercise(
                        "standing-calf-raise", 3, "12-20", 60, plan=_straight_plan(3, "12-20", 60)
                    ),
                ],
            ),
            (
                "Pull B",
                [
                    _seed_exercise(
                        "barbell-row",
                        3,
                        "5+",
                        150,
                        plan=_amrap_last_plan(3, 5, 150),
                        notes="Alternating main lift; final set AMRAP",
                    ),
                    _seed_exercise(
                        "one-arm-dumbbell-row", 3, "8-12", 90, plan=_straight_plan(3, "8-12", 90)
                    ),
                    _seed_exercise(
                        "lat-pulldown", 3, "8-12", 90, plan=_straight_plan(3, "8-12", 90)
                    ),
                    _seed_exercise(
                        "hammer-curl", 3, "10-15", 75, plan=_straight_plan(3, "10-15", 75)
                    ),
                ],
            ),
            (
                "Push B",
                [
                    _seed_exercise(
                        "incline-bench-press",
                        3,
                        "5+",
                        150,
                        plan=_amrap_last_plan(3, 5, 150),
                        notes="Alternating main lift; final set AMRAP",
                    ),
                    _seed_exercise(
                        "seated-dumbbell-press", 3, "8-12", 120, plan=_straight_plan(3, "8-12", 120)
                    ),
                    _seed_exercise(
                        "weighted-dip", 3, "8-12", 120, plan=_straight_plan(3, "8-12", 120)
                    ),
                    _seed_exercise(
                        "dumbbell-lateral-raise",
                        3,
                        "12-20",
                        60,
                        plan=_straight_plan(3, "12-20", 60),
                    ),
                ],
            ),
            (
                "Legs B",
                [
                    _seed_exercise(
                        "front-squat",
                        3,
                        "5+",
                        180,
                        plan=_amrap_last_plan(3, 5, 180),
                        notes="Alternating main lift; final set AMRAP",
                    ),
                    _seed_exercise(
                        "bulgarian-split-squat", 3, "8-12", 120, plan=_straight_plan(3, "8-12", 120)
                    ),
                    _seed_exercise("leg-curl", 3, "10-15", 90, plan=_straight_plan(3, "10-15", 90)),
                    _seed_exercise(
                        "seated-calf-raise", 3, "12-20", 60, plan=_straight_plan(3, "12-20", 60)
                    ),
                ],
            ),
        ],
    },
    {
        "slug": "bwf-recommended-routine",
        "title": "BWF Recommended Routine",
        "goal": "muscle_gain",
        "level": "beginner",
        "split_type": "full_body",
        "default_duration_weeks": 1,
        "provenance": _source_provenance(
            source_program_name="Recommended Routine",
            creator="r/bodyweightfitness community",
            community="Reddit bodyweightfitness wiki",
            canonical_source="https://old.reddit.com/r/bodyweightfitness/wiki/kb/recommended_routine",
            source_version="source-dated selected path accessed 2026-09-21",
            adaptation_notes="One fixed dynamic progression path selected; the evolving progression tree and isometric alternatives are not reproduced.",
            adaptation_ledger=[
                {"field": "bodyweight_identity", "status": "EXACT"},
                {"field": "paired_exercises", "status": "EXACT"},
                {"field": "selected_progression_path", "status": "ADAPTED"},
                {
                    "field": "dynamic_progression_tree",
                    "status": "UNSUPPORTED",
                    "blocking": False,
                    "note": "Not claimed as reproduced",
                },
                {
                    "field": "isometric_alternatives",
                    "status": "ADAPTED",
                    "note": "Fixed dynamic core path selected",
                },
            ],
            exercise_mapping={
                "vertical_pull": {"canonical_slug": "pull-up", "status": "EXACT"},
                "horizontal_push": {"canonical_slug": "push-up", "status": "EXACT"},
                "horizontal_pull": {"canonical_slug": "inverted-row", "status": "EXACT"},
                "squat_progression": {"canonical_slug": "split-squat", "status": "ADAPTED"},
                "hinge_progression": {
                    "canonical_slug": "bodyweight-glute-bridge",
                    "status": "ADAPTED",
                },
                "core_progression": {"canonical_slug": "dead-bug", "status": "ADAPTED"},
            },
        ),
        "program_metadata": _product_metadata(
            level="beginner",
            goal="muscle_gain",
            days_per_week=3,
            representation_days=3,
            split="full_body",
            equipment=["bodyweight", "bench"],
            progression_style="fixed_bodyweight_variation_path",
            cycle_length_weeks=None,
            advanced_methods=["paired_groups"],
            frequency_model="three training days",
        ),
        "days": [
            (
                "Recommended Routine A",
                [
                    _seed_exercise(
                        "pull-up",
                        3,
                        "5-8",
                        90,
                        plan=_straight_plan(3, "5-8", 90),
                        group_id=1,
                        group_kind="superset",
                        group_order=1,
                    ),
                    _seed_exercise(
                        "push-up",
                        3,
                        "5-8",
                        90,
                        plan=_straight_plan(3, "5-8", 90),
                        group_id=1,
                        group_kind="superset",
                        group_order=2,
                    ),
                    _seed_exercise(
                        "split-squat",
                        3,
                        "8-12",
                        90,
                        plan=_straight_plan(3, "8-12", 90),
                        group_id=2,
                        group_kind="superset",
                        group_order=1,
                    ),
                    _seed_exercise(
                        "inverted-row",
                        3,
                        "8-12",
                        90,
                        plan=_straight_plan(3, "8-12", 90),
                        group_id=2,
                        group_kind="superset",
                        group_order=2,
                    ),
                    _seed_exercise(
                        "bodyweight-glute-bridge",
                        3,
                        "8-12",
                        60,
                        plan=_straight_plan(3, "8-12", 60),
                        group_id=3,
                        group_kind="circuit",
                        group_order=1,
                    ),
                    _seed_exercise(
                        "dead-bug",
                        3,
                        "8-12",
                        60,
                        plan=_straight_plan(3, "8-12", 60),
                        group_id=3,
                        group_kind="circuit",
                        group_order=2,
                    ),
                    _seed_exercise(
                        "reverse-crunch",
                        3,
                        "8-12",
                        60,
                        plan=_straight_plan(3, "8-12", 60),
                        group_id=3,
                        group_kind="circuit",
                        group_order=3,
                    ),
                ],
            ),
            (
                "Recommended Routine B",
                [
                    _seed_exercise(
                        "inverted-row",
                        3,
                        "8-12",
                        90,
                        plan=_straight_plan(3, "8-12", 90),
                        group_id=4,
                        group_kind="superset",
                        group_order=1,
                    ),
                    _seed_exercise(
                        "push-up",
                        3,
                        "8-12",
                        90,
                        plan=_straight_plan(3, "8-12", 90),
                        group_id=4,
                        group_kind="superset",
                        group_order=2,
                    ),
                    _seed_exercise(
                        "split-squat",
                        3,
                        "8-12",
                        90,
                        plan=_straight_plan(3, "8-12", 90),
                        group_id=5,
                        group_kind="superset",
                        group_order=1,
                    ),
                    _seed_exercise(
                        "pull-up",
                        3,
                        "5-8",
                        90,
                        plan=_straight_plan(3, "5-8", 90),
                        group_id=5,
                        group_kind="superset",
                        group_order=2,
                    ),
                    _seed_exercise(
                        "bodyweight-glute-bridge",
                        3,
                        "8-12",
                        60,
                        plan=_straight_plan(3, "8-12", 60),
                        group_id=6,
                        group_kind="circuit",
                        group_order=1,
                    ),
                    _seed_exercise(
                        "dead-bug",
                        3,
                        "8-12",
                        60,
                        plan=_straight_plan(3, "8-12", 60),
                        group_id=6,
                        group_kind="circuit",
                        group_order=2,
                    ),
                    _seed_exercise(
                        "reverse-crunch",
                        3,
                        "8-12",
                        60,
                        plan=_straight_plan(3, "8-12", 60),
                        group_id=6,
                        group_kind="circuit",
                        group_order=3,
                    ),
                ],
            ),
            (
                "Recommended Routine C",
                [
                    _seed_exercise(
                        "pull-up",
                        3,
                        "5-8",
                        90,
                        plan=_straight_plan(3, "5-8", 90),
                        group_id=7,
                        group_kind="superset",
                        group_order=1,
                    ),
                    _seed_exercise(
                        "push-up",
                        3,
                        "8-12",
                        90,
                        plan=_straight_plan(3, "8-12", 90),
                        group_id=7,
                        group_kind="superset",
                        group_order=2,
                    ),
                    _seed_exercise(
                        "split-squat",
                        3,
                        "8-12",
                        90,
                        plan=_straight_plan(3, "8-12", 90),
                        group_id=8,
                        group_kind="superset",
                        group_order=1,
                    ),
                    _seed_exercise(
                        "inverted-row",
                        3,
                        "8-12",
                        90,
                        plan=_straight_plan(3, "8-12", 90),
                        group_id=8,
                        group_kind="superset",
                        group_order=2,
                    ),
                    _seed_exercise(
                        "bodyweight-glute-bridge",
                        3,
                        "8-12",
                        60,
                        plan=_straight_plan(3, "8-12", 60),
                        group_id=9,
                        group_kind="circuit",
                        group_order=1,
                    ),
                    _seed_exercise(
                        "dead-bug",
                        3,
                        "8-12",
                        60,
                        plan=_straight_plan(3, "8-12", 60),
                        group_id=9,
                        group_kind="circuit",
                        group_order=2,
                    ),
                    _seed_exercise(
                        "reverse-crunch",
                        3,
                        "8-12",
                        60,
                        plan=_straight_plan(3, "8-12", 60),
                        group_id=9,
                        group_kind="circuit",
                        group_order=3,
                    ),
                ],
            ),
        ],
    },
    {
        "slug": "dumbbell-ppl-gregarioushermit",
        "title": "Dumbbell P/P/L (Proposed Alternative to Dumbbell Stopgap)",
        "goal": "muscle_gain",
        "level": "intermediate",
        "split_type": "push_pull_legs",
        "default_duration_weeks": 1,
        "provenance": _source_provenance(
            source_program_name="Dumbbell P/P/L (Proposed Alternative to Dumbbell Stopgap)",
            creator="u/gregariousHermit",
            community="r/Fitness public archive",
            canonical_source="https://thefitness.wiki/reddit-archive/dumbbell-stopgap-ppl/",
            source_version="public archive accessed 2026-09-21",
            adaptation_notes="Selected deterministic six-day P/P/L/P/P/L/Rest schedule; DB variants and deloads remain explicit adaptations/manual rules.",
            adaptation_ledger=[
                {"field": "dumbbell_hypertrophy_identity", "status": "EXACT"},
                {"field": "six_day_schedule", "status": "ADAPTED", "decision": "P/P/L/P/P/L/Rest"},
                {"field": "rep_cap_progression", "status": "EXACT"},
                {"field": "exercise_deload", "status": "MANUAL_RULE"},
            ],
            exercise_mapping={
                "dumbbell_bench_press": {
                    "canonical_slug": "dumbbell-bench-press",
                    "status": "EXACT",
                },
                "incline_dumbbell_press": {
                    "canonical_slug": "incline-dumbbell-press",
                    "status": "EXACT",
                },
                "one_arm_dumbbell_row": {
                    "canonical_slug": "one-arm-dumbbell-row",
                    "status": "EXACT",
                },
                "chest_supported_dumbbell_row": {
                    "canonical_slug": "chest-supported-dumbbell-row",
                    "status": "EXACT",
                },
                "single_leg_deadlift": {
                    "canonical_slug": "single-leg-rdl",
                    "status": "ADAPTED",
                    "note": "Canonical RDL variant; source intent preserved",
                },
                "rear_delt_fly": {"canonical_slug": "rear-delt-fly", "status": "EXACT"},
            },
        ),
        "program_metadata": _product_metadata(
            level="intermediate",
            goal="muscle_gain",
            days_per_week=6,
            representation_days=6,
            split="push_pull_legs",
            equipment=["dumbbell", "bench", "bodyweight"],
            progression_style="rep_cap_double_progression",
            cycle_length_weeks=None,
            advanced_methods=[],
            frequency_model="six training days followed by rest",
        ),
        "days": [
            (
                "Push A",
                [
                    _seed_exercise(
                        "dumbbell-bench-press",
                        3,
                        "AMRAP 12",
                        120,
                        plan=_capped_amrap_plan(3, 12, 120),
                    ),
                    _seed_exercise(
                        "incline-dumbbell-press",
                        3,
                        "AMRAP 12",
                        120,
                        plan=_capped_amrap_plan(3, 12, 120),
                    ),
                    _seed_exercise(
                        "seated-dumbbell-press",
                        3,
                        "AMRAP 12",
                        90,
                        plan=_capped_amrap_plan(3, 12, 90),
                    ),
                    _seed_exercise(
                        "dumbbell-lateral-raise",
                        3,
                        "AMRAP 12",
                        60,
                        plan=_capped_amrap_plan(3, 12, 60),
                    ),
                    _seed_exercise(
                        "dumbbell-overhead-extension",
                        3,
                        "AMRAP 12",
                        75,
                        plan=_capped_amrap_plan(3, 12, 75),
                    ),
                ],
            ),
            (
                "Pull A",
                [
                    _seed_exercise(
                        "one-arm-dumbbell-row",
                        3,
                        "AMRAP 12",
                        90,
                        plan=_capped_amrap_plan(3, 12, 90),
                    ),
                    _seed_exercise(
                        "chest-supported-dumbbell-row",
                        3,
                        "AMRAP 12",
                        90,
                        plan=_capped_amrap_plan(3, 12, 90),
                    ),
                    _seed_exercise(
                        "rear-delt-fly", 3, "AMRAP 12", 60, plan=_capped_amrap_plan(3, 12, 60)
                    ),
                    _seed_exercise(
                        "dumbbell-curl", 3, "AMRAP 12", 75, plan=_capped_amrap_plan(3, 12, 75)
                    ),
                    _seed_exercise(
                        "dumbbell-shrug", 3, "AMRAP 12", 75, plan=_capped_amrap_plan(3, 12, 75)
                    ),
                ],
            ),
            (
                "Legs A",
                [
                    _seed_exercise(
                        "goblet-squat", 3, "AMRAP 12", 120, plan=_capped_amrap_plan(3, 12, 120)
                    ),
                    _seed_exercise(
                        "single-leg-rdl", 3, "AMRAP 12", 120, plan=_capped_amrap_plan(3, 12, 120)
                    ),
                    _seed_exercise(
                        "walking-lunge", 3, "AMRAP 12", 90, plan=_capped_amrap_plan(3, 12, 90)
                    ),
                    _seed_exercise(
                        "leg-curl", 3, "AMRAP 12", 90, plan=_capped_amrap_plan(3, 12, 90)
                    ),
                    _seed_exercise(
                        "standing-calf-raise", 3, "AMRAP 12", 60, plan=_capped_amrap_plan(3, 12, 60)
                    ),
                ],
            ),
            (
                "Push B",
                [
                    _seed_exercise(
                        "incline-dumbbell-press",
                        3,
                        "AMRAP 12",
                        120,
                        plan=_capped_amrap_plan(3, 12, 120),
                    ),
                    _seed_exercise(
                        "dumbbell-bench-press",
                        3,
                        "AMRAP 12",
                        120,
                        plan=_capped_amrap_plan(3, 12, 120),
                    ),
                    _seed_exercise(
                        "dumbbell-fly", 3, "AMRAP 12", 75, plan=_capped_amrap_plan(3, 12, 75)
                    ),
                    _seed_exercise(
                        "arnold-press", 3, "AMRAP 12", 90, plan=_capped_amrap_plan(3, 12, 90)
                    ),
                    _seed_exercise(
                        "dumbbell-overhead-extension",
                        3,
                        "AMRAP 12",
                        75,
                        plan=_capped_amrap_plan(3, 12, 75),
                    ),
                ],
            ),
            (
                "Pull B",
                [
                    _seed_exercise(
                        "chest-supported-dumbbell-row",
                        3,
                        "AMRAP 12",
                        90,
                        plan=_capped_amrap_plan(3, 12, 90),
                    ),
                    _seed_exercise(
                        "one-arm-dumbbell-row",
                        3,
                        "AMRAP 12",
                        90,
                        plan=_capped_amrap_plan(3, 12, 90),
                    ),
                    _seed_exercise(
                        "rear-delt-fly", 3, "AMRAP 12", 60, plan=_capped_amrap_plan(3, 12, 60)
                    ),
                    _seed_exercise(
                        "hammer-curl", 3, "AMRAP 12", 75, plan=_capped_amrap_plan(3, 12, 75)
                    ),
                    _seed_exercise(
                        "dumbbell-shrug", 3, "AMRAP 12", 75, plan=_capped_amrap_plan(3, 12, 75)
                    ),
                ],
            ),
            (
                "Legs B",
                [
                    _seed_exercise(
                        "bulgarian-split-squat",
                        3,
                        "AMRAP 12",
                        120,
                        plan=_capped_amrap_plan(3, 12, 120),
                    ),
                    _seed_exercise(
                        "db-squat", 3, "AMRAP 12", 120, plan=_capped_amrap_plan(3, 12, 120)
                    ),
                    _seed_exercise(
                        "single-leg-rdl", 3, "AMRAP 12", 120, plan=_capped_amrap_plan(3, 12, 120)
                    ),
                    _seed_exercise(
                        "seated-leg-curl", 3, "AMRAP 12", 90, plan=_capped_amrap_plan(3, 12, 90)
                    ),
                    _seed_exercise(
                        "seated-calf-raise", 3, "AMRAP 12", 60, plan=_capped_amrap_plan(3, 12, 60)
                    ),
                ],
            ),
        ],
    },
]

STRENGTH_TEMPLATE_SPECS.extend(_SOURCE_TEMPLATE_SPECS)
