# PR #963 — acceptance matrix

Срез этой матрицы относится только к техническому завершению PR #963. Контрольный HEAD до
интеграции: `98a54cf2d55bb86b2fd33669bfba93b9edee08e6`. Утверждённый owner visual package
#874 интегрирован commit `f4ed57e304cace5bd6d113e4a773d3fc7542a142`; итоговый exact HEAD
после обновления этой матрицы и required Checks публикуется в PR.

| Область | Статус в PR #963 | Доказательство | Оставшееся условие |
|---|---|---|---|
| #865, «О показателях» | `IMPLEMENTED_VERIFIED` | Одобрено владельцем `OWNER_865_VISUAL_APPROVAL=GRANTED`; обновлены только четыре Linux Chromium/WebKit goldens `progress-390x844-{dark,light}.png`; thresholds не менялись | Required CI на exact HEAD; отдельное разрешение на merge/release |
| #871, вариант B | `IMPLEMENTED_VERIFIED` | `OWNER_871_POLICY_APPROVAL=GRANTED_B`; server/client timezone guard, сохранение формы, race/dedupe; pytest, Vitest, Web/PWA/TMA Playwright | Required CI на exact HEAD; существенная новая визуальная переработка не заявлялась |
| #874, числовая parity и утверждённый visual package | `INTEGRATED_LOCAL_VERIFIED / OWNER_FINAL_VISUAL_APPROVAL_GRANTED / REQUIRED_CI_PENDING` | Owner approval `6128639269`; единая полнота данных, factual summary, one-record/empty states, цветные wellbeing/body графики, естественная pagination, cohesive «Сон и настроение», readable color/grayscale A4 и private `check_ins[].note` exclusion интегрированы в PR #963; targeted API/server-PDF/UI/browser-PDF/privacy checks зелёные | Required CI на итоговом exact HEAD; production/real-user proof и физические Safari/Telegram/VoiceOver не заявляются |
| #869/#870 | `PRESERVED` | Интегрированный код и существующие проверки не переписывались | Не расширять scope PR #963 |
| #914 | `PRESERVED` | Таймер отдыха, safe-area и защита от перекрытий сохранены; повторная интеграция не выполняется | Не расширять scope PR #963 |
| #946–#948 | `PRESERVED` | Утверждённый вариант поиска и keyboard states сохранены | Не расширять scope PR #963 |
| Пятиэлементная нижняя навигация | `PRESERVED / OWNER_APPROVED` | Существующий approved dock сохранён; отдельный floating `+` не добавлялся | Не запрашивать повторное визуальное согласование при неизменном результате |
| PR #966 | `ALREADY_INTEGRATED` | Уже является ancestry PR #963; повторная интеграция запрещена | Не cherry-pick/merge повторно |

## Release gates

`OWNER_874_FINAL_VISUAL_APPROVAL=GRANTED` · `MERGE=WAITING_OWNER_APPROVAL` ·
`DEPLOY=WAITING_OWNER_APPROVAL` · `AUTO_MERGE=DISABLED` · `env change required: no`.

Issues не закрываются этим техническим коммитом. После зелёного aggregate `checks` на точном
HEAD требуется отдельное разрешение владельца на merge/deploy.

## Текущая визуальная сверка #874

Утверждённый локальный пакет из `.artifacts/tasks/874-visual-proposal-20261012/` перенесён
в PR #963 без нового макета и без изменения бизнес-формул или API-контрактов. Реальные
локальные AFTER/PDF подтверждают:

- factual summary без пустой декоративной ячейки и единый блок «Полнота данных»;
- корректный one-record без выдуманного сравнения и пустые окружности без бессодержательной
  таблицы;
- цветной график массы тела, семантические 1–5 полосы сна/настроения с нулевыми категориями
  без заливки;
- cohesive блок «Сон и настроение», естественную pagination без orphan-заголовков и без
  жёсткого числа страниц;
- readable white color A4 и grayscale control.

Набор synthetic и локальный; он не доказывает production или real-user поведение. Финальный
технический gate — aggregate `checks` на exact HEAD в GitHub Actions.
