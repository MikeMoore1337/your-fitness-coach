# Issue #997 — предпросмотр программы до назначения

Статус пакета: **DESIGN_ONLY / до owner design approval**. Production JSX, production CSS, API,
миграции и бизнес-логика в этом пакете не изменялись.

Проверенная база: `origin/master` SHA `4c92832415d4eb994cf6b849a67074742f07ea50`.
Рабочая ветка: `codex/issue-997-program-preview-design`.

После решения владельца подпись `до назначения` закреплена как единый неразрывный токен во
всех трёх встречах в прототипе: вводном тексте, статусном чипе карточки и ownership-строке.
У токена `white-space: nowrap`; на узких экранах статусный чип переходит в отдельную строку,
а provenance-источники фактов переносятся внутри своих карточек через `overflow-wrap:anywhere`.
Это не уменьшает кегль и не меняет production-композицию: preview остаётся только макетом.

Единый финальный макет: [`prototype.html`](prototype.html). В нём одна композиция предпросмотра,
переключаемая на синтетические состояния готового шаблона, собственной программы, программы,
назначенной тренером, многонедельного источника и legacy без метаданных. Переключатель темы и
нативные controls нужны для review, а не являются новым production-компонентом.

Все значения в HTML синтетические. Они не являются production-данными и не требуют доступа к
пользовательским аккаунтам. AI Coach в макет не включён.

## Что проверено на текущем master

Текущий пользовательский путь находится в `frontend/src/features/programs/TemplatesList.tsx`:

1. Список загружает `/api/v1/programs/templates/mine` и получает полный `ProgramTemplateResponse`.
2. Карточка показывает тип программы, название и сокращённые метаданные. Кнопка `Посмотреть`
   открывает локальный preview modal.
3. Вторичное действие уже различает `Настроить копию` и `Редактировать` по правам.
4. Текущее основное действие `Запустить` сразу ведёт к расписанию назначения. В отдельном modal
   выбираются дата, срок и дни, а замена активной программы подтверждается отдельно.
5. Уже назначенная программа отображает `AssignedProgramDetails` с lifecycle, следующей
   тренировкой, блоками и ревизиями. Это post-assignment подробности, а не источник фактов для
   preview до назначения.

`ProgramRecommendation.tsx` уже имеет отдельный deterministic preview/confirm-путь генератора.
Он не объединяется с предпросмотром существующего `ProgramTemplateResponse`. Старый
`LegacyProgramRecommendation.tsx` передаёт выбранный шаблон в тот же preview modal через
`onPreview`.

Закрытая #863 уже выпущена и отвечает за компактное представление текущей активной программы,
этапа, недели и следующего действия. #997 не дублирует этот overview и не возвращает AI Coach.
Последняя цепочка, указанная в Issue #863: PR #915 → интеграция #963 → production SHA
`f99f1954c007567cefeec7dc882f14e68de6b0ba`; физические iPhone/Safari, TMA и VoiceOver там также
не были доказаны.

Проверенные связанные PR:

