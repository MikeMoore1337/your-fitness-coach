# #867 — safe-area и резерв под нижнюю навигацию

Актуальный срез для [Draft PR #976](https://github.com/MikeMoore1337/your-fitness-coach/pull/976). Изображения сняты в CI `38350144075` из mocked TMA-сценария с синтетическими данными. Историческое доказательство `evidence/867` не изменяется.

## BEFORE / AFTER

| Движок | BEFORE — golden до изменения | AFTER — фактический CI-снимок |
| --- | --- | --- |
| Chromium | [PNG](before-chromium-dark.png) | [PNG](after-chromium-dark.png) |
| WebKit | [PNG](before-webkit-dark.png) | [PNG](after-webkit-dark.png) |

После исправления содержимое получает дополнительный фактический резерв под измеренную высоту dock и `visualViewport` bottom offset. Пять элементов панели, порядок, тексты и визуальная композиция dock не менялись. Цель изменения — исключить перекрытие последнего контента и hit target, а не добавить новый dock или скрыть overflow.

В CI оба браузера подтвердили остальные мобильные сценарии: `10 passed`; оставшееся падение — ожидаемое расхождение full-page golden из-за добавленного резерва высотой 84 CSS px. DOM geometry/hit-test assertions проходят. Linux goldens обновлены только фактическими AFTER-снимками этого CI run; thresholds и тесты не ослаблялись.

Ранее утверждённая пятиэлементная визуальная композиция dock сохраняется. `CURRENT_GEOMETRY_VISUAL_ACCEPTANCE=PENDING`; физический iPhone/Safari, настоящий Telegram-клиент и VoiceOver не проверялись. `MERGE=FORBIDDEN; DEPLOY=FORBIDDEN`.
