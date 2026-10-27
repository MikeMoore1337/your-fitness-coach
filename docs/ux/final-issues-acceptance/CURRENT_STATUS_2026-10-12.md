# Актуальная сверка мобильной приёмки YFC - 12.10.2026

Это **сверка фактических статусов GitHub Issues** после публикации PR #963, а не переоценка подробных критериев исторического аудита от 11 октября. Старые доказательства и снимки сохраняются в [ISSUE_COVERAGE_MATRIX.md](ISSUE_COVERAGE_MATRIX.md). Статус Open означает открытую задачу, даже если часть исправлений уже в production.

## Подтверждённые факты

- [PR #963](https://github.com/MikeMoore1337/your-fitness-coach/pull/963) объединён с master, merge SHA [18bb76443deccf165d9d466eef65ffa8cdb2c968](https://github.com/MikeMoore1337/your-fitness-coach/commit/18bb76443deccf165d9d466eef65ffa8cdb2c968).
- [CI master](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38295366309) и [Release production](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38295723565) завершились SUCCESS.
- PR #907-#911, #915, #927, #958 интегрированы через #963; PR #941 - отдельная документация.
- Issue #874 закрыта после публикации; повторно открывать её из-за нового #970 не нужно.
- Физические Safari/iOS, Telegram, VoiceOver и авторизованные сценарии не объявляются проверенными на основании синтетических Chromium/WebKit тестов.

## Исходная выборка из 22 Issues

Таблица содержит **GitHub Open/Closed на 12.10.2026**, а не автоматический вывод, что каждый acceptance criterion пройден.

| Issue | GitHub | Текущее состояние и остаток |
|---|---|---|
| [#859](https://github.com/MikeMoore1337/your-fitness-coach/issues/859) | Open | Индекс мобильного аудита, новые дефекты привязаны к существующим и новым задачам |
| [#860](https://github.com/MikeMoore1337/your-fitness-coach/issues/860) | Open | Preview замены выпущен через PR #963; критерии Issue ещё требуют закрытия |
| [#861](https://github.com/MikeMoore1337/your-fitness-coach/issues/861) | Open | Picker выпущен; реальный iPhone показывает длинный список фильтров до результатов в справочнике |
| [#862](https://github.com/MikeMoore1337/your-fitness-coach/issues/862) | Open | Мобильный редактор выпущен; дефект синхронизации активного плана вынесен в #967 |
| [#863](https://github.com/MikeMoore1337/your-fitness-coach/issues/863) | Open | Улучшения Плана выпущены, но полный состав критериев Issue не закрыт |
| [#864](https://github.com/MikeMoore1337/your-fitness-coach/issues/864) | Open | После релиза на iPhone обнаружена отсутствующая верхняя рамка Расписания |
| [#865](https://github.com/MikeMoore1337/your-fitness-coach/issues/865) | Open | После релиза раскрытие О показателях перекрывает заголовок Прогресс |
| [#866](https://github.com/MikeMoore1337/your-fitness-coach/issues/866) | Open | Компактные завершённые упражнения выпущены; Issue ожидает фактической приёмки |
| [#867](https://github.com/MikeMoore1337/your-fitness-coach/issues/867) | Open | Реальный iPhone показывает перекрытие содержимого нижней панелью |
| [#868](https://github.com/MikeMoore1337/your-fitness-coach/issues/868) | Open | Прямой переход к воде включён в PR #963; Issue открыта |
| [#869](https://github.com/MikeMoore1337/your-fitness-coach/issues/869) | Open | Утверждённые UI-изменения выпущены; весь исходный объем приёмки не подтверждён |
| [#870](https://github.com/MikeMoore1337/your-fitness-coach/issues/870) | Open | Утверждённые UI-изменения выпущены; весь исходный объем приёмки не подтверждён |
| [#871](https://github.com/MikeMoore1337/your-fitness-coach/issues/871) | Open | Вариант B напоминаний согласован и реализован; остаток mobile-критериев не закрыт |
| [#873](https://github.com/MikeMoore1337/your-fitness-coach/issues/873) | Open | Реальный iPhone показывает разные стрелки и скрытую активную вкладку Прогресса |
| [#874](https://github.com/MikeMoore1337/your-fitness-coach/issues/874) | Closed | Report/PDF/privacy выпущены; новый дефект таблицы вынесен в #970 |
| [#903](https://github.com/MikeMoore1337/your-fitness-coach/issues/903) | Closed | Исправления оформления оценок лендинга; Issue закрыта |
| [#904](https://github.com/MikeMoore1337/your-fitness-coach/issues/904) | Closed | Демо 403 coach inbox; Issue закрыта |
| [#905](https://github.com/MikeMoore1337/your-fitness-coach/issues/905) | Closed | Демо 403 exercise history; Issue закрыта |
| [#906](https://github.com/MikeMoore1337/your-fitness-coach/issues/906) | Closed | Лендинг QHD, визуальный вариант B; Issue закрыта |
| [#946](https://github.com/MikeMoore1337/your-fitness-coach/issues/946) | Open | Поиск продуктов выпущен через PR #963, формальное закрытие не выполнялось |
| [#947](https://github.com/MikeMoore1337/your-fitness-coach/issues/947) | Open | Контраст выбранного продукта выпущен через PR #963, Issue открыта |
| [#948](https://github.com/MikeMoore1337/your-fitness-coach/issues/948) | Open | Читаемость выдачи продуктов выпущена через PR #963, Issue открыта |

## Production-находки после релиза, вне исходной выборки

| Issue | Статус | Описание |
|---|---|---|
| [#967](https://github.com/MikeMoore1337/your-fitness-coach/issues/967) | Backlog, P1 | Редактор назначенной программы показывает изменения, действующий план остаётся прежним |
| [#968](https://github.com/MikeMoore1337/your-fitness-coach/issues/968) | Backlog, P1 | Quick Add: поле времени за правой границей экрана |
| [#969](https://github.com/MikeMoore1337/your-fitness-coach/issues/969) | Backlog, P1 | Быстрый замер и самочувствие: нет очевидного выхода |
| [#970](https://github.com/MikeMoore1337/your-fitness-coach/issues/970) | Backlog, P2 | Переносы слов и столбцы в таблице изменений целей |

Новые реальные iPhone-наблюдения также внесены комментариями в #861, #864, #865, #867 и #873. Исходные личные скриншоты владельца в публичный GitHub не загружены.

## Сохранение доказательств и следующих шагов

- [Историческая интерактивная галерея](index.html) и [макеты варианта B лендинга #906](proposals/906-hero-qhd.md) сохранены.
- [Оригинальные 48 PNG PR #941](evidence/946-948/archive/pr941/README.md) сохранены отдельно; более новые канонические файлы after из master не затёрты.
- Для новых дефектов источником истины остаются соответствующие Issues и YFC Development. Нельзя закрывать их на основании факта публикации кода без приёмки.
- Документационный merge не меняет приложение: классификатор scripts/deployment_scope.py помечает изменения исключительно в docs как deploy_required=false.
- Для новых изменений внешнего вида нужны owner visual approval и отдельное разрешение на merge/deploy.
