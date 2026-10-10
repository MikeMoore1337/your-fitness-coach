# #859 · Ритм YFC · пакет финальной приёмки

Реальные снимки работающего приложения, не макеты. Код AFTER: `18d3e7224164b201d50679858713bb015f5227db` — единая ветка с исходными головами PR #907–#911. Голова для итогового CI: `7605801a7b9f695ffeded58ad08e5b9bf3b9b92a`; после съёмки менялись только состояние E2E-снимка и PNG-эталоны, runtime-исходники идентичны. BEFORE: `9a6594af1d674eaf4ca1bc419b0569c5a5a6c036` (master 0277d132 и PR #907). Все сведения о пользователях и записи — фиксированные синтетические fixtures.

[Интерактивная галерея](index.html) · [PR #915](https://github.com/MikeMoore1337/your-fitness-coach/pull/915) · [CI](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38044270525) · [Сравнение меню](comparisons/quick-add-comparison.jpg) · [Серверный PDF](pdf/server-report.pdf) · [Печать браузером](pdf/browser-report.pdf) · [Manifest и SHA-256](manifest.json)

OWNER_UI_APPROVAL=APPROVED. MERGE=false. DEPLOY=false. FINAL_STATUS=STOP_OWNER_RELEASE_APPROVAL. env change required: no.

## Прямые ссылки

| Размер / тема | BEFORE · меню | AFTER · меню | Все основные экраны AFTER | Сравнение |
|---|---|---|---|---|
| 360 / dark | [BEFORE](before/webkit-360-dark-quick-add.png) | [AFTER](after/webkit-360-dark-quick-add.png) | [8 экранов](comparisons/after-360-dark-overview.jpg) | [BEFORE/AFTER](comparisons/comparison-360-dark.jpg) |
| 360 / light | [BEFORE](before/webkit-360-light-quick-add.png) | [AFTER](after/webkit-360-light-quick-add.png) | [8 экранов](comparisons/after-360-light-overview.jpg) | [BEFORE/AFTER](comparisons/comparison-360-light.jpg) |
| 393 / dark | [BEFORE](before/webkit-393-dark-quick-add.png) | [AFTER](after/webkit-393-dark-quick-add.png) | [8 экранов](comparisons/after-393-dark-overview.jpg) | [BEFORE/AFTER](comparisons/comparison-393-dark.jpg) |
| 393 / light | [BEFORE](before/webkit-393-light-quick-add.png) | [AFTER](after/webkit-393-light-quick-add.png) | [8 экранов](comparisons/after-393-light-overview.jpg) | [BEFORE/AFTER](comparisons/comparison-393-light.jpg) |
| 430 / dark | [BEFORE](before/webkit-430-dark-quick-add.png) | [AFTER](after/webkit-430-dark-quick-add.png) | [8 экранов](comparisons/after-430-dark-overview.jpg) | [BEFORE/AFTER](comparisons/comparison-430-dark.jpg) |
| 430 / light | [BEFORE](before/webkit-430-light-quick-add.png) | [AFTER](after/webkit-430-light-quick-add.png) | [8 экранов](comparisons/after-430-light-overview.jpg) | [BEFORE/AFTER](comparisons/comparison-430-light.jpg) |

## Границы доказательств

Проверены установленные движки Chromium и WebKit, 360/393/430 px и обе темы; desktop, native focus/Tab/Escape, маршруты пяти действий, короткий TMA viewport и safe-area. Клавиатура проверена через сокращение visualViewport, Telegram API — harness. Физический iPhone, VoiceOver и настоящий клиент Telegram в этой среде не проверены. Это локальная проверка приложения и интеграционный CI; production не менялся.

#871: защита от прошедшего календарного дня включена из PR #911. Политика времени, уже прошедшего сегодня, требует решения владельца. Читаемая длительность тренировки и заголовок справочника остаются INTENDED. #872: нужен исходный XLSX; импорт не изменялся без файла.

## Исходные PR сохранены

- [#907](https://github.com/MikeMoore1337/your-fitness-coach/pull/907): `9a6594af1d674eaf4ca1bc419b0569c5a5a6c036`
- [#908](https://github.com/MikeMoore1337/your-fitness-coach/pull/908): `5023563aba71f11cf742a3a6b6d49d9d8bfb105f`
- [#909](https://github.com/MikeMoore1337/your-fitness-coach/pull/909): `c56cc2b37347d781846bf80566634ba19c900525`
- [#910](https://github.com/MikeMoore1337/your-fitness-coach/pull/910): `e35b988ecb9ba71f0e169c68596f2d53096f7373`
- [#911](https://github.com/MikeMoore1337/your-fitness-coach/pull/911): `578f5704cac780c02720e84cff2a96cdb7dd481e`

Каждый скриншот открывается отдельной прямой ссылкой из галереи; все файлы сохранены в Git. Immutable commit URLs сохраняют доступ после завершения Codex. Бизнес-данные, расчёты, API и доступные действия сохранены; PDF меняет типографику и переносы.
