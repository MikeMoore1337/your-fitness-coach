# Адресный разбор семи сигналов CodeQL

Объём согласован владельцем: только семь сигналов в пяти исходных файлах PR #927. Правила CodeQL, severity gate, workflow и существующие исключения сохранены побайтно. Новые исключения, suppressions и paths-ignore не добавлены. [Исходные сигналы и hashes gate](codeql-remediation.json). Обязательный CI конкретного HEAD проверяется отдельно в [PR Checks](https://github.com/MikeMoore1337/your-fitness-coach/pull/927/checks).

Результат ограниченного security review после исправлений: **NO_CONFIRMED_FINDINGS**. Выполнение скрипта или утечка credentials по исходным семи трассам не подтверждены. Это не аудит всего продукта и не заявление об отсутствии любых уязвимостей.

| Файл / сигнал | Data flow и вывод | Изменение и регрессия |
|---|---|---|
| auth.py / clear-text logging | Лог получает только три фиксированные категории ошибки. OAuth state передаётся только как SHA256 prefix. CodeQL эвристически считает имена с `oauth` password-данными. | Helper и переменные названы по фактическому содержимому: категория ошибки провайдера. Нормализация, redirect и logging-поведение сохранены. 8 новых caplog-сценариев проверяют отсутствие raw state, token и password; 64 auth-теста прошли. |
| allure_report.py / weak hashing | MD5 использовался для historyId синтетического сбоя отчёта, не для пароля или токена. | SHA256 вместо MD5. UUID и статус сохранены; тест проверяет стабильность historyId и различие runs/issues. |
| stage-0 prototype / XSS | URL direction проверялся через includes, но в HTML попадало повторно прочитанное значение. DOM setter также принимал произвольное direction. XSS не воспроизведён. | Единый выбор одного из трёх строковых литералов. URL и DOM input проверены в Chromium/WebKit. |
| reset prototype / XSS, DOM XSS, dynamic call | Truthy lookup допускал унаследованные ключи `constructor`, `toString`, `__proto__`. Последний действительно ломал статический прототип. Production API и пользовательские данные недоступны этому прототипу. | Renderer выбирается только из собственных entries, HTML получает выбранное локальное имя. Некорректный ввод возвращает обычный экран. Все 13 экранов, query, select и delegated click проверены в обоих движках. |
| AccountIdentity / DOM XSS | Preview приходит из URL.createObjectURL(File), затем в React img.src. XSS не воспроизведён. | Общая проверка абсолютного HTTP(S) и same-origin blob для private/preview. data/javascript/file и чужой blob отсекаются. Предпросмотр, revoke, fallback, сохранение, удаление и TMA проверены. Fixture теперь моделирует HTTPS provider photo с прежними SVG bytes. |

Подтверждённый старый дефект: crafted `?screen=__proto__` делает исторический прототип пустым с TypeError. [BEFORE negative control](prototype-negative-control.json) воспроизводит это в Chromium и WebKit на aef7c2ed; [AFTER тест](security-prototypes-final.json) проходит. Impact ограничен статическим прототипом; компрометация аккаунта не доказана.

[24 browser checks](security-browser-results-final.json), [54 timer regressions после исправлений](security-joint-timer-results.json), [32 native-event сценария и 0 нежелательных mutations](native-actions.json), [остальные проверки](tests.json). Физические iPhone/VoiceOver/Telegram и production не проверялись; ни merge, ни deploy не выполнялись.
