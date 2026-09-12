# Bounded Codex Code Review для final semantic gate

Файл сохраняет историческое имя для durable-ссылок, но действующий контракт больше не запрещает
Codex review полностью. Automatic Code Review в Codex/GitHub integration не включается изменениями
репозитория. Review запускается только явной controller-командой после GREEN exact-head required
`checks`; review-job в CI и отдельный reviewer-agent не создаются.

## Канонический quality gate

```text
implementation
→ targeted verification
→ final deterministic verification
→ один bounded self-review implementer
→ commit/push
→ PR в master
→ exact-head required CI GREEN
→ Codex review round 1
→ CLEAN → merge
→ blocking P0/P1 → один batch fix → affected checks → push → exact-head CI GREEN
→ Codex review round 2
→ CLEAN → merge | blocking P0/P1 → HUMAN_REQUIRED
→ post-merge cleanup
→ product-task deploy/production closeout, если требуется task contract
```

Controller хранит round state в shared Git common-dir и перед запросом проверяет PR, current head,
mergeability, exact-head `checks`, comments/reviews и resolved threads. Запрос для уже pending или
completed SHA переиспользуется. Разрешены максимум два managed requests на PR: round 2 возможен
только после blocking P0/P1 round 1 и изменившегося head SHA. MEDIUM/LOW/NIT не открывают round 2,
clean verdict не запускается повторно, третий request запрещён. Повторный blocking P0/P1 после
round 2 возвращает `HUMAN_REQUIRED` с точным blocker report.

Профильные QA, security, legal, human, external и destructive gates сохраняются. Codex review их
не заменяет; `master` остаётся PR-only, exact-head CI и aggregate `checks` не ослабляются.

## Внешняя настройка

Если владелец хочет отключить внешнюю автоматическую настройку Code Review, это выполняется вручную
в Codex/GitHub integration settings; repository не создаёт secret, token или автоматическое правило.
Недоступная внешняя настройка не блокирует repository changes и указывается как
`MANUAL_EXTERNAL_SETTING`.
