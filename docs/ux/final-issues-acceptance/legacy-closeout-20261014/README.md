# YFC — Final Legacy PR Closeout, 14.10.2026

Один окончательный комплект для owner visual acceptance #979/#978/#972. #990 — правило приёмки без изображений; #971 закрыт как superseded. Новых Issues и дублирующих PR нет. Master/production не менялись.

**Проверенная база и production:** `f99f1954c007567cefeec7dc882f14e68de6b0ba`, release #991, [CI38555115853](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38555115853), [production38555590138](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38555590138). Оба SUCCESS; deploy log содержит тот же production SHA.

**Итоговый integration runtime SHA:** `cc2d8d13546de74132d10b1259e04dad35f94594`. Все новые PNG сняты заново на этой сборке; старые снимки PR не используются как AFTER. Evidence files закреплены в `5dd5abb806800a4efe1b0a0f5aa56a5763d0df47`. Последующие commits этого пакета меняют только документацию и изображения: frontend tree и runtime не меняются.

## Итог по исходным PR

| Issue / PR | Точный итоговый SHA | Изменение | Проверки | CI | Visual status | Remaining |
|---|---|---|---|---|---|---|
| #959 / [#990](https://github.com/MikeMoore1337/your-fitness-coach/pull/990) | e3149f05043c12fcfd1f15ca3adcaa2c2460e0da | Единый окончательный пакет; отдельные mockup/AFTER/release gates; все прежние инструкции сохранены | diff, hooks, буквальная сохранность master вне нового блока | [SUCCESS38561477554](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38561477554) | Изображения не требуются | Отдельное разрешение на merge |
| #873 / [#979](https://github.com/MikeMoore1337/your-fitness-coach/pull/979) | bace7c8564b8f479022d837784c111902b105a55 | arrow-left → chevron-left; только один runtime literal. Test-only ожидание завершения существующей автопрокрутки TMA | unit17, navigation16, TMA repeat10+5; общий прогон ниже | [SUCCESS38581812416](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38581812416) | Реальные AFTER, ожидается owner acceptance | Большой scope #873 остаётся открытым |
| #969 / [#978](https://github.com/MikeMoore1337/your-fitness-coach/pull/978) | c5fc1c2594df3ffda4f561706a366243d59a97aa | Явный возврат, dirty/date/edit guards, честный local draft, устойчивое восстановление focus/TMA Back; desktop FAB не закрывает открытую форму | unit4; stress40 (20 web 320 + 20 mocked TMA 390, без retries); integration76+desktop4; общий прогон ниже | [SUCCESS38627047470](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38627047470) | Реальные AFTER, ожидается owner acceptance | Physical devices; отдельный release, Issue OPEN |
| #968 / [#972](https://github.com/MikeMoore1337/your-fitness-coach/pull/972) | ec2d95021d9152d60331f7d41ef36beb79d87e20 | Существующий TimeInput сохранён; 9 scoped CSS lines выравнивают 46px outer / 44px native input | unit28; browser24; DOM60; общий прогон ниже | [SUCCESS38562435409](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38562435409) | Реальные AFTER, ожидается owner acceptance | Native OS picker/physical keyboard; Issue OPEN до release |
| [#971](https://github.com/MikeMoore1337/your-fitness-coach/pull/971) | 16bbe01d190a679f34660722b26b736c72c1d4c0 (исторический head) | Закрыт superseded после сверки; уникальных актуальных требований для переноса нет | [Поясняющий комментарий](https://github.com/MikeMoore1337/your-fitness-coach/pull/971#issuecomment-6167977576) | Исторический CI не используется как current proof | Не требуется | Продуктовые Issues не закрывались |

## Реальные AFTER одним комплектом

| Область | Полный комплект | Покрытие |
|---|---|---|
| Progress | [16 PNG](progress/README.md) | Chromium/WebKit, Dark/Light, 320/360/393/430×844; оба chevron в одном кадре |
| Quick Measurement и Wellbeing | [192 PNG + DOM](forms/README.md) | Web 320/360/390/393/430, mocked TMA 390; обе темы и движка; unchanged, dirty, confirmation, shrunk viewport |
| Quick Add Calories/Time | [60 PNG + DOM](quick-add/README.md), [таблица границ/высот](QUICK_ADD_GEOMETRY.md) | 20 комбинаций × empty/filled/keyboard-safe-area-long-label; 320/360/390/393/430 |
| Desktop | [20 PNG](desktop/README.md) | 1280×900, оба браузера и темы; обе формы и confirmations, Quick Add |

[MANIFEST.json](MANIFEST.json) содержит каждый scenario/browser/theme/CSS viewport, PNG pixels, SHA256, размер файла и точный runtime SHA. Изображения скопированы побайтово из browser output, без ретуши, генерации или использования приватных снимков владельца. Все данные — синтетические fixtures. Mobile использует существующие iPhone13 UA/touch profiles с DPR1 для CSS-размеров и file budget; это эмуляция, не физический iPhone.

Baseline #968 измерен отдельно на f99f1954. Переполнение справа уже не воспроизводится: действующий TimeInput решает его без переноса старых width overrides. Высоты и нижние края не совпадали (включая Chromium 46 vs 48 и WebKit 54.625 vs 46); новый тест на baseline: 16 FAIL / 4 PASS. [20 baseline DOM JSON](baseline-quick-add/) сохраняют фактические измерения. На итоговом AFTER все 60 states: calorie/time outer 46px, native 44px, равные ширины и нижние края в двухколоночном режиме, zero horizontal overflow. Длинная подпись и 24px insets введены тестом как synthetic stress; высота viewport 420/430px имитирует клавиатуру.

## Интеграция и проверки

Все source PR включены нормальными merge поверх актуального origin/master. Force push/rebase не использовались. [INTEGRATION.json](INTEGRATION.json) фиксирует base, исходные/итоговые PR heads, first-parent порядок, merge commits, tree и git status.

Независимые merge master: #990 `0b7aefd2`, #979 `b4febcaa`, #972 `c9547d91`, #978 `4e104609` — конфликтов нет. В #972 единственный конфликт FoodPickerDialog разрешён сохранением текущего master; blob этого файла идентичен production base. В совместных merge конфликтов нет.

| Проверка итоговой сборки | Результат |
|---|---|
| git diff --check | PASS |
| typecheck, lint/Russian UI, build | PASS |
| Prettier canonical Git blobs, 18 source/test files | PASS; raw Windows checkout warnings связаны с CRLF |
| Полная Vitest suite | 869 PASS, 0 FAIL |
| Совместный mobile Chromium/WebKit | 76 PASS, 0 FAIL, 0 retry/skip |
| Desktop Chromium/WebKit 1280×900 | 4 PASS, 0 FAIL, 0 retry/skip; FAB hidden/open и restored/exit проверены |
| Native GitHub daily CI integration runtime `cc2d8d13` | [SUCCESS](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38628832702) |
| Snapshot/golden изменения | NONE |
| API/DB/migrations/shared UI/утверждённые #869/#871/CI source | Без изменений относительно f99f1954 |

[TEST_RESULTS.json](TEST_RESULTS.json) содержит фактические local counters/start times/durations без приватных payloads. Полная совместная проверка выполнена на integration, а не выведена из независимых PR tests.

Проверены create/edit/cancel/delete с подтверждением и сохранность других записей, local draft/re-entry/edit context, null/blank/custom-field order, смена даты, повторные submit/in-flight guard, dirty cancel/confirm, focus restoration, TMA Back/confirmation Back, длинная форма и reachability при shrunk viewport. Новая нижняя панель не создавалась. Measurement draft остаётся account-scoped на устройстве; если storage не принимает запись, confirmation честно предупреждает о потере. Wellbeing local draft не обещается: подтверждённый выход удаляет несохранённое, сохранённая история остаётся.

Первый CI `979/38562034762` падал на существующей scroll/click race weekly-review TMA smoke. Trace и воспроизведение 2/3 FAIL сохранены; исправлено ожидание фактического focus/scroll target перед обычным кликом. Assertions/animations сохранены; retries/force/sleeps не добавлены. Новый exact-head CI зелёный. Первый integration `1d71d1a5` выявил на visual QA перекрытие desktopReturn floatingFAB; before-hit-test FAIL сохранён в локальных доказательствах, исправлено 5 CSS lines по существующему open-state; все финальные AFTER пересняты на `cc2d8d13`.

## Воспроизведение

Из frontend выполнить `npm ci --ignore-scripts`, `npm run typecheck`, `npm run lint`, `npm run test`, `npm run build`. Preview: `node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4260 --strictPort`.

Для screenshot run задать PW_BASE_URL=http://127.0.0.1:4260, PLAYWRIGHT_OUTPUT_DIR, YFC_JSON_REPORT и YFC_QUICK_EXIT_EVIDENCE_DIR в ignored .artifacts. [mobile.config.ts](mobile.config.ts) переиспользует существующие mobile profiles, [desktop.config.ts](desktop.config.ts)/[desktop.spec.ts](desktop.spec.ts) проверяют те же потоки на desktop. Команда: `node node_modules/@playwright/test/cli.js test approved-mobile-ui.spec.ts quick-form-exit.spec.ts nutrition-diary.spec.ts daily-wellbeing.spec.ts progress-experience.spec.ts tma-smoke.spec.ts --config=../docs/ux/final-issues-acceptance/legacy-closeout-20261014/mobile.config.ts --workers=2 -g "approved B navigation and quick add|approved B quick add fits short TMA|quick exits|quick measurement protects|Quick Add geometry|nutrition diary is responsive, keyboard-safe|dark nutrition uses|measurements keep priority|quick measurement can return|daily wellbeing covers|weekly review focus exposes"`. Desktop: тот же CLI с `--config=../docs/ux/final-issues-acceptance/legacy-closeout-20261014/desktop.config.ts --workers=2`.

## Remaining и границы

- Единственный следующий owner gate — final visual acceptance всего этого пакета; затем отдельное разрешение на merge/deploy. Все 4 рабочих PR остаются Draft. #968/#969/#873 OPEN, не Done.
- #873 выполнен только в части пары chevron. Перестройка Progress и прочий scope остаются в существующей Issue; отмеченное clipping focus outline link у границы scroll rail относится к прежнему поведению, chevron controls/focus не ухудшены.
- Physical iPhone/Safari, native Telegram Android/iOS, VoiceOver, настоящий OS time picker и экранная клавиатура — NOT_VERIFIED. Автоматические resize/safe-area/mock TMA не заменяют их.
- Guard покрывает явные действия формы и TMA Back; закрытие вкладки/полная перезагрузка браузера не получают нового global blocker. Measurement draft сохраняется локально по существующему контракту; несохранённый Wellbeing после unload не обещан к восстановлению.
- Product V11/V12/V13/V14 не запускались/не менялись. Утверждённые макеты #869/#871 не изменены и не реализованы. Новых зависимостей, API/DB/migration/env changes нет.
- Исторические failures и NOT_REPRODUCED не переклассифицированы в PASS. #971 закрыт только как устаревший документ; его ветка/commits сохранены.
