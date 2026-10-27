# Design V2.1 — контракт Landing и `/login`

Изменения Task 151 (локальные шрифты, нейтральные темы, новая спортивная сцена) описаны в
[Протоколе силы](strength-protocol.md) и заменяют соответствующие визуальные положения ниже.

## Визуальная целостность

Landing и `/login` используют один canonical logo, semantic Light/Dark токены V2, controls с
радиусом `12px` и lime focus/primary action. Обе поверхности сохраняют production-стек
`Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` без
внешней font dependency и блокирующей загрузки. На Landing иерархия строится масштабом,
насыщенностью и ритмом исходной гарнитуры. Целостность не означает повтор композиции Landing
внутри auth flow.

Двухплоскостная композиция `/login` не импортирует colors из Direction A. Обе
плоскости сопоставлены production-контракту Design V2: Light canvas/surface/lime
`#F4F5F2 / #FFFFFF / #9EE02B`, Dark `#101310 / #161916 / #A8E83A`. Текст, border и semantic
error states берут theme tokens из `frontend/src/styles/design-system.css`.

## Landing — выбранный Premium Strength System

### Зафиксированное направление

Первый owner checkpoint task `73A` утвердил изображение candidate A и product-forward направление
candidate C. После сравнения production-рендера с обязательными moodboard references владелец явно
разрешил отойти от ранних композиционных ограничений; обязательными остались фирменные цвета YFC,
production-типографика, фактическая честность и выбранный athlete visual. Финальная
production-арт-дирекция фиксирует:

- информационная архитектура и product-forward storytelling — из candidate C `Strength System`,
  но hero, типографический контраст и ритм страницы переработаны напрямую по premium sport-tech
  принципам reference;
- athlete visual — точная owner-approved версия candidate A: классическая становая тяга и матовая
  чёрная майка;
- обязательные premium-strength references задают cinematic density, асимметрию, lime-траекторию
  и смену масштаба, но их identity, гарнитуры, тексты, cardio-сюжет и вымышленный product UI не
  копируются.

Сюжет Landing — не результат атлета и не testimonial. Спортсмен задаёт силовой контекст, а
доказательством продукта остаются только реальные YFC screens с подготовленными данными.

### Информационная архитектура

1. Header: полный canonical lockup, `Продукт / Демо / Вопросы`, theme control и `Войти`.
2. Cinematic hero: один H1 `Знайте, что делать сегодня.`, primary CTA `Открыть приложение`,
   neutral Demo action и фактический Web/Telegram context.
3. Единая сцена: transparent athlete cutout, lime-траектория и актуальный ordinary Mobile Web proof
   в тонком notchless display; label отделяет подготовленные данные от реальных пользователей.
4. Product chapter: крупная связка ordinary `/app` Today + workout proof, три текстовых направления
   `Сегодня / Питание / Прогресс` и отдельный self-training CTA без card wall.
5. Secondary trainer chapter: один factual value proposition и актуальный ordinary `/coach` proof.
6. Workflow и изолированный Demo: три шага продукта и три demo-сценария с отдельными данными.
7. Web/Telegram continuity, knowledge, FAQ и privacy собраны в одну assurance-главу.
8. Контрастный final CTA и footer сохраняют фактические public/support routes и полный lockup.

Запрещены fake metrics, testimonials, prices, trial, AI, readiness/recovery/HRV, wearables,
medical outcome и будущие capabilities. Текст остаётся crawlable HTML; на странице один H1,
headings сохраняют semantic order.

### Desktop-композиция

- На `1440/1280/1024` content ограничен `1320px`; hero остаётся открытой асимметричной плоскостью:
  copy, athlete и product display существуют в одной глубине без отдельной photo-card.
- Athlete, один крупный Mobile Web proof и лёгкий lime energy flow образуют одну сцену. Поток
  состоит из `7–14` независимых SVG-волокон без залитой поверхности: две ведущие траектории,
  более тонкие расходящиеся нити, мягкая маска на концах и ограниченное рассеянное свечение. Он
  проходит за CTA, athlete и display и снова выходит справа от устройства; proof не перекрывает
  лицо, обе кисти, гриф или контакт с оборудованием.
- Product narrative строится вокруг одного крупного current-app proof, трёх последовательных
  capability rows и отдельной самостоятельной value proposition.
- Supporting chapters меняют масштаб и пропорции; trainer остаётся вторичным, а однотипные card
  grids не становятся способом storytelling.