- [PR #915](https://github.com/MikeMoore1337/your-fitness-coach/pull/915) — merged,
  merge commit `18bb76443deccf165d9d466eef65ffa8cdb2c968`.
- [PR #963](https://github.com/MikeMoore1337/your-fitness-coach/pull/963) — merged в тот же
  integration commit; это не реализация #997.

## Контракт достоверных фактов

| Факт в предпросмотре | Источник на текущем API | Правило отображения |
| --- | --- | --- |
| Дни | `template.days.length`, `days[].title` | Показывать количество дней в составе шаблона и названия дней. Это не превращать в недельную частоту без отдельного источника. |
| Частота | `program_metadata.days_per_week` у seed-данных; `assigned_program_schedule_weekdays` только у назначения | Показывать только при числовом/явном значении и подписывать источник. Иначе `Нет данных`. |
| Состав недели | `days[].exercises[]`, `exercise_title`, `prescribed_sets/reps/duration_minutes`, `rest_seconds`, `notes` | Показать все названия дней и один раскрытый пример дня. Не добавлять отсутствующие подходы, минуты или порядок недель. |
| Уровень | `template.level` и, где применимо, `program_metadata.level` | Показать только непустое известное значение. Пустое, неизвестное или legacy значение — `Нет данных`. |
| Оборудование | `program_metadata.equipment` у seed-шаблонов; у упражнений в domain-модели есть nullable legacy `equipment` | Не выводить частичный список как полный. Если источник не даёт полного безопасного списка — `Нет данных`. |
| Многонедельные данные | `default_duration_weeks`, явные `weekly_prescriptions` | Показывать только факт источника: например, `12 недель в исходных prescriptions`. Не выводить типы недель, повторы или периодизацию, которых нет в текущем контракте назначения. |
| Длительность | В `ProgramTemplateResponse` нет общего подтверждённого поля оценки длительности | В production показывать `Нет данных`, пока сервер не вернёт отдельную помеченную оценку с источником. В макете `≈45 мин` — только синтетический пример с подписью `оценка, не фактическое время`. |
| Владелец/назначивший | `owner_user_id`, `can_edit`, `is_example`, `assigned_by_user_id`, `assigned_by_full_name` | Всегда показывать вид программы и владельца/назначившего, не смешивая «моя программа» с назначенной тренером. |
| Версия назначения | `assigned_program_revision_number`, `current_revision_number`, `assigned_program_updated` | Показывать только в назначенном состоянии. Перед применением проверять актуальную ревизию; stale response не должен тихо назначать устаревший preview. |

`default_duration_weeks == null` имеет только безопасное эффективное значение модели `1` для
существующих операций. Это не доказательство того, что пользователь выбрал одну неделю, и не
разрешает рисовать периодизацию. Ручные программы создаются с `program_metadata = null`;
legacy-ветка должна сохраняться честной.

## Предложенная композиция

Одна и та же composition показана в [`prototype.html`](prototype.html) как desktop side sheet и
как полноэкранный mobile dialog:

`вид программы и ownership → название → factual facts → состав недели → пример дня → source note → actions`.

Факты находятся выше действий, а неизвестные значения остаются видимыми как `Нет данных`.
Многонедельный state содержит заметку `только исходные данные`, чтобы не имитировать UI
планируемого cycle editor из V12.

Действия разделены намеренно:

| Действие | Разрешённый эффект | Не должно происходить |
| --- | --- | --- |
| `Посмотреть` | Открыть preview | Запрос назначения, изменение active program или ownership |
| `Закрыть` | Закрыть preview | Изменение active program |
| `Выбрать` | Сохранить выбор только в текущем flow | Немедленное назначение или архивирование |
| `Создать копию` | Создать отдельную личную копию только при разрешённом праве | Присвоение ownership тренерского шаблона пользователю без copy-операции; потеря provenance |
| `Редактировать` | Открыть editor только при `can_edit` | Появление кнопки у read-only назначения тренером |
| `Назначить` | Открыть расписание и отдельное явное подтверждение | Тихая замена активной программы; изменение от просмотра/закрытия |

При наличии активной программы подтверждение должно прямо сообщить о замене и сохранении
истории. Архивирование старой программы происходит только на уже существующем server-side
confirm/assign пути, а не в preview.

## Матрица состояний для будущей реализации

| Состояние | Что видно | Ожидаемые действия |
| --- | --- | --- |
| Готовый шаблон, 1 неделя | Полные seed metadata, дни, equipment, optional synthetic estimate | `Посмотреть`, `Выбрать`, `Назначить`, `Создать копию`; `Редактировать` отсутствует |
| Собственная программа | `Моя программа`, `can_edit`, факты только из собственных полей | `Посмотреть`, `Выбрать`, `Редактировать`, при отдельном copy-flow — `Создать копию`, `Назначить` |
| Назначена тренером | Назначивший, статус, срок назначения и ревизия; read-only для клиента | `Посмотреть`, `Закрыть`; self-edit/self-assign не появляются без отдельного разрешения |
| Явный многонедельный источник | `weekly_prescriptions`/срок только как факт источника | Не называть это новым cycle editor или автоматическим повтором; отсутствие contract — `Нет данных` |
| Legacy без metadata | Дни и доступные упражнения; level/frequency/equipment/duration/periods — `Нет данных` | Не подставлять `1 неделя`, уровень, минуты или периодизацию из догадки |
| Устаревший preview/version | Сообщение об обновлении данных | Не отправлять назначение по stale ревизии; оставить active program без изменения |

## Контракт проверок после owner approval

Это не production test в текущем design-only пакете. После отдельного разрешения на реализацию
нужны targeted browser/API проверки:

- Dark/Light: Chromium desktop и mobile synthetic viewports, без горизонтального overflow;
- tab order: `Закрыть → facts/expand → actions`, видимый `:focus-visible`, Esc/close без mutation;
- preview GET и закрытие не меняют active program, assignment, owner или history;
- `Выбрать` не вызывает assign endpoint; `Назначить` требует explicit confirmation;
- готовый, собственный и trainer-assigned ownership/permission matrix;
- одна неделя, явный много-недельный source и legacy без metadata;
- обновление версии и stale/409 response без тихого применения старого preview;
- no AI Coach node/CTA/empty placeholder;
- сохранение current API, RBAC, provenance и уже существующего Coach OS assignment;
- реальные AFTER Dark/Light после реализации и отдельный owner visual acceptance.

Физический iPhone/Safari, native TMA и VoiceOver в этом пакете **NOT_VERIFIED**. Chromium
viewport и условный keyboard focus не являются доказательством этих сред.

## Реальное браузерное evidence текущего макета

PNG и машинный отчёт созданы из `file://`-прототипа в установленном Microsoft Edge
`141.0.3537.57` через Playwright Chromium; это реальные браузерные captures, не синтетически
нарисованные изображения. Матрица — Dark/Light, `320/360/393/430/1440 × 900`:

- [`dark-320.png`](evidence/dark-320.png), [`dark-360.png`](evidence/dark-360.png),
  [`dark-393.png`](evidence/dark-393.png), [`dark-430.png`](evidence/dark-430.png),
  [`dark-1440.png`](evidence/dark-1440.png);
- [`light-320.png`](evidence/light-320.png), [`light-360.png`](evidence/light-360.png),
  [`light-393.png`](evidence/light-393.png), [`light-430.png`](evidence/light-430.png),
  [`light-1440.png`](evidence/light-1440.png);
- [`card-dark-320.png`](evidence/card-dark-320.png) и [`card-light-320.png`](evidence/card-light-320.png)
  показывают карточку с видимым чипом после закрытия предпросмотра;
- [`long-title-light-393.png`](evidence/long-title-light-393.png),
  [`text-size-125-light-393.png`](evidence/text-size-125-light-393.png) и
  [`confirmation-dark-393.png`](evidence/confirmation-dark-393.png) покрывают длинный заголовок,
  диагностическое увеличение размера текста 125% и явное подтверждение назначения;
- [`checks.json`](evidence/checks.json) содержит viewport-геометрию, `nowrap`, отсутствие
  горизонтального overflow/клиппинга, матрицу фикстур, различие действий и keyboard/focus.

Все assertions этого run прошли: две встречи видимой подписи имеют `white-space: nowrap`,
статусный чип остаётся внутри карточки, источники фактов не расширяют контейнер, а `Нет данных`
сохраняется для неполных и legacy-полей. Увеличение текста проверено браузерным root-text
diagnostic 125%; системные настройки доступности ОС не проверялись.

## Что не входит

- новый endpoint, migration, длительный estimator или алгоритм подбора;
- включение V11/V12/V13/V14;
- реализация cycle editor и планируемых повторов #916/#919/#920;
- изменения `AssignedProgramDetails` beyond the factual contract;
- возвращение AI Coach;
- правки общих CSS из #1002 или редактора циклов V12;
- merge, auto-merge, deploy или изменение production.

## Следующий gate

Сначала нужен **explicit owner design approval именно этого единого Dark/Light mobile/desktop
пакета**. После него — отдельная implementation-задача/PR с минимальным изменением
`TemplatesList`/preview, затем real AFTER evidence, отдельное owner visual acceptance и только
после отдельного разрешения — merge/release.

Существующий [Draft PR #1043](https://github.com/MikeMoore1337/your-fitness-coach/pull/1043)
обновляется этим пакетом. Merge, auto-merge и deploy в этой design-only стадии не выполнялись.
