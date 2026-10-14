# Проверка DOM-вставки дизайн-прототипов

Mode: `diff`. Base: `2fe1fee667c99358c25e798392f39e5d6fec763f`; исправленный код закреплён exact SHA в основном README пакета.

Проверены `compact-hydration.html`, `completed-workout.html` и адресная регрессия в `closeout-prototypes.spec.ts`. Это изолированные демонстрационные страницы без production auth, пользовательских записей или внешнего API. Полный security audit продукта не выполнялся.

Инвариант: текст disclosure остаётся текстом; только постоянный утверждённый SVG передаётся HTML-парсеру. Значения демонстрационных форм не должны превращаться в исполняемую разметку.

CodeQL run `38511505020` заблокировал два `js/xss-through-dom` candidates: `summary.textContent` повторно передавался в `innerHTML`. Labels в текущих HTML статические; практический attacker-controlled вход и эксплуатация в production не подтверждены. Небезопасный шаблон вставки всё равно устранён: `createElement`, `textContent`, `replaceChildren`, затем постоянный Icon SVG. Новых trust boundaries нет. Escape пользовательских подписей истории и `textContent` для имён ёмкостей сохранены.

Проверки: 24/24 существующих prototype cases Chromium/WebKit после исправления; 2/2 negative cases с безвредной строкой, похожей на HTML, подтверждают отсутствие созданного элемента. HTML/PNG повторно сопоставлены. Подавления, allowlist и ослабления CodeQL не добавлялись; результат нового exact-head CodeQL указан в PR #991.

Status: `NO_CONFIRMED_FINDINGS` в проверенном исправленном flow. Это не утверждение о полном security coverage или разрешение на выпуск. Остальные security controls проверяются обычными required CI jobs.
