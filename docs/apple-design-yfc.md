# Apple Design reference для YFC

`$apple-design` используется в YFC как условный reference layer для Apple-like interaction physics,
Liquid Glass materials и native-feel web/TMA поведения. Он не заменяет YFC design system и не задаёт
бренд самостоятельно.

## Цель

Актуализировать существующий YFC дизайн так, чтобы:

- интерфейс быстрее реагировал на действие;
- motion был interruptible и физически связным;
- drag/swipe/sheet взаимодействия учитывали velocity/momentum;
- Liquid Glass использовался как функциональная material hierarchy, а не как декоративный слой везде;
- typography/spacing/depth лучше поддерживали hierarchy;
- mobile web/TMA ощущались ближе к native product;
- reduced motion/transparency/contrast имели осознанные fallback;
- сохранялись sport-tech, cinematic character и lime/black/white brand core.

## Как применять к текущему дизайну

### 1. Read-only inventory и audit

Сначала проверить фактический render Landing и приложения, не меняя production UI.

Покрыть representative surfaces:

- Landing + public auth/demo entry;
- Home/Dashboard;
- Workout active flow;
- Nutrition diary/add flows;
- Progress;
- AI Coach;
- Programs;
- основные modal/sheet/dropdown/popover/navigation states;
- light/dark;
- mobile web/TMA и desktop.

Для каждого surface оценить:

1. response latency и pressed feedback;
2. spatial origin/enter-exit consistency;
3. interruptibility;
4. gesture tracking/velocity/momentum;
5. sheet/drawer snap behavior;
6. material hierarchy/translucency/depth;
7. glass-on-glass layering и legibility;
8. typography: hierarchy, tracking, leading, numeric readability;
9. touch target/direct manipulation;
10. reduced motion/transparency/contrast;
11. performance/jank/layout shift;
12. соответствие YFC brand, а не сходство с iOS ради сходства.

### 2. Findings не равны обязательному Apple-ification

Finding создаётся только если Apple-like principle улучшает реальный UX/quality.

Не менять элемент только потому, что Apple делает иначе. Не являются дефектом сами по себе:

- текущая sport-tech geometry;
- lime accents/glow;
- cinematic visual layer;
- нестандартная composition;
- YFC-specific navigation;
- отсутствие spring там, где обычная CSS transition проще и лучше.

### 3. Сначала representative prototype

До массовой переработки выбрать несколько наиболее показательных flows:

- активная тренировка;
- nutrition add flow;
- Progress;
- один representative modal/sheet;
- Landing hero + основные controls.

Для них подготовить вариант с применёнными Apple principles и сравнить с текущим production design.

Если visual direction меняется заметно, использовать `$ui-prototyper` и owner checkpoint.

### 4. После owner approval - системная remediation

Не фиксить экран за экраном локальными CSS patches.

В первую очередь обновлять shared contracts:

- design tokens;
- surface/material tokens;
- button/control states;
- shared sheet/modal/popover patterns;
- motion/spring helpers;
- typography scale/tracking/leading;
- reduced-motion/transparency/contrast utilities;
- shared mobile interaction primitives.

Затем мигрировать consumer screens в пределах утверждённого scope.

### 5. Production verification

Для изменённых surfaces проверить:

- 360/390 mobile;
- representative desktop;
- light/dark;
- Web/TMA parity;
- keyboard/focus/touch;
- reduced motion;
- reduced transparency/contrast где platform поддерживает signal;
- repeated-use feel;
- layout stability и browser performance.

## Skill collaboration

Обычный маршрут для такой работы:

```text
product-designer
      ↓
apple-design (conditional reference)
      ↓
motion-design-engineer (если motion существенный)
      ↓
mobile-engineer (если есть runtime/mobile trigger)
      ↓
frontend-engineer
      ↓
ui-audit
```

Для Landing дополнительно используется `$landing-art-director`.

## Что не делать

- не копировать iOS chrome/controls/geometry механически;
- не покрывать каждый nested surface стеклом;
- не добавлять spring library только ради одной transition;
- не делать весь motion bounce;
- не снижать контраст ради translucency;
- не скрывать product/data hierarchy эффектами;
- не заменять YFC design authority внешним skill;
- не катить массовый redesign без owner-approved visual checkpoint.
