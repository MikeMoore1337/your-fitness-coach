---
name: accessibility-engineer
description: >
  Design, implement and verify accessible Web, Telegram Mini App and mobile product experiences.
  Use when a task changes navigation, forms, dialogs, data visualizations, responsive behavior,
  keyboard/focus handling, semantic HTML, contrast, motion, errors or any user-facing UI. Do not use
  as a substitute for real assistive-technology checks or to claim full WCAG conformance without evidence.
---

# accessibility-engineer

Работай как профильный инженер по доступности продукта. Твоя задача - встроить доступность в фактический UX и код, а не добавить несколько `aria-*` атрибутов перед релизом.

## Когда подключать

Skill обязателен, если задача затрагивает хотя бы одно из следующего:

- новую страницу, форму, навигацию или интерактивный сценарий;
- modal, dialog, drawer, sheet, popover, dropdown или tooltip;
- клавиатуру, focus, tab order, escape/back behavior;
- график, таблицу, прогресс, цветовую индикацию или статус;
- ошибки, валидацию, loading/empty/partial/disabled states;
- responsive/mobile/TMA layout, safe areas или экранную клавиатуру;
- анимацию, мигание, auto-scroll или reduced motion;
- публичный контент, heading hierarchy, landmarks или ссылки;
- upload, auth, destructive action или другой high-risk flow;
- утверждение о WCAG/accessibility readiness.

Не подключай skill к чистому backend-refactor без пользовательского контракта, если API и ошибки не меняются.

## Базовый стандарт

Цель - практическое соответствие WCAG 2.2 AA для релевантных поверхностей, но итоговый отчёт должен различать:

- проверено автоматически;
- проверено вручную клавиатурой;
- проверено с assistive technology;
- проверено только по коду;
- не проверено из-за ограничений среды.

Не заявляй полное соответствие на основании Lighthouse/axe или unit-тестов.

## Сначала

1. Определи основной пользовательский сценарий и его критические действия.
2. Найди существующие Design V2 primitives и accessibility contracts.
3. Проверь DOM/semantic tree, а не только визуальный снимок.
4. Определи keyboard и focus lifecycle до реализации.
5. Зафиксируй состояния: default, hover, focus-visible, active, disabled, loading, error, success, empty, partial.
6. Определи текстовую альтернативу всем визуальным данным.
7. Проверь mobile/TMA отдельно: touch targets, zoom, safe areas, viewport и keyboard.

## Семантика и структура

- Используй нативный элемент, когда он существует: `button`, `a`, `input`, `select`, `dialog`, `table`, `details`.
- Не превращай `div` в кнопку без крайней необходимости.
- Один логичный `h1`; уровни заголовков не выбираются ради размера шрифта.
- Landmarks и доступные имена должны помогать навигации, а не дублировать шум.
- Ссылки описывают назначение вне контекста; не использовать десятки одинаковых «Подробнее» без доступного имени.
- Иконка без текста получает точное accessible name; декоративная иконка скрывается.
- Не дублируй одинаковый текст для screen reader через несколько вложенных элементов.

## Keyboard и focus

Для каждого интерактивного сценария опиши и проверь:

- ожидаемый tab order;
- видимый `focus-visible`;
- открытие с клавиатуры;
- Escape/Back behavior;
- начальный focus при открытии dialog/sheet;
- focus trap только там, где это действительно modal;
- возврат focus инициатору после закрытия;
- отсутствие keyboard trap;
- сохранение focus после async update/delete/reorder;
- отсутствие неожиданного auto-focus на mobile.

Drag-and-drop не может быть единственным способом перестановки. Нужна доступная альтернатива.

## Формы и ошибки

- Label должен быть программно связан с полем.
- Placeholder не заменяет label.
- Required, hint, unit и error объявляются однозначно.
- Ошибка сообщает, что исправить, и связывается с полем.
- После submit пользователь получает summary/focus на первую ошибку без потери введённых данных.
- Цвет не является единственным носителем ошибки или успеха.
- Формат даты, времени, веса, повторов и КБЖУ должен быть понятен.
- Destructive action требует ясного имени объекта и предсказуемого подтверждения.
- Disabled control не должен быть единственным способом объяснить, почему действие недоступно.

## Responsive, touch и reflow

Проверяй минимум 1440, 1280, 768, 430, 390 и 360 px, touch/`hover: none`, а также увеличение текста/масштаб браузера.

- Никакого обязательного горизонтального scroll, кроме оправданной специализированной области с альтернативой.
- Touch targets должны быть практически удобны, особенно во время тренировки; для primary controls ориентир не меньше 44x44 px.
- Fixed/sticky UI не перекрывает content, focus, safe areas и экранную клавиатуру.
- На 200%/400% zoom основной сценарий остаётся выполнимым.
- Длинные имена упражнений, продуктов, клиентов и локализованный текст не ломают композицию.

## Цвет, визуальные данные и motion

- Проверяй contrast текста, controls, focus indicator и meaningful graphics в обеих темах.
- Не полагайся на цвет для статусов, графиков, RIR, прогресса или календаря.
- График получает текстовое описание, units, period и доступ к точкам/таблице.
- Skeleton/loading не мигает и не объявляется бесконечно.
- Respect `prefers-reduced-motion`; критическое действие не зависит от анимации.
- Избегай flashing, сильного parallax и автоматической карусели без управления.

## TMA и mobile

Для Telegram Mini App дополнительно используй `references/MOBILE_TMA_ACCEPTANCE_MATRIX.md` и проверь:

- safe areas и content safe areas;
- Telegram BackButton и browser history;
- current/stable viewport resize, keyboard и focus visibility;
- foreground/background restore без потери accessible state;
- theme change без потери focus/state;
- отсутствие конфликта platform controls с shared controls;
- доступность при использовании только touch и только внешней клавиатуры, где применимо.

Telegram theme не оправдывает снижение контраста или отдельную несогласованную palette.

## Проверки

Минимальный набор в зависимости от scope:

- semantic/component tests;
- automated axe/аналог как smoke, не как доказательство полного соответствия;
- ручной keyboard pass;
- focus order и focus restoration;
- screen-reader spot checks для критичных сценариев, если среда доступна;
- light/dark;
- 360/390/768/desktop;
- zoom/reflow;
- errors/loading/empty/partial;
- reduced motion;
- touch target review;
- TMA mock или реальный client с честной фиксацией уровня проверки.

## Результат

В отчёте укажи:

- какие сценарии проверены;
- какие barriers исправлены;
- какие проверки выполнены автоматически и вручную;
- известные ограничения;
- remaining issues с severity и воспроизводимостью;
- почему сделанные изменения не ухудшили основной UX.

## Внешний чек-лист

При необходимости используй `../../references/external-quality/ui-skills/fixing-accessibility.md`
для точечного поиска проблем; не приравнивай его выполнение к доказательству WCAG.
