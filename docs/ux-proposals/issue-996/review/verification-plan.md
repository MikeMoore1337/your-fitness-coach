# План проверки после owner approval

Это план, а не заявка о выполненной production-проверке.

## E2E / браузер

- Web Chromium и WebKit, 360/393/430, light/dark, synthetic API: открыть замену, получить 3–5 кандидатов, выбрать radio, открыть «Все подходящие», искать, применить допустимый equipment-фильтр; проверить DOM overflow, focus, `aria-live`, `aria-describedby` и сохранение search value.
- Request assertions: GET query содержит только выбранные `available_equipment_ids`; preview ровно один на submit; apply содержит тот же request + `preview_token`; до apply не меняются workout/program endpoints.
- Negative matrix: GET error/retry, empty, offline, preview 503/retry, apply 409/re-preview, duplicate submit, reopen, started/completed target, pain_or_injury, foreign workout/authorization.
- WebKit/headless — evidence only. Physical iPhone/Safari, native Telegram Mini App, OS keyboard and VoiceOver remain separate `NOT_VERIFIED` gates.

## Vitest

- Быстрый список: 3 visible + full response, search/filter never creates an item outside response, no-result copy.
- Search focus/value survives rerender; Escape/close returns focus to invoking control if a second layer is approved.
- Preview/apply remain separate; disabled/pending/offline/conflict states; no program/future mutation in request mocks.
- Reason allowlist has neutral fallback; unknown key is not rendered as a fabricated user promise.

## Pytest

- Existing `list_compatible_alternatives` and replacement tests remain green: equipment subset, metric, visible/avoided/used, unstarted target, curated/planned fallback distinction.
- Existing preview/apply tests remain green: stale token/target facts/409, idempotent identical apply, program snapshot unchanged, pain safety stop and audit.
- Add no new backend test until a concrete production contract change is approved; design-only stage must not alter server behavior.
