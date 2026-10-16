# Технический контракт #996

Документ описывает только существующий backend-контракт и безопасное поведение будущего UI. Новый endpoint не предлагается.

## 1. Получение кандидатов

```http
GET /api/v1/workouts/{workout_id}/exercises/{workout_exercise_id}/alternatives?available_equipment_ids=dumbbell&available_equipment_ids=bench
```

Ответ: `200 OK`, массив `WorkoutAlternativeItem`:

```json
[
  {
    "exercise_id": 123,
    "title": "Жим гантелей лёжа",
    "equipment_ids": ["dumbbell", "bench"],
    "score": 150,
    "reason_keys": ["curated_pair", "movement_pattern", "primary_muscle"]
  }
]
```

Фактическая серверная граница:

- workout принадлежит пользователю, относится к текущему дню и находится в разрешенном состоянии;
- target не должен иметь completed/reps/weight/duration/distance/heart-rate/zone/RIR/failure evidence;
- target/replacement не должны нарушать visible/avoided/used ограничения;
- metric type должен совпадать;
- equipment кандидата должен быть подмножеством `available_equipment_ids`;
- для `planned` допускается текущий catalog fallback внутри серверного scorer, для `in_progress` используется curated set;
- результат не содержит pagination/limit/offset. «Все подходящие» безопасно только над всем этим ответом, не над локальным каталогом.

Клиент не должен повторять серверное решение, добавлять кандидатов из другого endpoint или преобразовывать `score` в пользовательское обещание. Поиск и equipment-фильтры — это пересечение с уже полученным массивом; пустой результат означает «в этом ответе ничего не найдено», а не новый поиск.

## 2. Preview

```http
POST /api/v1/workouts/{workout_id}/adaptations/preview
Content-Type: application/json
```

```json
{
  "reason": "replace_exercise",
  "target_workout_exercise_id": 101,
  "replacement_exercise_id": 123,
  "available_equipment_ids": ["dumbbell", "bench"]
}
```

Ответ `WorkoutAdaptationPreviewResponse` имеет `status: preview | no_changes | safety_stop`, `ruleset_version`, `changes`, `original_exercises`, `adapted_exercises`, `warnings`, `message` и nullable `preview_token`. До успешного preview локальное состояние workout/program не меняется. Apply не вызывается автоматически.

## 3. Apply

```http
POST /api/v1/workouts/{workout_id}/adaptations/apply
Content-Type: application/json
```

Тело повторяет preview-запрос и добавляет `preview_token` длиной 64. Apply обязан повторно проверить актуальное состояние, token и совместимость. `409` — не повод молча повторять старый token: UI очищает preview, сохраняет выбранные условия для повторного preview и сообщает о конфликте. Повторный идентичный apply остается идемпотентным по существующему контракту.

## 4. Что не входит в #996

- новый полнотекстовый/search endpoint, pagination, server-side filter contract или новый reason dictionary;
- изменение правил совместимости, медицинская/биомеханическая рекомендация, AI Coach, программа или будущие тренировки;
- перенос фактов подходов, замена уже начатого target, изменение RBAC или обход серверной проверки;
- изменение общих стилей active set, навигации и preview программ.

Если backend позднее начнет возвращать неполное множество, текущий UX-контракт должен fail closed: скрыть/заблокировать «Все подходящие» и остановиться на отдельном API-решении.
