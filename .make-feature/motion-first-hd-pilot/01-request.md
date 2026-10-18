# Request

## Scope

Нужен отдельный Draft-пилот после визуально неуспешного RIFE baseline: сравнить original/native/RIFE, не выпускать ghosted или анатомически сомнительные клипы, закрепить provenance и права, а также добавить тестируемые ограничения обработки.

## Exclusions

- не менять `backend/assets/exercise-guides/manifest.json`, production media, существующие approved HD, PR #1111/#1094/#1109;
- не запускать массовую обработку 90/206 упражнений;
- не считать browser/desktop capture доказательством iPhone, Telegram WebView, VoiceOver или production.

## Acceptance

Каждый кандидат имеет canonical mapping, source SHA, rights basis, technical metadata, motion/ghosting/technique review status, exact output path и no-overwrite evidence. Неизвестное состояние остаётся `MOTION_SOURCE_REVIEW`; hard reject никогда не обходит pipeline.
