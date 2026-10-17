# Issue #1048 — структура настроек КБЖУ

Скриншоты сделаны на синтетических данных fixture API, без пользовательских или владелецких
данных.

## BEFORE

Источник: `origin/master` на SHA `396bae69530d6d21c2de89b11daa2d48c3f824d5` до изменения.

- [Mobile Web 390×844 Dark](before/mobile-web-390x844-dark.png)
- [Mobile Web 768×900 Dark](before/mobile-web-768x900-dark.png)
- [Mock TMA 390×844 Light](before/tma-mock-390x844-light.png)

На исходном состоянии видны последовательные раскрытия «Настройки питания» → «КБЖУ» и
вложенная карточка формы.

## AFTER

Пакет Chromium после реализации:

- Mobile Web: [320 Light](after/mobile-web-320x760-light.png), [360 Light](after/mobile-web-360x800-light.png), [393 Dark](after/mobile-web-393x852-dark.png), [430 Light](after/mobile-web-430x932-light.png)
- Desktop Web: [1280 Dark](after/desktop-web-1280x900-dark.png), [1440 Light](after/desktop-web-1440x900-light.png)
- Mock TMA: [320 Dark](after/tma-mock-320x760-dark.png), [360 Dark](after/tma-mock-360x800-dark.png), [393 Light](after/tma-mock-393x852-light.png), [430 Dark](after/tma-mock-430x932-dark.png)

Дополнительная проверка компоновки после интеграции с принятой #1047 (Chromium, закрытые секции):

- [Mobile overview 393×844 Dark](after/mobile-overview-393x844-dark.png)
- [Mobile overview 393×844 Light](after/mobile-overview-393x844-light.png)

На AFTER секция называется «Настройки КБЖУ», находится перед планом питания и списком покупок,
а режимы и форма видны сразу после одного раскрытия. Во всех трёх закрытых секциях
сохранены одинаковые рамки, фон и интервал 16px из #1047.
Внешний dock остаётся частью viewport;
достижимость кнопки сохранения отдельно проверяется после прокрутки к ней.

## Проверки

- `npm run typecheck`
- `npm run lint`
- `npm exec prettier -- --check ...` для изменённых исходников и E2E
- адресные Vitest: `NutritionForm.test.tsx`, `nutritionCalculator.test.ts` — 25 тестов
- Chromium: порядок/название/одно раскрытие, ручной режим, валидация, сохранение, история,
  touch targets, overflow, dock и AFTER matrix
- WebKit: тот же ручной сценарий и AFTER matrix

Тесты не меняют формулы расчёта, API, модели данных или сохранённые цели.
