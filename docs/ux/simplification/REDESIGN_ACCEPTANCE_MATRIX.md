# Acceptance matrix локального IA redesign

Эта матрица описывает локальную проверку композиции и навигации. Она не является PASS для
`124B`, реального Telegram, physical device или production.

| Риск                    | Acceptance                                                                                                                                                   | Evidence                                    |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- |
| Main nav overload       | authenticated/demo shell показывает `Сегодня / План / Питание / Прогресс`; account entry ведёт в Profile; AI/catalog/reports/scanner не становятся top-level | DOM navigation assertions + screenshots     |
| Today focus             | выше fold видны date, current/next workout, одна primary action, week context и 2–3 факта; AI не занимает отдельную большую card                             | mobile 360/390 screenshots + bounding boxes |
| Global quick add        | `+` имеет доступный label, открывает один sheet, sheet не скрывает primary content и закрывается Escape/BackButton; actions ведут в existing flows           | component/e2e interaction                   |
| Plan separation         | default Plan не рендерит full builder/library/import; `Управление программой` открывает существующий management surface; schedule доступно в Plan            | direct route tests + screenshot             |
| Progress responsibility | schedule отсутствует в default Progress, history/analytics/measurements остаются; report action находится в secondary reports area                           | component assertions + desktop screenshot   |
| Nutrition focus         | diary/add food first; target calculator is secondary disclosure; no repeated AI card                                                                         | unit/render + 390 screenshot                |
| Profile focus           | compact settings rows precede forms; existing personal/trainer/notification/security/AI actions remain reachable; no fake integration action                 | direct hash navigation + screenshot         |
| Demo safety             | `/demo` public, `/app` remains AuthGate-protected; demo states are deterministic/read-only and reset remains available                                       | route smoke + reset test                    |
| Responsive/TMA          | no horizontal overflow at 360/390/430; target >=44px; bottom nav/safe area/focus/reduced motion remain valid                                                 | Playwright geometry/accessibility checks    |
| Honest evidence         | screenshots identify local Demo/mock state and are not described as real-user/device/production proof                                                        | artifact manifest + final report            |

## Local usability proxy

До `124B` не объявляется PASS. В локальном smoke проверяются representative paths: first open →
next action, open/manage/create program, technique entry, start/log workout, cardio, food search,
barcode/manual entry point, progress, profile/security, navigation explanation, water/history,
wellbeing/history and notification settings. Базовая цель — 2–3 meaningful actions без лишнего
backtracking; любой реальный BLOCKER/HIGH регистрируется отдельно и не маскируется demo.
