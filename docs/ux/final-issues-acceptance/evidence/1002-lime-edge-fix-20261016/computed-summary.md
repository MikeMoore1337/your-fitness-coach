# Issue #1002 — computed-style AFTER summary

Источник измерений: `getComputedStyle` в synthetic Playwright fixtures на commit
`1c05a6bbbe799ab5f0057e9478e968493242ecc4`.
Для Report и Cardio контракт повторён в Light/Dark на ширинах `320/360/390/393/430/1440 px`
в Chromium и WebKit. Для Active Workout контракт повторён в Light/Dark на `320/360/393/430 px`.

| Case | Selector | AFTER computed result | Regression assertion |
| --- | --- | --- | --- |
| A-01 | `.progress-report-overview` | `border-left-width: 0px`; `border-left-style: none` | запрещённая толстая левая грань отсутствует |
| A-02 | `.progress-report-factual-summary` | `border-left: 1px solid`; left color equals top color | обычный frame сохранён |
| A-03 | `.progress-report-program` | `border-left-width: 0px`; `border-left-style: none` | запрещённая толстая левая грань отсутствует |
| A-04 | `.progress-report-exercises article` | 2 cards; `top/right/bottom/left: 1px`; left color equals top color | обе карточки сохранили равномерный frame |
| A-05 | `.cardio-log` | `top/right/bottom/left: 1px solid`; all colors equal | обычный frame и focus/validation guard сохранены |
| A-06 | `.active-workout-set.is-current` | `box-shadow: none`; `border-width: 1px`; border color `rgb(178, 245, 32)` | current frame, RIR and timer preserved |

Дополнительные факты:

- Report computed helper требует ровно две exercise cards, поэтому A-04 учитывает 2 видимых
  runtime-инстанса, а не только имя селектора.
- Cardio test дополнительно фокусирует `Длительность, мин`, проверяет disabled `Сохранить кардио`
  при невалидном состоянии и отсутствие горизонтального overflow.
- Active Workout cross-browser checks оставляют `aria-pressed=true` для RIR и видимый timer;
  mock-TMA Chromium critical checks покрывают safe-area/lifecycle и RIR/finish controls.
- AI Coach checked separately as hidden in Web/TMA/PWA surfaces; его rail не входил в этот diff.

Не следует трактовать эти browser/mock-TMA результаты как physical iPhone, native Telegram,
VoiceOver, production smoke или owner visual acceptance.
