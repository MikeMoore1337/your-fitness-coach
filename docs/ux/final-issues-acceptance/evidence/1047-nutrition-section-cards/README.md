# Issue #1047: мобильные карточки разделов питания

Синтетическое evidence для проверки регрессии в Chromium Web на viewport `393x844`.
Данные тестовые, персональные данные не использовались; анимации отключены.

## До исправления

- [Dark, BEFORE](before/chromium-mobile-393x844-dark.png)
- [Light, BEFORE](before/chromium-mobile-393x844-light.png)

На снимках разделы отображаются как строки с одним нижним разделителем.

## После исправления

- [Dark, AFTER](after/chromium-mobile-393x844-dark.png)
- [Light, AFTER](after/chromium-mobile-393x844-light.png)

Оба раздела снова имеют тонкую рамку со всех сторон, скругление и фон карточки.

## Ограничения evidence

Это browser/synthetic evidence, а не проверка физического iPhone, нативного Telegram,
VoiceOver или production.
