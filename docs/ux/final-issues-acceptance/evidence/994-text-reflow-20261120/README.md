# #994 — Progress и тренировка при увеличенном тексте

Часть единого AFTER-пакета #994. Снимки сделаны в Chromium и WebKit на локальном приложении с синтетическими данными. Исходная ревизия для сравнения — `b4e854eb82541b7bf272e6d6925aead0ae5173a5`. PNG сохранены в исходном разрешении; длинные листы разделены по целым снимкам.

Ранее принятые изменения: [карточка Today, PR #1501](https://github.com/MikeMoore1337/your-fitness-coach/pull/1501) и [dock, Quick Add и Today, AFTER на точном SHA](https://github.com/MikeMoore1337/your-fitness-coach/blob/973fdb6097ac4d2cd066d95b9e587c216e454d59/docs/ux/final-issues-acceptance/evidence/994-dock-p2-20261119/README.md).

## Увеличенный текст 200%

| Состояние | Браузер | Тема | Ширины и снимки |
| --- | --- | --- | --- |
| Progress, до и после | chromium | light | [320px / before, 360px / before, 390px / before, 393px / before, 430px / before](after/progress-chromium-light-a.png) · [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/progress-chromium-light-b.png) |
| Progress, до и после | chromium | dark | [320px / before, 360px / before, 390px / before, 393px / before, 430px / before](after/progress-chromium-dark-a.png) · [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/progress-chromium-dark-b.png) |
| Progress, до и после | webkit | light | [320px / before, 360px / before, 390px / before, 393px / before, 430px / before](after/progress-webkit-light-a.png) · [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/progress-webkit-light-b.png) |
| Progress, до и после | webkit | dark | [320px / before, 360px / before, 390px / before, 393px / before, 430px / before](after/progress-webkit-dark-a.png) · [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/progress-webkit-dark-b.png) |
| Тренировка, до и после | chromium | light | [320px / before, 360px / before, 390px / before, 393px / before, 430px / before](after/workout-chromium-light-a.png) · [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/workout-chromium-light-b.png) |
| Тренировка, до и после | chromium | dark | [320px / before, 360px / before, 390px / before, 393px / before, 430px / before](after/workout-chromium-dark-a.png) · [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/workout-chromium-dark-b.png) |
| Тренировка, до и после | webkit | light | [320px / before, 360px / before, 390px / before, 393px / before, 430px / before](after/workout-webkit-light-a.png) · [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/workout-webkit-light-b.png) |
| Тренировка, до и после | webkit | dark | [320px / before, 360px / before, 390px / before, 393px / before, 430px / before](after/workout-webkit-dark-a.png) · [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/workout-webkit-dark-b.png) |
| Progress: справка раскрыта | chromium | light | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/help-chromium-light.png) |
| Progress: справка раскрыта | chromium | dark | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/help-chromium-dark.png) |
| Progress: справка раскрыта | webkit | light | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/help-webkit-light.png) |
| Progress: справка раскрыта | webkit | dark | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/help-webkit-dark.png) |
| Progress: фокус с клавиатуры | chromium | light | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/focus-chromium-light.png) |
| Progress: фокус с клавиатуры | chromium | dark | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/focus-chromium-dark.png) |
| Progress: фокус с клавиатуры | webkit | light | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/focus-webkit-light.png) |
| Progress: фокус с клавиатуры | webkit | dark | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/focus-webkit-dark.png) |
| Progress: свой период | chromium | light | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/custom-chromium-light.png) |
| Progress: свой период | chromium | dark | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/custom-chromium-dark.png) |
| Progress: свой период | webkit | light | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/custom-webkit-light.png) |
| Progress: свой период | webkit | dark | [320px / after, 360px / after, 390px / after, 393px / after, 430px / after](after/custom-webkit-dark.png) |

## Desktop при обычном тексте

| Экран | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
| --- | --- | --- | --- | --- |
| Progress 1280 px | [chromium light](after/progress-desktop-chromium-light.png) | [chromium dark](after/progress-desktop-chromium-dark.png) | [webkit light](after/progress-desktop-webkit-light.png) | [webkit dark](after/progress-desktop-webkit-dark.png) |
| Тренировка 1280 px | [chromium light](after/workout-desktop-chromium-light.png) | [chromium dark](after/workout-desktop-chromium-dark.png) | [webkit light](after/workout-desktop-webkit-light.png) | [webkit dark](after/workout-desktop-webkit-dark.png) |

## Проверки и границы

- Адресная регрессия: пять ширин, две темы, Chromium/WebKit; подписи, выбранный период, Enter/Escape, раскрытие справки и возврат из тренировки. До исправления проверка обрезания падала в обоих движках.
- При обычном тексте сравнивались пиксели заголовка, периодов и заголовка тренировки с чистым dev на 320–430, 768, 1280, 1440 и 1920 px в двух темах и движках.
- Настоящий zoom вкладки Chromium 200% проверен на исходных 320, 360, 390, 393, 430 и 640 px: фактический viewport 160, 180, 195, 196, 215 и 320 CSS px. Проверялись подписи, раскрытие справки, форма периода и ширина документа. Снимки выше показывают увеличенный базовый шрифт, не browser zoom.
- Сохранённые эталоны питания не совпали с текущим изображением и так же не совпали на чистом dev; эталоны не менялись. Физические iPhone, Safari, VoiceOver и настоящий Telegram: NOT_VERIFIED.
- Этот пакет не является приёмкой оставшихся разделов V14 и не подтверждает production release.
