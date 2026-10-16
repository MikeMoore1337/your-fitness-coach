# #869 — AFTER браузерные кадры компактной гидратации

Ранее утверждённая владельцем структура: [#869 approval 14.10.2026](https://github.com/MikeMoore1337/your-fitness-coach/issues/869#issuecomment-6167084075), прототип PR #991 `33703af7c737e9e30d8c90116320d5f5ab72ecb8`. Повторное согласование неизменённого дизайна не требуется, но реальные AFTER и release permission нужны отдельно.

Подтверждённое направление: сводка и быстрый ввод → история за день (3 последние записи, полный список по действию при 4+) → сворачиваемые личный ориентир/кружки; native Planner/Grocery disclosures; белое H₂O с тонкой тёмной обводкой. Числа и сохранение не изменялись; AI Coach остаётся скрытым.

Синтетические кадры с локального Chromium:

- [Web Mobile Light, compact](mobile-web-light-compact.png)
- [Web Mobile Light, quick add/undo](mobile-web-light-quick-add-undo.png)
- [Mock TMA Dark, expanded + reduced motion](mock-tma-dark-expanded-reduced-motion.png)

Кадры не являются доказательством реальных Safari/iPhone/TMA/VoiceOver; полный визуальный Dark/Light-пакет и отдельный owner AFTER acceptance остаются обязательными до release. Локальные тесты согласно Codex: Vitest 11/11, Playwright 8/8 #869, hydration 4/4, contrast 14/14, build/typecheck/lint PASS; exact CI еще не проверен. Исходные личные снимки пользователя не публиковались. **No merge/deploy.**
