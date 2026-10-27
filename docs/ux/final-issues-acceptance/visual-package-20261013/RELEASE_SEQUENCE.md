# PR #991 — безопасная последовательность выпуска

Подготовлено 14.10.2026. Выпуск не разрешён этим документом: Draft #991 ожидает окончательного визуального согласования владельца и отдельного разрешения на merge/release. Merge, auto-merge, deploy и закрытие Issues в этой задаче не выполняются.

## Проверенная исходная точка

- Исходный head #991: `f0f3597f521aaf2d34132f0abfd590b51910b3dc`; точечная поправка и AFTER: `7212fae63c0ae797d13fc8359bed6909f465e34b`. Итоговый PR head и его exact-head CI указаны в описании PR; документационный commit не меняет код поправки.
- Текущий `origin/master`, **B**: `11cff463834fd41c1392d646f6baaf361ac9bebc`. Он является предком #991 и его merge-base с master.
- Последний доказанный Actions deploy, **P**: `18bb76443deccf165d9d466eef65ffa8cdb2c968`. [Release run 38295723565](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38295723565), [job 114966297913](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38295723565/job/114966297913): `Deployment verdict: active; revision=18bb76443deccf165d9d466eef65ffa8cdb2c968; slot=legacy`, 12.10.2026 19:11:18 UTC.
- Более поздний successful run [38304774683](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38304774683) на B пропустил job deploy. Success такого workflow не доказывает выпуск B. Другие более поздние просмотренные runs 38377700695 и 38530721096 — SKIPPED.
- P является предком B; diff P..B содержит только документацию UX. Новых миграций в `backend/alembic/versions` между P и текущим объединённым кандидатом нет. `env change required: no`.

P — последняя найденная запись успешного выпуска, а не новая проверка сегодняшнего runtime через SSH. Перед будущим выпуском нужно подтвердить активную ревизию существующей read-only проверкой provenance.

## Уже объединённые исходные PR

Состояния и головы повторно прочитаны из GitHub; все шесть PR OPEN. Для каждой головы `git merge-base --is-ancestor <head> <candidate>` вернул 0, а проверка относительно B — 1. Их код уже входит в #991 и ещё не входит в master.

| PR                                                                   | Проверенный head                           | Предок #991 | Предок B |
| -------------------------------------------------------------------- | ------------------------------------------ | ----------- | -------- |
| [#976](https://github.com/MikeMoore1337/your-fitness-coach/pull/976) | `68f80d8e08e35ff76656d5b439a9abc9fd86505f` | да          | нет      |
| [#988](https://github.com/MikeMoore1337/your-fitness-coach/pull/988) | `aa6809a66461a86e4719d0bf1cb29a4a3786ef62` | да          | нет      |
| [#987](https://github.com/MikeMoore1337/your-fitness-coach/pull/987) | `2f4370bb2cabe3738ef5b1899037bf01b1d62f4b` | да          | нет      |
| [#975](https://github.com/MikeMoore1337/your-fitness-coach/pull/975) | `3ada8a324b02250d900c7e66d02c739c2de86f85` | да          | нет      |
| [#973](https://github.com/MikeMoore1337/your-fitness-coach/pull/973) | `04f2dbd255be009de1a29cfb599b02ca6e8912f4` | да          | нет      |
| [#974](https://github.com/MikeMoore1337/your-fitness-coach/pull/974) | `f0ed33e3151b9b061f21f6c3096b1ca2ac5f80af` | да          | нет      |

Повторно merge/cherry-pick этих исходных голов не требуется. Если перед выпуском голова любого PR изменилась, её новые уникальные commits не считаются включёнными: остановить интеграцию и отдельно сверить scope с владельцем.

## Один будущий маршрут

1. Получить финальное визуальное согласование пакета и разрешение владельца на merge/release. Старые согласования неизменённых элементов сохраняются; #869/#871 остаются design-only. Зелёный CI сам по себе разрешения не даёт.
2. Обновить Git/GitHub: актуальный master, head #991, heads исходных PR, ancestry, unresolved review threads и required `checks`. Native rules требуют strict current-base; при изменении базы получить новый проход Checks. Подтвердить активный P и повторно проверить миграции/config delta, не используя только workflow conclusion.
3. Интегрировать **только #991 штатным GitHub merge commit**. Репозиторий разрешает этот метод; обязательной линейной истории нет. Он сохраняет ancestry всех шести исходных PR. Обозначить фактический `mergeCommit.oid` как **M**; сейчас M ещё не существует. Не подменять M PR head или исходной головой одного из шести PR.
4. Проверить, что все шесть проверенных голов являются предками M. Повторно прочитать состояния исходных PR: GitHub может отметить содержащиеся commits как merged. Не выполнять их повторную интеграцию или автоматическое закрытие Issues.
5. Дождаться успешного **CI push master именно на M**. PR CI проверяет кандидата, но не заменяет проверку release revision. Затем использовать штатный `Release production` после CI: тот же M, immutable tested bundle, существующая последовательность миграций, rollout и smoke. Не выпускать по очереди шесть исходных PR и не отправлять старый исторический SHA на deploy.
6. Подтвердить deployment evidence и read-only provenance: runtime/backend/worker/bot revision и digests соответствуют M, migration heads согласованы, health/smoke успешны. Выполнить ограниченную проверку затронутых сценариев объединённого пакета, включая Nutrition target cards/print и сохранение программы #967. Отделять synthetic browser proof от физических iPhone/Safari, native Telegram и VoiceOver, которые здесь NOT_VERIFIED.
7. При неуспехе остановить выпуск. Использовать существующий owner-authorized rollback только к совместимой, известной успешной production evidence (P после повторной проверки), с учётом миграций. Не переписывать master и не создавать локальный release controller.

Этот документ не запускает Actions, не меняет production и не создаёт новую очередь работ. После пакета #991 текущая задача останавливается.
