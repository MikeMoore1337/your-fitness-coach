from __future__ import annotations

from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.services.exercise_catalog_metadata import (
    ITEM_GUIDE_CONTENT,
    LOWER_BODY_MACHINE_SLUGS,
    UPPER_BODY_MACHINE_SLUGS,
)
from fitminiapp_api.services.exercise_domain import (
    DEFAULT_SAFETY_NOTES,
    SOURCE_LICENSE_URL,
    canonical_muscle_identifier,
    exercise_equipment_payload,
    exercise_muscle_payload,
)
from fitminiapp_api.services.exercise_guide_media import get_guide_media, resolve_guide_source

SOURCE_NAME = "free-exercise-db"
SOURCE_URL = "https://github.com/yuhonas/free-exercise-db"
SOURCE_LICENSE = "Unlicense (общественное достояние)"

GENERATED_CARDIO_SLUGS = {
    "outdoor-run",
    "elliptical-trainer",
    "outdoor-cycling",
    "stationary-bike",
    "outdoor-walk",
    "treadmill-walk",
    "stair-climber",
    "swimming",
    "ski-erg",
}

YFC_GENERATED_120D_SLUGS = frozenset(
    {
        "bodyweight-glute-bridge",
        "dead-hang",
        "pendlay-row",
        "weighted-dip",
        "single-leg-calf-raise",
        "hollow-hold",
        "belt-squat",
        "wall-sit",
    }
)
YFC_SINGLE_IMAGE_SLUGS = frozenset(GENERATED_CARDIO_SLUGS) | YFC_GENERATED_120D_SLUGS

YFC_ORIGINAL_VECTOR_SLUGS = frozenset(UPPER_BODY_MACHINE_SLUGS + LOWER_BODY_MACHINE_SLUGS)


MUSCLE_FUNCTIONS = {
    "Грудь": "Приводит плечо к корпусу и перемещает руку вперёд в фазе усилия.",
    "Спина": "Приводит плечо к корпусу и тянет плечевой пояс назад и вниз.",
    "Разгибатели спины": "Удерживают позвоночник нейтральным и разгибают корпус.",
    "Квадрицепс": "Разгибает коленный сустав и помогает контролировать опускание.",
    "Бицепс бедра": "Разгибает бедро, сгибает колено и контролирует таз.",
    "Ягодицы": "Разгибают и стабилизируют тазобедренный сустав.",
    "Ноги": "Создают усилие в тазобедренных, коленных и голеностопных суставах.",
    "Задняя цепь": "Разгибает тазобедренный сустав и удерживает корпус жёстким.",
    "Плечи": "Поднимают и стабилизируют плечо при движении руки.",
    "Передняя дельта": "Сгибает плечо и помогает выводить руку вперёд и вверх.",
    "Средняя дельта": "Отводит плечо в сторону.",
    "Задняя дельта": "Отводит плечо назад и участвует во внешней ротации.",
    "Нижняя трапеция": "Опускает и вращает лопатку, сохраняя её положение.",
    "Трапеции": "Поднимают и стабилизируют лопатки.",
    "Бицепс": "Сгибает локоть и помогает разворачивать предплечье ладонью вверх.",
    "Трицепс": "Разгибает локтевой сустав.",
    "Предплечья": "Удерживают запястье и обеспечивают надёжный хват.",
    "Хват": "Фиксирует снаряд и стабилизирует кисть и предплечье.",
    "Икры": "Разгибают голеностоп, поднимая пятку.",
    "Пресс": "Сгибает корпус и препятствует избыточному разгибанию поясницы.",
    "Кор": "Стабилизирует позвоночник и передаёт усилие между верхом и низом тела.",
    "Косые мышцы": "Поворачивают корпус и препятствуют нежелательному вращению.",
    "Приводящие": "Приводят бедро и стабилизируют таз и колено.",
    "Все тело": "Согласует работу ног, корпуса и плечевого пояса.",
    "Кардио": "Поддерживает циклическую работу всего тела и энергоснабжение движения.",
    "Кондиция": "Обеспечивает повторную взрывную работу и общую устойчивость к нагрузке.",
}


