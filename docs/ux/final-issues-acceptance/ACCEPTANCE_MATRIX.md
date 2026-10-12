# PR #963 — acceptance matrix

Срез этой матрицы относится только к техническому завершению PR #963. Контрольный исходный
HEAD: `296a13837e31cbb5de311b139ac566027f5f24a7`. Итоговый exact HEAD и required Checks
публикуются в комментарии PR после завершения CI.

| Область | Статус в PR #963 | Доказательство | Оставшееся условие |
|---|---|---|---|
| #865, «О показателях» | `IMPLEMENTED_VERIFIED` | Одобрено владельцем `OWNER_865_VISUAL_APPROVAL=GRANTED`; обновлены только четыре Linux Chromium/WebKit goldens `progress-390x844-{dark,light}.png`; thresholds не менялись | Required CI на exact HEAD; отдельное разрешение на merge/release |
| #871, вариант B | `IMPLEMENTED_VERIFIED` | `OWNER_871_POLICY_APPROVAL=GRANTED_B`; server/client timezone guard, сохранение формы, race/dedupe; pytest, Vitest, Web/PWA/TMA Playwright | Required CI на exact HEAD; существенная новая визуальная переработка не заявлялась |
| #874, числовая parity | `IMPLEMENTED_VERIFIED` | Один canonical JSON fixture для API/UI/browser PDF/server PDF; фактическое извлечение PDF-текста; проверены empty и one-record, даты, периоды, единицы и privacy boundaries | Required CI на exact HEAD; production/real-user proof не заявляется |
| #869/#870 | `PRESERVED` | Интегрированный код и существующие проверки не переписывались | Не расширять scope PR #963 |
| #914 | `PRESERVED` | Таймер отдыха, safe-area и защита от перекрытий сохранены; повторная интеграция не выполняется | Не расширять scope PR #963 |
| #946–#948 | `PRESERVED` | Утверждённый вариант поиска и keyboard states сохранены | Не расширять scope PR #963 |
| Пятиэлементная нижняя навигация | `PRESERVED / OWNER_APPROVED` | Существующий approved dock сохранён; отдельный floating `+` не добавлялся | Не запрашивать повторное визуальное согласование при неизменном результате |
| PR #966 | `ALREADY_INTEGRATED` | Уже является ancestry PR #963; повторная интеграция запрещена | Не cherry-pick/merge повторно |

## Release gates

`MERGE=FORBIDDEN` · `DEPLOY=FORBIDDEN` · `AUTO_MERGE=FORBIDDEN` · `env change required: no`.

Issues не закрываются этим техническим коммитом. После зелёного aggregate `checks` на точном
HEAD требуется отдельное разрешение владельца на merge/deploy.
