# Issue #870 — профиль без дублирующего меню

Статус: `EVIDENCE ONLY`. Production UI, `MiniAppPage.tsx`, `ProfileForm` и общие токены не изменялись. Этот пакет подготовлен для одного owner design approval до любой реализации layout.

## Baseline и границы

- Issue: [#870](https://github.com/MikeMoore1337/your-fitness-coach/issues/870).
- Исходный и текущий baseline: `8a5c955400de87eed8c92974bd196a8343c6cd35` (`origin/master`, 2026-10-16).
- Evidence-ветка: `codex/issue-870-profile-design`.
- Proposed-снимки получены из того же baseline в браузере: в synthetic render удалён только DOM-узел `.profile-settings-nav`; production DOM и CSS не менялись.
- Фикстуры браузера обезличены: `Анна`, синтетические параметры, без данных владельца и пользователей.
- AI Coach в proposed UI отсутствует. Пункт меню и карточка не возвращаются; legacy hash получает безопасный fallback.
- `design-v2.css`, `ux-ia-redesign.css`, UI-токены, API, RBAC, данные и production-компоненты в этой стадии не менялись.

Точки проверки на baseline SHA: [MiniAppPage.tsx](https://github.com/MikeMoore1337/your-fitness-coach/blob/8a5c955400de87eed8c92974bd196a8343c6cd35/frontend/src/pages/miniapp/MiniAppPage.tsx#L281-L420), [profile nav render](https://github.com/MikeMoore1337/your-fitness-coach/blob/8a5c955400de87eed8c92974bd196a8343c6cd35/frontend/src/pages/miniapp/MiniAppPage.tsx#L628-L785), [ProfileForm](https://github.com/MikeMoore1337/your-fitness-coach/blob/8a5c955400de87eed8c92974bd196a8343c6cd35/frontend/src/features/profile/ProfileForm.tsx#L225-L390), [profile CSS](https://github.com/MikeMoore1337/your-fitness-coach/blob/8a5c955400de87eed8c92974bd196a8343c6cd35/frontend/src/styles/design-v2.css#L5526-L5805), [task-294](https://github.com/MikeMoore1337/your-fitness-coach/blob/8a5c955400de87eed8c92974bd196a8343c6cd35/frontend/tests/e2e/task-294-mobile-first-ux.spec.ts#L314-L492), [task-295](https://github.com/MikeMoore1337/your-fitness-coach/blob/8a5c955400de87eed8c92974bd196a8343c6cd35/frontend/tests/e2e/task-295-today-daily-snapshot.spec.ts#L425-L455).

## Что проверено

BEFORE снят из собранного baseline через локальный Vite preview, Chromium и WebKit, с mock Platform API. Размеры: 320, 360, 390, 393, 430 px и desktop 1280 px; обе темы.

Полный BEFORE-пакет:

- mobile: [320](./evidence/before/before-mobile-320-light-chromium.png), [360](./evidence/before/before-mobile-360-light-chromium.png), [390](./evidence/before/before-mobile-390-light-chromium.png), [393](./evidence/before/before-mobile-393-light-chromium.png), [430](./evidence/before/before-mobile-430-light-chromium.png);
- desktop: [1280 Light](./evidence/before/before-desktop-1280-light-chromium.png), [1280 Dark](./evidence/before/before-desktop-1280-dark-chromium.png);
- WebKit-параллельная контрольная серия имеет те же имена с суффиксом `-webkit` в каталоге [evidence/before](./evidence/before).

PROPOSED снят с автономного HTML-макета в Chromium во всех требуемых размерах и темах:

- [Light mobile 320](./evidence/proposed/proposed-mobile-320-light.png), [360](./evidence/proposed/proposed-mobile-360-light.png), [390](./evidence/proposed/proposed-mobile-390-light.png), [393](./evidence/proposed/proposed-mobile-393-light.png), [430](./evidence/proposed/proposed-mobile-430-light.png);
- [Dark mobile 320](./evidence/proposed/proposed-mobile-320-dark.png), [360](./evidence/proposed/proposed-mobile-360-dark.png), [390](./evidence/proposed/proposed-mobile-390-dark.png), [393](./evidence/proposed/proposed-mobile-393-dark.png), [430](./evidence/proposed/proposed-mobile-430-dark.png);
- [Light desktop 1280](./evidence/proposed/proposed-desktop-1280-light.png) и [Dark desktop 1280](./evidence/proposed/proposed-desktop-1280-dark.png).

## Результаты воспроизведения

### `CONFIRMED`

1. Верхний `.profile-settings-nav` дублирует функциональные секции ниже: пять shortcut-строк повторяют `profile-personal`, вложенный `profile-fitness`, `profile-trainer`, `profile-notifications` и `profile-security`. Это видно в каждом BEFORE-снимке. AI Coach среди пяти строк baseline отсутствует после #1021.
2. Hash-only переходы не проходят через resolver deep link. При последовательном переходе внутри уже открытого профиля `#profile-trainer`, `#profile-notifications` и `#profile-security` остаются закрытыми; прямой reload той же ссылки раскрывает `details`.
3. `#profile-ai-coach` при hash-only переходе остаётся в URL, хотя `#profile-ai-coach` в DOM и текст `AI Coach` отсутствуют. Прямая загрузка legacy URL уже заменяется на `/app?section=profile`. Причина в текущем effect: он зависит от `section`/`search` и статуса AI, но не от изменения hash.

### `ALREADY_FIXED`

1. Длинная цель не обрезается: `#profile-goal-value` переносит текст и допускает разрыв длинного значения. Это уже доставлено через #910/#966 и не повторяется в proposed scope.
2. На мобильной ширине список тренировочных предпочтений не создаёт отдельную вложенную вертикальную прокрутку: после #966 для `max-width: 760px` используется обычная прокрутка страницы. Desktop-ограничение списка остаётся существующим локальным affordance и этой задачей не меняется.

### `NOT_REPRODUCED`

1. Наложение заголовка «Профиль и настройки» на описание не воспроизвелось в 30 измерениях: Light/Dark × 1024/1280/1440/1920/2560 × 100/125/150% emulated zoom. Во всех строках `overlapPx=0`, горизонтального overflow нет.
2. Physical iPhone/Safari, Telegram Mini App и VoiceOver не проверялись: `NOT_VERIFIED`. Chromium/WebKit evidence не является доказательством реального устройства, TMA или screen reader.

Машинные результаты: [hash-navigation.json](./evidence/runtime/hash-navigation.json) и [desktop-header.json](./evidence/runtime/desktop-header.json).

## Proposed: минимальное изменение композиции

Оставить текущий hero и все функциональные карточки/формы в прежнем порядке, удалить только верхний `profile-settings-nav`. Proposed-снимки — это тот же текущий экран с единственным evidence-only изменением: удалением верхнего nav из DOM.

```text
Profile page
├─ hero: «Профиль и настройки» + описание
├─ details#profile-personal
│  └─ section#profile-fitness (внутри profile-personal, включая «Цели»)
├─ existing TrainingPreferencesForm / training-preferences-card
├─ details#profile-trainer
├─ details#profile-notifications
└─ details#profile-security
```

Новые карточки, AI Coach, новый service/controller/state, изменение токенов или изменение бизнес-данных не предлагаются. Proposed не является новым layout: это визуальная проверка удаления одного дублирующего блока с сохранением native/ARIA-семантики, SVG-иконок, фокуса, контраста и touch targets текущей системы.

## Контракт deep links и истории после approval

До реализации нужно утвердить этот контракт вместе с макетом:

1. `#profile-personal` раскрывает `details#profile-personal`; `#profile-fitness` раскрывает родительский `details#profile-personal` и прокручивает к вложенной секции; остальные три hash раскрывают свои существующие `details`.
2. Валидный hash сохраняется в URL и работает при прямой загрузке, hash-only переходе, `back`, `forward` и reload. Раскрытие не создаёт лишнюю запись истории.
3. Старый `#profile-ai-coach` не создаёт AI UI и не оставляет мёртвый hash: нормализуется в `/app?section=profile` через replace-семантику; тот же fallback действует при прямой загрузке и переходе внутри уже открытого профиля.
4. После удаления верхнего меню `activeProfileNavTarget` и `openProfileSection` больше не нужны: текущие вызовы находятся только в shortcut-навигации. Остаётся общий hash resolver для раскрытия `details`, scroll и history; его обработка должна быть независима от удалённого active-nav state.
5. Оставшиеся ссылки `#profile-ai-coach` в скрытых AI entry points не должны возвращать пункт меню, карточку или пустой placeholder. Их legacy fallback должен вести в обычный профиль.

## Будущая реализация и тесты — только после approval

- Обновить `MiniAppPage.tsx` минимальным удалением верхнего nav и shared hash resolver без изменения `ProfileForm`, API/RBAC и данных.
- Удалить только мёртвые `activeProfileNavTarget`/`openProfileSection` и старые active-nav assertions; не удалять `profile-fitness` или «Цели».
- Переписать устаревшие ожидания пяти/шести shortcut-строк в `task-294` и `task-295` на существующие секции, `details`, hash/history и отсутствие AI UI. Проверить также `profile-settings-simplification.spec.ts` и `profile-goal-value.spec.ts`, где сейчас кликается верхнее меню.
- Добавить regression cases для каждого hash: direct load, same-document hash-only transition, keyboard activation, `back`, `forward`, reload, parent `details.open`, no horizontal overflow; отдельно `#profile-ai-coach` → обычный профиль без AI DOM.
- Повторить Light/Dark и все 320/360/390/393/430 + desktop 1024/1280/1440/1920/2560; затем получить реальное AFTER и отдельное owner visual acceptance.

## Гейт владельца

Требуется один явный `owner design approval` именно для удаления верхнего `profile-settings-nav` в представленном Dark/Light комплекте. До этого approval: нет production layout implementation, PR, merge, auto-merge и deploy. После approval следующий шаг — отдельная команда на реализацию утверждённой версии 1:1; она не включена в этот коммит.
