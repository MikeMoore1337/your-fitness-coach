# Реальная навигация Demo тренера после реализации

Снимки сделаны в локальном Chromium с реальным FastAPI, SQLite и синтетическими данными. Это фактический интерфейс после реализации, а не временная подстановка DOM. Mobile: 390×844; desktop: 1440×900. Физический Safari/iPhone и Telegram Mini App не проверены.

[Согласованный макет](../coach-navigation-prototype/README.md) · [Видео: разделы тренера и переход «Для себя»](coach-navigation-after.webm)

| Состояние | Mobile light | Mobile dark | Desktop light | Desktop dark |
| --- | --- | --- | --- | --- |
| Граница Demo | [mobile light](mobile-light-boundary.png) | [mobile dark](mobile-dark-boundary.png) | [desktop light](desktop-light-boundary.png) | [desktop dark](desktop-dark-boundary.png) |
| Сегодня | [mobile light](mobile-light-today.png) | [mobile dark](mobile-dark-today.png) | [desktop light](desktop-light-today.png) | [desktop dark](desktop-dark-today.png) |
| Клиенты | [mobile light](mobile-light-clients.png) | [mobile dark](mobile-dark-clients.png) | [desktop light](desktop-light-clients.png) | [desktop dark](desktop-dark-clients.png) |
| Программы | [mobile light](mobile-light-programs.png) | [mobile dark](mobile-dark-programs.png) | [desktop light](desktop-light-programs.png) | [desktop dark](desktop-dark-programs.png) |
| Ещё | [mobile light](mobile-light-tools.png) | [mobile dark](mobile-dark-tools.png) | [desktop light](desktop-light-tools.png) | [desktop dark](desktop-dark-tools.png) |

Демо-версия раздела программ показывает доступную сводку и ограничение редактирования без обращения к недоступным операциям. Действия, фокус, адаптивность и ограничения проверяются отдельно тестами; снимки не являются визуальной приёмкой владельца.

[Парные BEFORE / AFTER личных разделов и переключателя возврата](../personal-navigation-comparison/README.md).