- На `768` copy предшествует сцене, header menu остаётся доступным для keyboard/touch.
- Hero, Today/workout и trainer используют соответствующие теме captures актуального интерфейса.
  Nutrition и Progress объясняются текстом без загрузки отдельных неиспользуемых proofs.

### Mobile-композиция

- На `430/390/360`: promise → primary и Demo actions → athlete + current-product proof. На первом
  viewport видны обе CTA, лицо и верх display; кисти, гриф и блины продолжаются сразу ниже fold без
  смены главы. Горизонтального overflow нет.
- На mobile остаются восемь наиболее выразительных волокон; их толщина и glow уменьшаются, а поток
  не используется как border/divider и не конкурирует с текстом.
- Athlete не обрезается внутри scene: transparent cutout сохраняет лицо, обе кисти, гриф и блины;
  мобильная сцена меняет positioning, а не raster crop.
- Hero proof остаётся реальным vertical Mobile Web state, получает отдельную mobile perspective и не
  перекрывает copy.
- Mobile menu закрывается после route selection, `Escape` или outside action, возвращает focus и
  сохраняет controls `>=44px`.
- Light/Dark используют один одобренный transparent athlete asset с theme-aware CSS integration и
  соответствующие теме product renders.

### Motion

- CSS-first motion ограничен hero: волокна `EnergyFlow` раскрываются за `1200ms` с независимыми
  задержками `80–550ms`, product display появляется за `700ms` после `90ms`.
- H1, CTA, athlete и navigation доступны сразу; animation не управляет layout и не блокирует
  interaction. Ниже fold нет scroll-triggered entrance state.
- `prefers-reduced-motion: reduce` отменяет trajectory/device movement и сразу показывает финальную
  композицию, сохраняя короткий feedback controls.
- Нет scroll hijacking, loop, autoplay video, parallax или runtime animation dependency.

### Athlete asset и provenance

- Тип: оригинальный `generated asset`, созданный встроенным OpenAI image generation tool
  `2026-08-25` специально для YFC; модель/version metadata инструмент не раскрывает.
- Owner предоставил выбранный generated frame и запросил единственную semantic правку: окрасить
  светлую майку в матовый чёрный. Edit prompt требовал сохранить лицо, телосложение, позу, хват,
  штангу, блины, освещение, фон и crop.
- Moodboard references не передавались генератору как image bytes и не используются как production
  assets. Внешних hotlinks, фотографий, лицензий, логотипов или likeness реального публичного лица нет.
- Статус права использования: asset создан по запросу владельца проекта через встроенный generator,
  утверждён владельцем для YFC и не зависит от сторонней stock-лицензии.
- Source PNG хранится только в task artifacts и не загружается клиентом. SHA-256 точной утверждённой
  ревизии: `A0E8C8D11B1D0E657DEB92FC1EF53BA835BD83E1B443B3425640DC2BC1D42123`.
- Anatomy/equipment review: взрослый светлокожий мужчина европейской внешности, правдоподобное
  атлетичное телосложение, conventional stance, обе кисти на грифе, симметричные блины и замки,
  контролируемая траектория без maximum-effort caricature; на одежде и оборудовании нет брендов.

Production derivatives с прозрачным фоном находятся в `frontend/public/assets/marketing/`:

| Width |  Bytes | WebP SHA-256                                                       |
| ----: | -----: | ------------------------------------------------------------------ |
|   640 | 30 856 | `E1FAAE11CE0F0F311E30AFCC6E6D6B83DFE6030C0B8B2B48736C540DBC8CD76C` |
|   960 | 51 084 | `F00BC8C7A388491A40914212551B3F4BF82C020792DD84F680FF2DF039730CD0` |
|  1280 | 73 286 | `D53D8C7AD0BCB6D8C7CBA9BB81F6D0F809B7938BF46239F39E0910565D2231B6` |

`<picture>` выбирает WebP `640/960/1280` по `sizes`, задаёт intrinsic `1280×1171` и
`fetchPriority="high"` только для hero athlete. Hero Mobile Web proof активной тренировки также
eager, потому что он входит в первый экран. В блоке «Продукт в действии» desktop `1440×900` и
mobile `390×844` показывают один актуальный экран «Сегодня» с текущей иконографикой; эти Today- и
trainer-proofs ниже fold загружаются lazy. Для каждого PNG заданы width/height и текстовый failure
fallback.