PROFILES = {
    "chest_press": {
        "steps": [
            "Сведи и опусти лопатки, поставь стопы устойчиво и сохрани естественный прогиб спины.",
            "Опускай снаряд под контролем к нижней части груди, удерживая предплечья близко к вертикали.",
            "Выжми вес по устойчивой траектории, не теряя опору стоп и положение лопаток.",
        ],
        "breathing": "Вдох на опускании, выдох после прохождения самой тяжёлой части жима.",
        "mistakes": [
            "Отрыв таза или стоп",
            "Раскрытые плечи и потеря лопаток",
            "Удар снарядом о грудь",
        ],
        "secondary": ["Трицепс", "Передняя дельта"],
    },
    "chest_fly": {
        "steps": [
            "Зафиксируй грудную клетку и лопатки, оставь локти слегка согнутыми.",
            "Разводи руки до комфортного растяжения груди без провала плеч назад.",
            "Сведи руки дугой за счёт грудных мышц, сохраняя угол в локтях.",
        ],
        "breathing": "Вдох при разведении, выдох при сведении рук.",
        "mistakes": ["Слишком глубокое растяжение", "Превращение движения в жим", "Рывок корпусом"],
        "secondary": ["Передняя дельта", "Бицепс"],
    },
    "pushup_dip": {
        "steps": [
            "Создай жёсткую линию корпуса, опусти плечи и зафиксируй лопатки.",
            "Согни руки под контролем до комфортной глубины, не проваливая плечи.",
            "Разогни локти и вернись вверх, сохраняя положение таза и корпуса.",
        ],
        "breathing": "Вдох при опускании, выдох при подъёме.",
        "mistakes": ["Провисание таза", "Плечи у ушей", "Слишком резкое опускание"],
        "secondary": ["Трицепс", "Передняя дельта", "Кор"],
    },
    "vertical_pull": {
        "steps": [
            "Возьмись за перекладину или рукоять и сначала опусти лопатки от ушей.",
            "Тяни локти вниз к корпусу, сохраняя грудную клетку раскрытой.",
            "Под контролем выпрями руки, не теряя напряжение плечевого пояса.",
        ],
        "breathing": "Выдох во время тяги, вдох при возвращении рук вверх.",
        "mistakes": ["Раскачивание корпусом", "Тяга только кистями", "Резкий бросок веса вверх"],
        "secondary": ["Бицепс", "Предплечья", "Задняя дельта"],
    },
    "row": {
        "steps": [
            "Зафиксируй нейтральную спину и устойчивое положение таза.",
            "Начни движение лопаткой и тяни локоть назад вдоль корпуса.",
            "Коротко сведи лопатки и плавно выпрями руку без округления спины.",
        ],
        "breathing": "Выдох в тяговой фазе, вдох при возврате веса.",
        "mistakes": ["Рывок поясницей", "Плечи у ушей", "Избыточное сгибание кистей"],
        "secondary": ["Бицепс", "Задняя дельта", "Предплечья"],
    },
    "pullover": {
        "steps": [
            "Зафиксируй рёбра и таз, оставь локти немного согнутыми.",
            "Отведи руки до комфортного растяжения широчайших без прогиба поясницы.",
            "Верни руки к корпусу дугой, сохраняя почти неизменный угол в локтях.",
        ],
        "breathing": "Вдох при отведении рук, выдох при приведении.",
        "mistakes": ["Прогиб в пояснице", "Сильное сгибание локтей", "Рывок из нижней точки"],
        "secondary": ["Грудь", "Трицепс", "Кор"],
    },
    "hinge": {
        "steps": [
            "Поставь стопы устойчиво, напряги кор и удерживай позвоночник нейтральным.",
            "Отводи таз назад, сохраняя снаряд близко к ногам и колени направленными по линии стоп.",
            "Разогни тазобедренные суставы и встань, не переразгибая поясницу наверху.",
        ],
        "breathing": "Вдох и фиксация корпуса перед повтором, выдох после прохождения тяжёлой точки.",
        "mistakes": [
            "Округление поясницы",
            "Снаряд далеко от тела",
            "Переразгибание в верхней точке",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Разгибатели спины", "Кор"],
    },
    "squat": {
        "steps": [
            "Распредели вес по всей стопе, напряги кор и направь колени по линии носков.",
            "Опускай таз между стопами до глубины, на которой сохраняется нейтральная спина.",
            "Оттолкнись всей стопой и синхронно разогни колени и таз.",
        ],
        "breathing": "Вдох и фиксация корпуса перед спуском, выдох после самой тяжёлой части подъёма.",
        "mistakes": ["Колени заваливаются внутрь", "Пятки отрываются", "Потеря нейтральной спины"],
        "secondary": ["Ягодицы", "Бицепс бедра", "Кор"],
    },
    "lunge": {
        "steps": [
            "Поставь стопы на ширине таза и удерживай корпус собранным.",
            "Сделай шаг и опускай таз вертикально, направляя переднее колено по линии стопы.",
            "Оттолкнись опорной ногой и вернись в устойчивое положение.",
        ],
        "breathing": "Вдох при опускании, выдох при подъёме.",
        "mistakes": [
            "Слишком узкая постановка стоп",
            "Завал колена внутрь",
            "Толчок только носком",
        ],
        "secondary": ["Ягодицы", "Бицепс бедра", "Кор"],
    },
    "leg_isolation": {
        "steps": [
            "Настрой тренажёр по оси сустава и плотно прижми корпус к опоре.",
            "Выполни рабочую фазу в полной контролируемой амплитуде без рывка.",
            "Плавно верни вес, сохраняя напряжение и положение таза.",
        ],
        "breathing": "Выдох в фазе усилия, вдох при возврате.",
        "mistakes": [
            "Неверная настройка оси тренажёра",
            "Удар весового стека",
            "Отрыв таза от опоры",
        ],
        "secondary": ["Кор"],
    },
    "glute": {
        "steps": [
            "Зафиксируй рёбра и поясницу, поставь стопы так, чтобы колени двигались по линии носков.",
            "Разогни бедро за счёт ягодиц, не подбрасывая вес поясницей.",
            "Сожми ягодицы в верхней точке и опустись под контролем.",
        ],
        "breathing": "Выдох при разгибании бедра, вдох при возвращении.",
        "mistakes": ["Переразгибание поясницы", "Толчок носками", "Потеря контроля таза"],
        "secondary": ["Бицепс бедра", "Кор"],
    },
    "shoulder_press": {
        "steps": [
            "Напряги ягодицы и кор, удерживай запястья над локтями.",
            "Выжми вес вверх, позволяя лопаткам естественно вращаться.",
            "Опусти снаряд до комфортного уровня без потери положения рёбер.",
        ],
        "breathing": "Вдох перед жимом, выдох после прохождения тяжёлой точки.",
        "mistakes": [
            "Сильный прогиб поясницы",
            "Запястья заламываются назад",
            "Плечи постоянно подняты",
        ],
        "secondary": ["Трицепс", "Передняя дельта", "Кор"],
    },
    "shoulder_raise": {
        "steps": [
            "Опусти плечи, слегка согни локти и зафиксируй корпус.",
            "Подними руки в заданном направлении до уровня, где плечо остаётся стабильным.",
            "Плавно опусти вес, не раскачивая корпус.",
        ],
        "breathing": "Выдох при подъёме рук, вдох при опускании.",
        "mistakes": [
            "Раскачивание корпусом",
            "Плечи тянутся к ушам",
            "Слишком большой рабочий вес",
        ],
        "secondary": ["Трапеции", "Передняя дельта", "Задняя дельта"],
    },
    "arm_curl": {
        "steps": [
            "Зафиксируй плечо и корпус, удерживай запястье нейтральным.",
            "Согни локоть без вывода плеча вперёд и без раскачивания.",
            "Под контролем полностью опусти снаряд, сохраняя локоть на месте.",
        ],
        "breathing": "Выдох при сгибании, вдох при разгибании руки.",
        "mistakes": ["Раскачивание корпусом", "Локти уходят вперёд", "Залом кисти"],
        "secondary": ["Предплечья"],
    },
    "triceps": {
        "steps": [
            "Зафиксируй плечо и корпус, держи локти направленными по траектории движения.",
            "Разогни локти до контролируемого сокращения трицепса.",
            "Плавно верни предплечья, не позволяя плечам смещаться.",
        ],
        "breathing": "Выдох при разгибании локтя, вдох при возврате.",
        "mistakes": ["Локти расходятся", "Движение плечом вместо предплечья", "Рывок корпусом"],
        "secondary": ["Предплечья", "Кор"],
    },
    "calf": {
        "steps": [
            "Поставь переднюю часть стопы устойчиво и сохрани нейтральное положение голеностопа.",
            "Поднимись максимально высоко на носок без завала стопы наружу.",
            "Медленно опусти пятку до комфортного растяжения икры.",
        ],
        "breathing": "Выдох при подъёме, вдох при опускании пятки.",
        "mistakes": ["Пружинящие повторы", "Завал стопы", "Сокращённая амплитуда"],
        "secondary": ["Кор"],
    },
    "core_static": {
        "steps": [
            "Выстрой тело в устойчивую линию и создай опору руками или локтями.",
            "Подтяни рёбра к тазу, напряги ягодицы и спокойно удерживай позицию.",
            "Заверши подход до того, как поясница или плечи потеряют положение.",
        ],
        "breathing": "Дыши спокойно короткими вдохами, не расслабляя живот.",
        "mistakes": ["Провисание поясницы", "Задержка дыхания", "Плечи у ушей"],
        "secondary": ["Ягодицы", "Плечи"],
    },
    "core_dynamic": {
        "steps": [
            "Зафиксируй поясницу и начни движение за счёт мышц живота.",
            "Выполни рабочую фазу без рывка и без помощи инерции.",
            "Вернись под контролем, сохраняя напряжение корпуса.",
        ],
        "breathing": "Выдох при сокращении пресса, вдох при возвращении.",
        "mistakes": [
            "Рывок шеей или ногами",
            "Отрыв поясницы",
            "Слишком быстрый возврат в исходное положение",
        ],
        "secondary": ["Кор", "Косые мышцы"],
    },
    "core_rotation": {
        "steps": [
            "Зафиксируй таз и позвоночник, создай устойчивую опору стопами.",
            "Поверни или удержи корпус за счёт мышц живота, не дёргая руками.",
            "Плавно вернись и повтори симметрично для второй стороны.",
        ],
        "breathing": "Выдох в рабочей фазе, вдох при возврате.",
        "mistakes": ["Вращение только руками", "Потеря положения таза", "Рывок в крайней точке"],
        "secondary": ["Кор", "Ягодицы"],
    },
    "running": {
        "steps": [
            "Выпрямись, слегка наклони всё тело вперёд от голеностопа и расслабь плечи.",
            "Ставь стопу под центром тяжести и направляй колено по линии носка.",
            "Поддерживай короткий естественный шаг и активную работу согнутых рук.",
        ],
        "breathing": "Дыши ритмично; на лёгком темпе сохраняй возможность говорить фразами.",
        "mistakes": [
            "Приземление далеко впереди корпуса",
            "Сильный наклон из поясницы",
            "Зажатые плечи и чрезмерно длинный шаг",
        ],
        "secondary": ["Ноги", "Ягодицы", "Икры", "Кор"],
    },
    "walking": {
        "steps": [
            "Держи макушку вверх, взгляд вперёд, а плечи расслабленными.",
            "Перекатывайся с пятки на носок, ставя стопу близко к центру тяжести.",
            "Двигай руками естественно и сохраняй ровный темп без подпрыгивания.",
        ],
        "breathing": "Дыши свободно и ритмично, согласуя дыхание с темпом шагов.",
        "mistakes": [
            "Сутулость и взгляд под ноги",
            "Слишком длинный шаг",
            "Опора на поручни дорожки весом тела",
        ],
        "secondary": ["Ноги", "Ягодицы", "Икры", "Кор"],
    },
    "cycling": {
        "steps": [
            "Настрой седло так, чтобы в нижней точке педали колено оставалось слегка согнутым.",
            "Удерживай нейтральную спину, расслабленные плечи и мягко согнутые локти.",
            "Крути педали плавно, сохраняя колени по линии стоп и устойчивый таз.",
        ],
        "breathing": "Дыши ровно; усиливай выдох при росте мощности, не задерживая дыхание.",
        "mistakes": [
            "Слишком низкое или высокое седло",
            "Колени заваливаются внутрь",
            "Раскачивание таза и чрезмерное напряжение рук",
        ],
        "secondary": ["Квадрицепс", "Ягодицы", "Икры", "Кор"],
    },
    "elliptical": {
        "steps": [
            "Поставь стопы полностью на платформы, выпрямись и слегка согни колени.",
            "Двигай платформы и рукояти плавно, удерживая таз по центру тренажёра.",
            "Сохраняй пятки на опоре и ровный ритм без рывков в крайних точках.",
        ],
        "breathing": "Дыши ритмично и свободно, подбирая сопротивление под целевую интенсивность.",
        "mistakes": [
            "Перенос веса на рукояти",
            "Отрыв пяток от платформ",
            "Сильные наклоны корпуса вперёд и назад",
        ],
        "secondary": ["Ноги", "Ягодицы", "Икры", "Плечи", "Кор"],
    },
    "stair_climber": {
        "steps": [
            "Выпрямись, положи руки на поручни только для равновесия и смотри вперёд.",
            "Ставь на ступень большую часть стопы и направляй колено по линии носка.",
            "Поднимай тело усилием опорной ноги, сохраняя таз ровным и шаг стабильным.",
        ],
        "breathing": "Дыши ритмично и снижай скорость, если дыхание перестаёт быть контролируемым.",
        "mistakes": [
            "Опора всем весом на поручни",
            "Шаг только на носках",
            "Завал коленей внутрь и сутулость",
        ],
        "secondary": ["Квадрицепс", "Ягодицы", "Икры", "Кор"],
    },
    "swimming": {
        "steps": [
            "Вытяни тело в длинную линию и удерживай голову нейтрально, глядя вниз.",
            "Поворачивай корпус вместе с плечами и тазом, начиная гребок с опоры предплечьем.",
            "Для вдоха поверни голову вместе с корпусом и плавно выдыхай в воду.",
        ],
        "breathing": "Выдыхай в воду непрерывно, а короткий вдох делай во время поворота корпуса.",
        "mistakes": [
            "Высоко поднятая голова",
            "Пересечение рукой средней линии тела",
            "Задержка дыхания до момента вдоха",
        ],
        "secondary": ["Спина", "Плечи", "Кор", "Ноги"],
    },
    "ski_erg": {
        "steps": [
            "Встань устойчиво, подними рукояти и сохрани плечи опущенными.",
            "Начни тягу корпусом через сгибание таза, затем веди руки вниз вдоль тела.",
            "Заверши рукоятями у бёдер и плавно вернись вверх без переразгибания поясницы.",
        ],
        "breathing": "Выдох во время тяги вниз, вдох при контролируемом возвращении вверх.",
        "mistakes": [
            "Тяга только руками",
            "Округление или переразгибание поясницы",
            "Поднятые плечи и резкий возврат рукоятей",
        ],
        "secondary": ["Спина", "Плечи", "Трицепс", "Кор", "Ноги"],
    },
    "conditioning": {
        "steps": [
            "Прими устойчивое исходное положение и заранее освободи пространство для движения.",
            "Выполняй повторения ритмично, сохраняя технику даже при росте пульса.",
            "Снизь темп или закончи подход, если перестаёшь контролировать корпус и суставы.",
        ],
        "breathing": "Дыши ритмично и не задерживай дыхание на серии повторений.",
        "mistakes": [
            "Темп выше технических возможностей",
            "Жёсткое приземление",
            "Потеря контроля корпуса",
        ],
        "secondary": ["Ноги", "Кор", "Плечи"],
    },
    "carry": {
        "steps": [
            "Подними снаряд безопасной тягой, выпрямись и опусти плечи.",
            "Иди короткими контролируемыми шагами, не отклоняясь в сторону.",
            "Остановись устойчиво и опусти вес через сгибание таза и коленей.",
        ],
        "breathing": "Дыши коротко и ритмично, сохраняя напряжение корпуса.",
        "mistakes": ["Наклон корпуса", "Плечи у ушей", "Слишком длинные неустойчивые шаги"],
        "secondary": ["Предплечья", "Трапеции", "Кор", "Ягодицы"],
    },
    "wrist": {
        "steps": [
            "Зафиксируй предплечья на устойчивой опоре, оставив кисти свободными.",
            "Перемещай гриф только в запястьях без движения локтей.",
            "Вернись в исходное положение медленно, сохраняя хват.",
        ],
        "breathing": "Выдох в рабочей фазе, вдох при контролируемом возврате.",
        "mistakes": ["Движение локтями", "Рывок грифом", "Слишком тяжёлый вес"],
        "secondary": ["Хват"],
    },
    "grip_static": {
        "steps": [
            "Создай устойчивый хват и убери ноги с опоры без раскачивания.",
            "Удерживай корпус спокойно и продолжай ровно дышать.",
            "Верни ноги на опору до полной потери хвата.",
        ],
        "breathing": "Дыши спокойно и не задерживай дыхание.",
        "mistakes": ["Раскачивание", "Задержка дыхания", "Неконтролируемое завершение"],
        "secondary": ["Предплечья", "Спина", "Плечи", "Кор"],
    },
}


PROFILE_SLUGS = {
    "chest_press": {
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
        "floor-press",
    },
    "chest_fly": {
        "dumbbell-fly",
        "incline-dumbbell-fly",
        "cable-fly",
        "low-to-high-cable-fly",
        "pec-deck",
    },
    "pushup_dip": {
        "push-up",
        "weighted-dip",
        "chest-dip",
        "bench-dip",
        "machine-dip",
        "assisted-dips",
    },
    "vertical_pull": {
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
    },
    "row": {
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
    },
    "pullover": {"dumbbell-pullover", "straight-arm-pulldown", "machine-pullover"},
    "hinge": {
        "deadlift",
        "rack-pull",
        "hyperextension",
        "good-morning",
        "romanian-deadlift",
        "stiff-leg-deadlift",
        "single-leg-rdl",
        "glute-ham-raise",
        "cable-pull-through",
        "kettlebell-swing",
        "sumo-deadlift",
        "reverse-hyperextension",
        "trap-bar-deadlift",
    },
    "squat": {
        "squat",
        "front-squat",
        "hack-squat",
        "smith-squat",
        "goblet-squat",
        "bodyweight-squat",
        "belt-squat",
        "leg-press",
        "sissy-squat",
        "wall-sit",
        "kettlebell-goblet-squat",
        "pendulum-squat",
        "plate-loaded-leg-press",
        "unilateral-leg-press",
        "v-squat-machine",
        "pistol-squat",
        "overhead-squat",
        "safety-bar-squat",
        "db-squat",
    },
    "lunge": {
        "lunge",
        "walking-lunge",
        "reverse-lunge",
        "bulgarian-split-squat",
        "split-squat",
        "step-up",
        "smith-split-squat",
    },
    "leg_isolation": {
        "leg-extension",
        "leg-curl",
        "seated-leg-curl",
        "standing-leg-curl",
        "nordic-curl",
        "hip-abduction",
        "hip-adduction",
        "cable-kickback",
        "machine-glute-kickback",
    },
    "glute": {
        "hip-thrust",
        "single-leg-hip-thrust",
        "barbell-glute-bridge",
        "bodyweight-glute-bridge",
        "machine-hip-thrust",
    },
    "shoulder_press": {
        "overhead-press",
        "seated-dumbbell-press",
        "arnold-press",
        "machine-shoulder-press",
        "independent-lever-shoulder-press",
        "smith-shoulder-press",
        "landmine-press",
        "push-press",
    },
    "shoulder_raise": {
        "dumbbell-lateral-raise",
        "cable-lateral-raise",
        "machine-lateral-raise",
        "dumbbell-front-raise",
        "rear-delt-fly",
        "reverse-pec-deck",
        "barbell-shrug",
        "dumbbell-shrug",
        "y-raise",
        "cable-external-rotation",
        "band-pull-apart",
    },
    "arm_curl": {
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
    },
    "wrist": {"barbell-wrist-curl", "barbell-wrist-extension", "wrist-roller"},
    "grip_static": {"dead-hang"},
    "triceps": {
        "skull-crusher",
        "rope-pushdown",
        "cable-pushdown",
        "overhead-triceps-extension",
        "dumbbell-overhead-extension",
        "lying-dumbbell-triceps-extension",
        "triceps-kickback",
        "single-arm-cable-triceps-extension",
        "machine-triceps-extension",
    },
    "calf": {
        "standing-calf-raise",
        "seated-calf-raise",
        "donkey-calf-raise",
        "calf-press",
        "single-leg-calf-raise",
    },
    "core_static": {
        "plank",
        "side-plank",
        "hollow-hold",
        "dead-bug",
        "bird-dog",
        "dragon-flag",
        "l-sit",
    },
    "core_dynamic": {
        "crunch",
        "reverse-crunch",
        "cable-crunch",
        "hanging-leg-raise",
        "captain-chair-leg-raise",
        "ab-wheel",
        "mountain-climber",
        "decline-crunch",
        "hanging-knee-raise",
        "machine-seated-crunch",
        "jackknife-sit-up",
    },
    "core_rotation": {"russian-twist", "pallof-press", "woodchopper"},
    "carry": {"farmer-walk", "suitcase-carry", "kettlebell-overhead-carry"},
    "running": {"outdoor-run", "treadmill-run"},
    "walking": {"outdoor-walk", "treadmill-walk"},
    "cycling": {"outdoor-cycling", "stationary-bike", "recumbent-bike"},
    "elliptical": {"elliptical-trainer"},
    "stair_climber": {"stair-climber"},
    "swimming": {"swimming"},
    "ski_erg": {"ski-erg"},
    "conditioning": {
        "burpee",
        "box-jump",
        "jump-rope",
        "rowing-machine",
        "assault-bike",
        "battle-rope",
        "sled-push",
        "sled-pull",
        "medicine-ball-slam",
        "wall-ball",
        "thruster",
        "kettlebell-clean",
        "kettlebell-snatch",
        "turkish-get-up",
        "bear-crawl",
        "clean-and-jerk",
        "hang-power-clean",
    },
}


SLUG_TO_PROFILE = {slug: profile for profile, slugs in PROFILE_SLUGS.items() for slug in slugs}


def _base_slug(exercise: Exercise) -> str:
    return exercise.slug.split("-u-", maxsplit=1)[0]


def get_exercise_guide(
    exercise: Exercise,
    *,
    alternatives: list[dict[str, int | str]] | None = None,
) -> dict | None:
    slug = _base_slug(exercise)
    profile_name = SLUG_TO_PROFILE.get(slug)
    if profile_name is None:
        return None

    profile = ITEM_GUIDE_CONTENT.get(slug, PROFILES[profile_name])
    structured_muscles = exercise_muscle_payload(exercise)
    if not any(item["role"] == "primary" for item in structured_muscles):
        primary = exercise.primary_muscle or "Все тело"
        structured_muscles.insert(
            0,
            {
                "identifier": canonical_muscle_identifier(primary) or "",
                "name": primary,
                "role": "primary",
            },
        )
    muscles = [
        {
            "identifier": item["identifier"] or None,
            "name": item["name"],
            "role_id": item["role"],
            "role": "Основная" if item["role"] == "primary" else "Вспомогательная / стабилизатор",
            "function": MUSCLE_FUNCTIONS.get(item["name"], MUSCLE_FUNCTIONS["Все тело"]),
        }
        for item in structured_muscles
    ]

    is_yfc_original = slug in YFC_SINGLE_IMAGE_SLUGS or slug in YFC_ORIGINAL_VECTOR_SLUGS
    metadata = exercise.guide_metadata
    source_name = (
        metadata.source_name
        if metadata is not None
        else ("Your Fitness Coach" if is_yfc_original else SOURCE_NAME)
    )
    source_url = (
        metadata.source_url if metadata is not None else ("/" if is_yfc_original else SOURCE_URL)
    )
    source_license = (
        metadata.source_license
        if metadata is not None
        else ("Иллюстрация создана для приложения" if is_yfc_original else SOURCE_LICENSE)
    )
    source_license_url = (
        metadata.source_license_url
        if metadata is not None
        else (None if is_yfc_original else SOURCE_LICENSE_URL)
    )
    source_name, source_url, source_license, source_license_url = resolve_guide_source(
        slug,
        source_name=source_name,
        source_url=source_url,
        source_license=source_license,
        source_license_url=source_license_url,
    )
    media = get_guide_media(
        slug,
        exercise_title=exercise.title,
        source_name=source_name,
        source_url=source_url,
        source_license=source_license,
        source_license_url=source_license_url,
    )
    images = [{"phase": item["phase"], "url": item["url"], "alt": item["alt"]} for item in media]
    specific_safety_notes = profile.get("safety_notes")

    return {
        "technique_steps": profile["steps"],
        "breathing": profile["breathing"],
        "common_mistakes": profile["mistakes"],
        "muscles": muscles,
        "equipment": exercise_equipment_payload(exercise),
        "safety_notes": list(
            specific_safety_notes
            or (metadata.safety_notes if metadata is not None else DEFAULT_SAFETY_NOTES)
        ),
        "alternatives": alternatives or [],
        "media": media,
        "images": images,
        "media_reference": metadata.media_reference
        if metadata is not None
        else f"exercise-guides:{slug}",
        "source_name": source_name,
        "source_url": source_url,
        "source_license": source_license,
        "source_license_url": source_license_url,
    }
