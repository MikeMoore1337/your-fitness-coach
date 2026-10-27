# #869 и #870 - доказательства точечных улучшений

**Реальные браузерные скриншоты** из тестового интерфейса с синтетическими данными, не макеты. Сняты в Chromium/WebKit, Light/Dark на ширинах 320/360/393/430 CSS px. Не подтверждают физический iPhone, VoiceOver или нативную клавиатуру Telegram.

BEFORE: интеграционная ветка review/mobile-package-20261012 (20f4a019). AFTER: новая реализация ui/869-870-targeted-fixes-20261012, точный SHA указан в PR. Полный дизайн приложения и существующие маршруты сохранены.

### Что изменено

- #869: числа +250/+350/+500 мл теперь не разрываются, названия вторичны и перенесены по словам; добавлена защита от повторной записи при двух быстрых нажатиях. План питания/Список покупок уже компактны в исходной мобильной интеграции, их не перерисовывали.
- #870: полный текст выбранной цели выделен ниже нативного select, а список упражнений на телефоне прокручивается вместе со страницей без внутреннего ограниченного контейнера. Локальная навигация профиля сохранена, поскольку это рабочие переходы по разделам.

**Эти изображения - для визуальной приёмки владельца. Не выполнять merge/deploy до его явного решения.**

OWNER_VISUAL_APPROVAL=PENDING; MERGE=FORBIDDEN; DEPLOY=FORBIDDEN

## #869 - Питание

- Быстрые объёмы воды, BEFORE, dark, 320px, chromium: [скриншот](before/before-869-hydration-dark-320-chromium.png)
- Быстрые объёмы воды, AFTER, dark, 320px, chromium: [скриншот](after/after-869-hydration-dark-320-chromium.png)
- Быстрые объёмы воды, AFTER, dark, 320px, webkit: [скриншот](after/after-869-hydration-dark-320-webkit.png)
- План питания и покупки, BEFORE, dark, 393px, chromium: [скриншот](before/before-869-planning-dark-393-chromium.png)
- План питания и покупки, AFTER, dark, 393px, chromium: [скриншот](after/after-869-planning-dark-393-chromium.png)
- Быстрые объёмы воды, BEFORE, light, 320px, chromium: [скриншот](before/before-869-hydration-light-320-chromium.png)
- Быстрые объёмы воды, AFTER, light, 320px, chromium: [скриншот](after/after-869-hydration-light-320-chromium.png)
- Быстрые объёмы воды, AFTER, light, 320px, webkit: [скриншот](after/after-869-hydration-light-320-webkit.png)
- План питания и покупки, BEFORE, light, 393px, chromium: [скриншот](before/before-869-planning-light-393-chromium.png)
- План питания и покупки, AFTER, light, 393px, chromium: [скриншот](after/after-869-planning-light-393-chromium.png)
- Быстрые объёмы воды, AFTER, dark, 360px, chromium: [скриншот](after/after-869-hydration-dark-360-chromium.png)
- Быстрые объёмы воды, AFTER, dark, 430px, chromium: [скриншот](after/after-869-hydration-dark-430-chromium.png)

## #870 - Профиль

- Полная выбранная цель, BEFORE, dark, 320px, chromium: [скриншот](before/before-870-goal-dark-320-chromium.png)
- Полная выбранная цель, AFTER, dark, 320px, chromium: [скриншот](after/after-870-goal-dark-320-chromium.png)
- Полная выбранная цель, AFTER, dark, 320px, webkit: [скриншот](after/after-870-goal-dark-320-webkit.png)
- Навигация профиля, BEFORE, dark, 393px, chromium: [скриншот](before/before-870-nav-dark-393-chromium.png)
- Навигация профиля, AFTER, dark, 393px, chromium: [скриншот](after/after-870-nav-dark-393-chromium.png)
- Длинный список предпочтений, AFTER, dark, 393px, chromium: [скриншот](after/after-870-preferences-dark-393-chromium.png)
- Полная выбранная цель, BEFORE, light, 320px, chromium: [скриншот](before/before-870-goal-light-320-chromium.png)
- Полная выбранная цель, AFTER, light, 320px, chromium: [скриншот](after/after-870-goal-light-320-chromium.png)
- Полная выбранная цель, AFTER, light, 320px, webkit: [скриншот](after/after-870-goal-light-320-webkit.png)
- Навигация профиля, BEFORE, light, 393px, chromium: [скриншот](before/before-870-nav-light-393-chromium.png)
- Навигация профиля, AFTER, light, 393px, chromium: [скриншот](after/after-870-nav-light-393-chromium.png)
- Длинный список предпочтений, AFTER, light, 393px, chromium: [скриншот](after/after-870-preferences-light-393-chromium.png)
- Полная выбранная цель, AFTER, dark, 360px, chromium: [скриншот](after/after-870-goal-dark-360-chromium.png)
- Длинный список предпочтений, AFTER, dark, 360px, chromium: [скриншот](after/after-870-preferences-dark-360-chromium.png)
- Полная выбранная цель, AFTER, dark, 430px, chromium: [скриншот](after/after-870-goal-dark-430-chromium.png)
- Длинный список предпочтений, AFTER, dark, 430px, chromium: [скриншот](after/after-870-preferences-dark-430-chromium.png)
