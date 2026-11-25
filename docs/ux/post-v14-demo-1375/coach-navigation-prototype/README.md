# Макет навигации тренерского Demo

**Статический макет для предварительного решения владельца.** Это не реализованный интерфейс и не подтверждение его работы. Снимки сделаны в локальном Chromium с синтетическими данными; в DOM временно подставлена предлагаемая навигация поверх действующего Demo. Изменения интерфейса приложения для этого макета не вносились.

## Предложение

- В мобильном рабочем пространстве тренера показывать существующие разделы Coach OS в общем dock: «Сегодня», «Клиенты», «Программы», «Ещё». Текущий раздел имеет общий выбранный стиль. Локальную повторную навигацию скрыть.
- В мобильном рабочем пространстве тренера убрать персональный Quick Add из dock, как в текущем Coach OS. Вернуться к персональному пространству и его действиям можно через существующий переключатель «Для себя». Доступ к сценарию, сбросу и выходу сохраняется через существующую границу Demo.
- На desktop оставить существующую оболочку и показывать разделы тренера через общий `SegmentedControl`, как в Coach OS. Существующие содержимое, палитра и типографика не меняются.

## Все состояния одного варианта

Chromium: mobile 390×844 и desktop 1440×900. Каждый файл — отдельный статический кадр, переключение вкладок и другие действия в изображениях не работают. Данные и имена синтетические.

| Состояние | Mobile light | Mobile dark | Desktop light | Desktop dark |
| --- | --- | --- | --- | --- |
| Граница Demo | [mobile light](mobile-light-boundary.png) | [mobile dark](mobile-dark-boundary.png) | [desktop light](desktop-light-boundary.png) | [desktop dark](desktop-dark-boundary.png) |
| Сегодня | [mobile light](mobile-light-today.png) | [mobile dark](mobile-dark-today.png) | [desktop light](desktop-light-today.png) | [desktop dark](desktop-dark-today.png) |
| Клиенты | [mobile light](mobile-light-clients.png) | [mobile dark](mobile-dark-clients.png) | [desktop light](desktop-light-clients.png) | [desktop dark](desktop-dark-clients.png) |
| Программы | [mobile light](mobile-light-programs.png) | [mobile dark](mobile-dark-programs.png) | [desktop light](desktop-light-programs.png) | [desktop dark](desktop-dark-programs.png) |
| Ещё | [mobile light](mobile-light-tools.png) | [mobile dark](mobile-dark-tools.png) | [desktop light](desktop-light-tools.png) | [desktop dark](desktop-dark-tools.png) |

## Границы и проверка после решения

Макет не проверяет клики, клавиатуру, фокус, BackButton, safe-area, жесты, reduced motion, отсутствие переполнения на всех ширинах или работу реального Telegram. После принятия потребуется реализация с повторным использованием AppShell и Coach OS, проверка маршрутов и ограничений Demo, отдельная автоматизированная и браузерная проверка, реальные AFTER-снимки и отдельная визуальная приёмка. Это решение не разрешает merge или deploy.

**Решение:** принять или отклонить этот единый вариант для реализации. До принятия навигационная композиция в приложении не меняется.
