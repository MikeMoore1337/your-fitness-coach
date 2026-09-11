# AI Coach: управляемая долгосрочная память

Статус: Task 92A, узкий rollout по owner decision от 2026-09-11.

## Product contract

AI Coach может использовать небольшой набор явно подтверждённых пользователем
предпочтений, чтобы последовательнее объяснять материал. Память не является вторым
профилем пользователя, источником фактов или историей диалога. Каноническая модель
YFC и данные текущего read-only tool всегда имеют приоритет.

Разрешены только четыре категории:

- `preferred_explanation_style` — например, короткий ответ или ответ по шагам;
- `ai_interaction_preferences` — форма обращения и другие предпочтения взаимодействия;
- `stable_non_medical_preferences` — стабильное немедицинское предпочтение, если для него
  нет канонического поля Profile/Preferences;
- `explicit_ai_context` — явно заданный пользователем немедицинский контекст для AI Coach.

В memory нельзя сохранять цели, вес и антропометрию, калории и КБЖУ, факты питания,
воду, программы, тренировочную историю, упражнения, подходы, повторы, кардио,
прогресс, оборудование, существующие поля профиля/настроек, medical/injury данные,
AAS/drugs, психографику, trainer/client данные, рекламные сведения, секреты,
произвольную историю разговора или raw workout/nutrition history. Если предпочтение
должно стать частью продукта, нужен отдельный product follow-up для канонического поля;
memory не расширяется вместо этой модели.

## Write pipeline

Контракт записи: `candidate -> deterministic validation -> prohibited-category rejection
-> explicit confirmation -> bounded structured write`. В текущем rollout нет generic
`write_memory(text)` и нет записи результата модели. UI отправляет категорию, ограниченное
однострочное значение и `confirmation=true`; backend повторно проверяет allowlist,
prompt-injection/safety паттерны, ссылки, контакты, идентификаторы и запрещённые
канонические/медицинские категории.

Один элемент ограничен 240 символами, аккаунт — 20 активными элементами. Для каждой
записи сохраняются категория, версия, `source_kind`, `confidence`, безопасный
`source_ref` и timestamps. Текст prompt, ответ модели, conversation history и raw tool
payload в memory не записываются. Audit содержит только действие, категорию, версию,
статус и количество удалённых элементов; значение memory в audit не копируется.

Будущий candidate flow может использовать `source_kind=confirmed_candidate`, но запись
возможна только после той же deterministic validation и явного подтверждения. Модель не
получает право самостоятельно создавать или менять memory.

## Consent и пользовательский контроль

Memory имеет отдельную запись согласия `ai_coach_memory_consents` со scope
`ai_coach_memory_v1` и версиями `enabled`, `paused`, `revoked`. Это не заменяет базовое
согласие personal read-only tools. Для генерации должны одновременно выполняться:

1. активное базовое personal consent;
2. активное memory consent;
3. текущая rollout/policy-проверка AI Coach.

Пауза и отзыв немедленно исключают memory из следующего provider request. Сами записи
при pause/revoke остаются видимыми пользователю, чтобы их можно было исправить или
удалить; `clear all`, удаление одного элемента и account deletion удаляют их сразу.
Пользователь может просмотреть категории и значения, изменить или удалить отдельный
элемент, очистить всё, включить/поставить на паузу/отозвать memory и запросить account
export. Эти операции остаются authenticated-user controls даже при временной
недоступности генерации или после выхода аккаунта из rollout cohort; создание новых
элементов по-прежнему ограничено текущей rollout-проверкой. Включение выключено по умолчанию.

## Retrieval precedence и provider boundary

Для personal запроса backend формирует отдельный `memory_context` только при active
memory consent. В provider payload передаются только категория, значение, origin и
`updated_at`; внутренний memory ID и user ID не передаются. Generic route memory не
получает.

Memory маркируется как недоверенный continuity context, а не evidence. Она может влиять
только на стиль и форму объяснения. Факт из canonical personal tool или отчёта всегда
побеждает memory; конфликтующая memory игнорируется. Memory не может стать основанием
для медицинского вывода, расчёта, цели, программы или изменения данных.

## Privacy, export и rollout

Схема добавлена миграцией `0079_ai_coach_memory`. В account export входят consent и
структурированные memory items, но не prompt/answer/provider payload. Удаление аккаунта
удаляет обе memory-таблицы вместе с account-owned данными. Новые environment keys,
provider и multiprovider fallback не добавляются; operational env change required: no.

Rollout использует существующую AI Coach cohort/personal policy. Логи остаются
metadata-only: request ID, job, trust class, provider/model metadata, outcome, latency,
attempts, nullable usage, tool name и безопасный error code. Значения memory и текст
запроса в логи не попадают.

Task 92B остаётся `RESEARCH FIRST`: текущий single provider сохраняется. Для multiprovider
нужны отдельные измеренные evidence outage/quota/capability/latency/cost/privacy/quality
gap и новый owner decision; эта task такой routing не включает.
