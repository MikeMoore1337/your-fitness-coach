# AI Coach: grounded итог канонического отчёта (Task 91)

Task 91 добавляет отдельный read-only tool `get_period_report_insights`. Он запускается
только явным действием пользователя после выбора периода и объясняет уже построенный
канонический progress report. Детальная factual report без AI остаётся источником истины;
AI Coach не пересчитывает её значения и не изменяет данные приложения.

## Контракт периода и evidence

Разрешены `days_7`, `days_30`, `days_90` и bounded `custom` с диапазоном не более 366
дней и без будущих дат. Границы периода и timezone разрешаются сервером для текущего
аутентифицированного пользователя. `period`, `date_from`, `date_to` и `period_days` не
позволяют выбрать чужой аккаунт или произвольный SQL-запрос.

В provider передаётся минимальный versioned bundle:

- факты с единицами и `source_section`;
- coverage/data sufficiency и канонические `reason_keys`;
- исторические версии nutrition targets;
- ограничения и зарезервированное поле contradictions;
- период, timezone, `progress-report-v1`, input `ai-coach-period-report-input-v1` и
  output `ai-coach-period-report-output-v1`.

Из bundle исключены `user_id`, имя/цель subject, Telegram/email, SQL, ORM-объекты,
raw diary, названия упражнений, check-in notes, wellbeing и sleep/mood. Hydration
включается только при наличии записанных значений и coverage. Missing/incomplete дни
питания не становятся нулевыми значениями; исторические цели не заменяются текущей.

`report_revision` — детерминированный SHA-256 минимального bundle без output-version.
Он возвращается клиенту для диагностики версии snapshot, но содержимое отчёта не
сохраняется в БД и не становится AI Coach memory. Отдельная memory Task 92A может
передаваться только как пользовательский continuity context для стиля объяснения; она
не меняет канонические факты отчёта.

## Output и safety

Provider обязан вернуть русский structured output с разделами:

1. `Главное за период` — 2–4 grounded `fact`;
2. `Ограничения данных` — missing, incomplete и contradictory coverage;
3. `Что можно сделать дальше` — 1–3 `suggestion`, только обратимые действия вроде
   заполнения исходных записей или повторного просмотра раздела;
4. `Почему` — `evidence_ids` и детерминированные `reason_keys`.

Дополнительно допускается не более четырёх `inference`. Каждый claim имеет kind,
allowlisted evidence anchors и bounded text. Сервис отклоняет неизвестные anchors,
URL, prompt-injection markers, диагнозы, причинные утверждения, прогнозы, medical HR
thresholds, eating-back, body-composition certainty и изменения программы, workout,
targets или reminders.

При недостаточной sufficiency provider не вызывается: возвращается короткий
`insufficient_data` fallback с теми же четырьмя разделами и одной безопасной
следующей подсказкой. Factual report и ссылка на экран `/progress` остаются доступными.

## Consent, cost и lifecycle

Используется существующее отдельное согласие Task 89 (`personal_readonly_tools_v1`);
новая категория данных отчёта не добавляется. Результат transient/re-generatable, без
сохранения report payload. Отдельная user-controlled memory описана в
`docs/ai/ai-coach-memory.md` и не является частью отчёта. Сохраняются только безопасные metadata: outcome, tool, latency,
bounded token/cost counters, provider policy, prompt/output version и report revision.

Runtime сохраняет персональный kill switch, per-user/global quota, bounded timeout,
один provider attempt для personal route и cooldown. При недоступности provider UI
показывает контролируемое состояние; пользователь может отменить запрос или повторить
его. Автоматической генерации, фоновых задач, trainer/client delivery, Telegram/PDF
share и write tools нет.

## UI

В AI Coach доступен быстрый запрос `Итог периода`, выбор 7/30/90 дней и произвольного
bounded диапазона с датами. В ответе отдельно видны facts, ограничения, suggestions,
inferences/основания, report version и underlying source. Raw evidence anchors остаются
техническими data attributes и не превращаются в исполняемую разметку или ссылки.

Новые environment variables, зависимости и database migrations для Task 91 не требуются.