#### Обязательный контракт product screenshots

- Источник — всегда текущий authenticated UI на обычном route приложения (`/app`, `/coach` или
  другой фактический product route), отрендеренный текущими production-компонентами.
- Данные — только локальные детерминированные fixtures тестового authenticated-пользователя. Нельзя
  использовать реальные имена, измерения, дневники, комментарии, токены или другие персональные
  production-данные.
- Demo-кабинет и `/demo` не являются источником marketing product proof. Их screenshots допустимы
  только внутри явно подписанного Demo narrative и не подменяют доказательство текущего продукта.
- После изменения icon set, navigation, typography или layout все затронутые Light/Dark и
  desktop/mobile derivatives переснимаются из текущей реализации. Старый raster не сохраняется как
  fallback.
- Воспроизводимость подтверждает manifest с `route`, `theme`, `viewport`, `fixture`, размером файла
  и SHA-256. Проверка должна подтвердить отсутствие demo chrome, production PII и расхождения между
  заявленным и фактическим UI.
- Landing разделяет сценарии: hero может показывать актуальную активную тренировку, а «Продукт в
  действии» — актуальный Today. Оба proof обязаны следовать одному контракту источника и данных.

Исторический набор task `73A` снят `26.08.2026` из ordinary authenticated routes с локальными
fixtures; `/demo` и production-данные не использовались. Task 151 переснимает этот набор и
публикует lossless WebP; текущий manifest находится в [Протоколе силы](strength-protocol.md).

| Файл                                | Route / fixture                                | Тема и viewport   |  Bytes | SHA-256                                                            |
| ----------------------------------- | ---------------------------------------------- | ----------------- | -----: | ------------------------------------------------------------------ |
| `landing-today-desktop-light.png`   | `/app`; `mockDashboard(planned)`               | Light, `1440×900` | 71 421 | `AA37ECAFDEA2853A04967AB9175CE655B3C97F3D75207B35F6876A86DAC213E5` |
| `landing-today-desktop-dark.png`    | `/app`; `mockDashboard(planned)`               | Dark, `1440×900`  | 70 950 | `F574E31702F228D066D9914E64B052E222001A2ED170CF4EB78E1DAC8BB13DBC` |
| `landing-today-mobile-light.png`    | `/app`; `mockDashboard(planned)`               | Light, `390×844`  | 36 786 | `34CE7B5082DD42F3EBB7327050882751DC34CE8E2D71F15B4BE164D2CF12D7CA` |
| `landing-today-mobile-dark.png`     | `/app`; `mockDashboard(planned)`               | Dark, `390×844`   | 36 781 | `48DB3C944E5C566FC284BBBB5C41E70C6054402C6E511B771087D4F7A4E9FAB2` |
| `landing-workout-mobile-light.png`  | `/app → Continue workout`; `mockActiveWorkout` | Light, `390×844`  | 32 952 | `F054AA815382F5D55CE522EFA97A95E05F1F07DF6EA3284BEAD694B45EFD1B75` |
| `landing-workout-mobile-dark.png`   | `/app → Continue workout`; `mockActiveWorkout` | Dark, `390×844`   | 32 689 | `77DFD809E599A31FD5FFFE694724D89ACA02BD005E959026AE9EB2769841B231` |
| `landing-trainer-desktop-light.png` | `/coach`; `mockCoachWorkspace`                 | Light, `1280×972` | 93 333 | `685F00981F7253FF1F9E345CF86C736D69B7F0769DB51F41A3317B89358615AD` |
| `landing-trainer-desktop-dark.png`  | `/coach`; `mockCoachWorkspace`                 | Dark, `1280×972`  | 93 346 | `9D58D878B859A61D1E67C587FB11E0849A267607FE9C4D4835A2BE3BCCB79CFE` |

Capture hooks включаются только явным `YFC_CAPTURE_LANDING_PRODUCT_PROOFS=1` в соответствующих
Playwright specs. Обычный test run не перезаписывает production assets.

### Остальные production-правила Landing

- Header action `Войти` использует lime fill с `on-lime` текстом в Light и Dark; theme/menu controls
  остаются нейтральными.
