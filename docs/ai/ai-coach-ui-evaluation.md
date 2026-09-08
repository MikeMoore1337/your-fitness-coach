# AI Coach: internal beta UI и evaluation gate (Task 90A)

Task 90A добавляет только внутренний UI-контур AI Coach. Он не становится пунктом основной
навигации Today/TMA и не является доказательством реальных пользовательских сессий.

## Server gate

Входы и экран доступны только если сервер вернул:

- `AI_COACH_UI_ENABLED=true`;
- текущий внутренний account id присутствует в `AI_COACH_INTERNAL_USER_IDS`;
- запрос к `GET /api/v1/ai-coach/status` прошёл authenticated boundary.

Runtime availability, kill switch, cost/data policy и персональная capability остаются
server-authoritative. UI не угадывает их по `.env`, профилю или полям пользователя. При
несовместимом provider/capability публичная помощь и персональная сводка показывают разные
контролируемые состояния; core-продукт продолжает работать.

## User boundary

Публичный режим отправляет только bounded job, короткий текст вопроса и server-known public
`context_id`. Персональный режим требует отдельного согласия и передаёт только одну read-only
сводку за период 7/30/90 дней. UI не хранит историю диалога, не создаёт память, не меняет
программу, цели, калории или расписание.

Ответ показывается как plain React text с минимальным Markdown-подмножеством. Markdown-ссылка
становится кликабельной только если её HTTPS URL совпадает с server-provided citation; raw HTML,
raw provider JSON, tool calls и upstream error не рендерятся.

## Versioned deterministic UI eval

Версия UI-контракта: `ai-coach-ui-beta-v1`.

| Case               | Что проверяется                             | Ожидаемое состояние                                                                 |
| ------------------ | ------------------------------------------- | ----------------------------------------------------------------------------------- |
| `UI-ENTRY-01`      | secondary entry из Today/Progress/Nutrition | виден только server-authorized cohort                                               |
| `UI-CONSENT-01`    | первый личный вызов                         | видны scope, период, ограничения и continue-without-AI путь                         |
| `UI-ANSWER-01`     | проверенный ответ                           | answer + limitations + canonical citations                                          |
| `UI-SAFE-01`       | markdown/URL payload                        | unsafe HTML/unknown links не исполняются и не становятся ссылками                   |
| `UI-STATE-01`      | insufficient/refusal/quota/unavailable      | controlled Russian state без raw internal error                                     |
| `UI-CAPABILITY-01` | generic доступен, personal недоступен       | публичный режим остаётся доступным, personal показывает отдельное unavailable state |
| `UI-RESET-01`      | повторный вопрос                            | очищается текущий ответ и bounded input, долгосрочная память отсутствует            |
| `UI-ANALYTICS-01`  | outcome/helpfulness events                  | нет prompt, answer, user id, exact fact, URL или provider payload                   |
| `UI-MOBILE-01`     | 360/390/430 px, touch и keyboard            | нет горизонтального overflow, CTA и field остаются доступными                       |

Провайдерские, adversarial, domain и source-gating проверки Task 88/89 остаются обязательным
основанием этого UI и запускаются теми же targeted backend tests. Эта task не меняет их dataset
задним числом и не называет synthetic eval реальным feedback.

## 90B gate

Переход к Task 90B запрещён до owner approval и готовых реальных participants/consent. Внутренний
UI и synthetic evaluation сами по себе этот gate не закрывают.
