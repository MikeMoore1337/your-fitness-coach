# Landing #1422: V10 → V4 → реализация

Сравнение подготовлено для [#1422](https://github.com/MikeMoore1337/your-fitness-coach/issues/1422) и последующей независимой проверки [#989](https://github.com/MikeMoore1337/your-fitness-coach/issues/989). Это снимки локальной сборки с синтетическими данными, а не production.

- Исходная сборка V10: `d7c04239d3296155092f3ae8169472c090e1b3d1`.
- Прототип V4: архив SHA-256 `4ed8f4bd0d1bd93fc694422aec5be2801dc4c67ddf13be22c3877b33ad421d72`.
- Код реализации на снимках: `159056b4f56e6168efa861717f646e17d7ae0e28`. Последующий коммит с этим пакетом добавляет только evidence.
- Chromium 151.0.7922.34, desktop 1440×900, mobile 390×844, `prefers-reduced-motion: reduce`. Снимки полностраничные; JPEG сжат для просмотра в GitHub. Полноразмерные PNG сохранены локально в `.artifacts/tasks/1422/evidence/159056b4f56e6168efa861717f646e17d7ae0e28/`.
- [Манифест снимков](manifest.json) содержит источник, viewport, качество JPEG и собранные ошибки страниц и HTTP-ответов. В 24 проходах ошибок страницы и HTTP-ответов 4xx/5xx не зафиксировано; внешние запросы были заблокированы, реальная аналитика и внешний вход этим не проверялись.

## Полные страницы

| Аудитория | Вид | Тема | V10 | V4 | AFTER |
| --- | --- | --- | --- | --- | --- |
| Для себя | Mobile | Light | [V10](v10-athlete-light-mobile.jpg) | [V4](v4-athlete-light-mobile.jpg) | [AFTER](after-athlete-light-mobile.jpg) |
| Для себя | Mobile | Dark | [V10](v10-athlete-dark-mobile.jpg) | [V4](v4-athlete-dark-mobile.jpg) | [AFTER](after-athlete-dark-mobile.jpg) |
| Для тренера | Mobile | Light | [V10](v10-coach-light-mobile.jpg) | [V4](v4-coach-light-mobile.jpg) | [AFTER](after-coach-light-mobile.jpg) |
| Для тренера | Mobile | Dark | [V10](v10-coach-dark-mobile.jpg) | [V4](v4-coach-dark-mobile.jpg) | [AFTER](after-coach-dark-mobile.jpg) |
| Для себя | Desktop | Light | [V10](v10-athlete-light-desktop.jpg) | [V4](v4-athlete-light-desktop.jpg) | [AFTER](after-athlete-light-desktop.jpg) |
| Для себя | Desktop | Dark | [V10](v10-athlete-dark-desktop.jpg) | [V4](v4-athlete-dark-desktop.jpg) | [AFTER](after-athlete-dark-desktop.jpg) |
| Для тренера | Desktop | Light | [V10](v10-coach-light-desktop.jpg) | [V4](v4-coach-light-desktop.jpg) | [AFTER](after-coach-light-desktop.jpg) |
| Для тренера | Desktop | Dark | [V10](v10-coach-dark-desktop.jpg) | [V4](v4-coach-dark-desktop.jpg) | [AFTER](after-coach-dark-desktop.jpg) |

## Состояния AFTER

| Аудитория и тема | Mobile | Desktop |
| --- | --- | --- |
| Для себя, Light | [Меню](after-athlete-light-menu-mobile.jpg), [результат подхода](after-athlete-light-interactive-mobile.jpg) | [FAQ](after-athlete-light-faq-desktop.jpg), [результат подхода](after-athlete-light-interactive-desktop.jpg) |
| Для себя, Dark | [Меню](after-athlete-dark-menu-mobile.jpg), [результат подхода](after-athlete-dark-interactive-mobile.jpg) | [FAQ](after-athlete-dark-faq-desktop.jpg), [результат подхода](after-athlete-dark-interactive-desktop.jpg) |
| Для тренера, Light | [Меню](after-coach-light-menu-mobile.jpg), [просмотр решения](after-coach-light-interactive-mobile.jpg) | [FAQ](after-coach-light-faq-desktop.jpg), [просмотр решения](after-coach-light-interactive-desktop.jpg) |
| Для тренера, Dark | [Меню](after-coach-dark-menu-mobile.jpg), [просмотр решения](after-coach-dark-interactive-mobile.jpg) | [FAQ](after-coach-dark-faq-desktop.jpg), [просмотр решения](after-coach-dark-interactive-desktop.jpg) |

## Границы проверки

- Автоматическая матрица проверяла ширины 320, 360, 390, 393, 430, 768, 1024, 1280, 1440 и 1920 в Chromium и WebKit. Это не проверка на физических устройствах Apple.
- Фактический desktop browser zoom 200%, VoiceOver, системный edge-back и экранная клавиатура: `NOT_VERIFIED`.
- В прототипе высота изображения питания на mobile вычисляется как 1024 px при ширине 350 px. В реализации изображение сохраняет пропорции; это отличие требует внимания при визуальной приёмке.
- Сохранены существующий раздел «Почему YFC» и интерактивный пример прогресса. Они отличаются от более короткой композиции V4. Существующие кнопки юридических документов по-прежнему показывают сообщение, что документы не подключены; реальные URL не подтверждены.
- Независимый visual critique: `NOT_RUN` по решению владельца, передан в #989. Визуальная приёмка AFTER и разрешение на выпуск — отдельные решения.