- Outlined Demo открывает production demo-cabinet с явными `cabinet`, `scenario` и `section`.
- Image failure не скрывает H1 и CTA; в media geometry заранее зарезервировано место и есть текстовый
  fallback. После успешной загрузки fallback скрывается, поэтому сообщение о недоступности не может
  оставаться под узким product proof.
- Platform boundary замкнута со всех сторон; footer privacy ведёт в публичный раздел до авторизации.
- Final CTA использует одну контрастную плоскость и одну lime-траекторию, без glow и набора
  декоративных containers.

## `/login` — выбранные A surfaces и V2 type

### Desktop

- Split `1.04fr/.96fr`: слева continuation plane, справа auth plane.
- Desktop-сцена использует тот же container, что и landing: `min(1180px, calc(100% - 48px))`.
  На широких viewport, включая `2K`, полноэкранные фоновые плоскости сохраняются, но контент не
  растягивается и не прижимается к внешним краям; граница фоновых плоскостей продолжает совпадать
  с границей tracks центрированной сцены.
- Левая плоскость использует более сильный V2 dark/surface contrast из approved board; правая остаётся
  спокойной theme-native plane. В Dark их semantic relationship не инвертируется механически.
- Continuation group центрирована по вертикали. `Вернитесь к своему плану.` — `35px`, одна строка
  и не менее `22px` inline clearance. Supporting copy не обещает автоматическое слияние accounts.
- Auth stack центрирован по обеим осям. Eyebrow/title/context/provider выровнены по provider track
  `300px`; полные provider labels остаются на одной строке, а error/helper могут занимать до
  `360px` для читаемого recovery.
- Четыре provider actions остаются вертикальным stack. Лишние header/home/theme controls для
  V2.1 исключены.
- В continuation plane логотип выбирается по локальной тёмной поверхности (`dark` asset), а не по
  глобальной Light/Dark теме страницы.

### Tablet/mobile

- На `<1024` split становится одной document column. Mobile title — `Войти и продолжить`;
  continuation context остаётся фактическим и не занимает отдельный viewport.
- Mobile header показывает полный lockup `YOUR FITNESS COACH` без дублирующей кнопки `Войти`:
  пользователь уже находится на экране входа.
- Provider actions занимают всю ширину, их высота `>=48px`, а внешний gutter — не менее `16px`.
- Loading и error остаются in-flow. Light loading и Dark error в approved board — только representative
  states: оба состояния обязаны работать в обеих темах.
- При открытой keyboard active control/error/action остаются видимыми, content может scroll.

### Providers и OAuth return

- Providers: Telegram, Google, Яндекс, VK ID — ровно по runtime configuration.
- Каждый внешний provider action показывает узнаваемый фирменный знак в официальной палитре;
  знак остаётся видимым на desktop/mobile и в Light/Dark. Нельзя заменять его общей пиктограммой,
  первой буквой, emoji или скрывать ради более нейтрального списка.
- Provider color ограничен компактным icon carrier; сама action сохраняет theme-native YFC surface,
  читаемый текст и lime direction marker. Иконка декоративна, а доступное имя задаёт полный label.
- Нажатие provider блокирует duplicate submit и сохраняет allowlisted return context.
- Cancellation возвращает focus на исходный provider.
- Provider unavailable, invalid state и conflict объясняют безопасное recovery без silent identity merge.
- OAuth success ведёт по validated internal path; external/open redirect запрещён.
- Valid TMA launch пропускает browser provider stack и входит в platform auth loading/error.

## Финальные evidence и ограничения

### Motion `/login`

- Initial composition использует один спокойный `--motion-spatial` entrance без задержки формы,
  focus или provider actions.
- Provider click немедленно показывает busy label, блокирует duplicate submit и не задерживает
  фактический redirect. OAuth-return error и recovery доступны сразу.
- Email login/register/recover меняют только локальную mode panel через `--motion-state`; введённые
  данные, validation и focus сохраняют semantic order.
- `prefers-reduced-motion: reduce`, hidden document и inactive TMA сразу показывают final state.
- Landing hero motion остаётся owner-approved bounded исключением task `73A`; task `74A`
  унифицирует control feedback, но не переигрывает его композицию или storytelling.

- Frozen renders покрывают Landing desktop/mobile Light/Dark и `/login` desktop/mobile Light/Dark с
  loading/error representation.
- Static boards подтверждают только composition, typography и hierarchy. Keyboard, focus order, OAuth
  return, provider configuration, TMA auth и responsive overflow проверяются runtime-тестами.
