# SERP и competitor matrix: RU/CIS

Дата: 2026-09-16
Task: 241A
Принцип: фиксируются реальные URL, структура intent и utility gap; тексты конкурентов не
копируются и не используются как source content.

## Методика и ограничения

- Google: ручные UI snapshots для русскоязычной выдачи с `hl=ru&gl=ru`; контрольные запросы
  выполнялись 2026-09-14 и 2026-09-16.
- Yandex: manual snapshot по `калькулятор 1пм` 2026-09-16 (`lr=2`, видимый регион Санкт-Петербург);
  после серии запросов включился SmartCaptcha. Дальнейшие Yandex results нельзя выдавать за
  полный sample. Данные ниже, помеченные `Yandex directional`, используют доступный snapshot и
  независимые public-page checks, а не frequency.
- Page checks: публичные HTTP pages 2026-09-14–16; проверялись title/H1/H2, наличие form/input,
  obvious JSON-LD и CTA pattern. Отсутствие найденной schema в HTML-check не является доказательством,
  что schema нет после client-side render.
- Никаких volume/traffic numbers не собиралось. SERP composition — qualitative evidence.

## Query-level SERP observations

| Cluster/query | Google observation | Yandex observation | Dominant intent / implication |
| --- | --- | --- | --- |
| `калькулятор 1пм` | Calculator pages occupy organic set: last-man, FRS24, Body1, AnatomyStudy, GeneticLab, Start-fit, Zozhnik, Inspire2; related queries include bench/squat/deadlift | Accessible page showed Start-fit, Calc-fit, FRS24, Sport-iv, GeneticLab, CalcNeo, Last-man, OnlyPump, жимлежа.рф, Iron-mind; visible `19 млн результатов` is not volume | Tool/BOFU; a useful result beats another formula article |
| `калькулятор объема тренировки` | Start-fit, AnatomyStudy, TrainerRoad-related calculator/article, Sport-iv and other fitness calculators | AnatomyStudy, Start-fit, OnlyPump, Calcal, Sport-iv | Tool + planning; define planned vs completed volume |
| `программа тренировок 3 раза в неделю` | Fitbar, Flex Sport, Maxler, VK/Dzen, RT-sport, Reddit, JV/Pinterest mix | Repeated anti-bot after initial attempts; no reliable full page snapshot | Program/template; one canonical 3-day program with variants |
| `full body 3 раза в неделю` | InstructorPRO, Maxler, Dzen, Championat, Drive-fit, Reddit and video block; related queries split by gender/home/goal | Captcha reached before a stable sample | Program + video; page needs usable schedule and save path |
| `crm для фитнес тренера` | Fitness1C, Rubitime, YCLIENTS, Bitrix24, Fitbase, KP/SportPriority/MoyKlass | Full repeatable snapshot unavailable after captcha | Commercial investigation; YFC must state narrower trainer scope |
| `жим лежа техника` | Fitness3000, Sport-Express, PlanetaSport, Nef, Power35, Domsporta, DDX; media/step-by-step content | Full repeatable snapshot unavailable after captcha | Informational; canonical exercise page + media and safety |
| `калькулятор кбжу` | Alena RightFood, Smart Eat, XFIT, PowerTeam, WillFood and nutrition/medical domains | Full repeatable snapshot unavailable after captcha | Tool, but high trust/YMYL; strengthen `/nutrition` first |
| `калькулятор пульсовых зон` | Lifehacker, GET.run, GeneticLab, PaceRun, Velodaily, Inspire2, Velosophy | Full repeatable snapshot unavailable after captcha | Tool with health/claims risk; defer |
| `дневник тренировок приложение` | App Store Forma, GymUp, Gymate, roundups from Lifehacker/Brite/RBC and app content | Full repeatable snapshot unavailable after captcha | Commercial app comparison; strengthen `/training` |

## Competitor matrix

### A — 1ПМ / working-weight calculators

| Engine | Competitor | Observed title/H1 | Type / interaction | CTA, app, schema | Strength | YFC utility gap |
| --- | --- | --- | --- | --- | --- | --- |
| Google | [Body1](https://body1.ru/kalkulyator-odnopovtornogo-maksimuma-1pm/) | «Калькулятор одноповторного максимума (1ПМ)» | form; 4 inputs | CTA to Telegram; `WebApplication`, `Offer`, breadcrumbs | Formula plus percentage working weights | Explain uncertainty, exercise context and save-to-program path |
| Google/Yandex | [GeneticLab](https://geneticlab.ru/calc/gym/) | «Калькулятор для расчёта жима лёжа» | form; many inputs | product/site CTA; obvious calculator schema | Focused bench result and explanation | Neutral multi-exercise tool, transparent limits, YFC action |
| Google/Yandex | [Start-fit](https://start-fit.ru/calc/kalkulyator-1pm-odnopovtornogo-maksimuma/) | «Калькулятор 1ПМ» | interactive calculator | calculator/article markup observed | Utility plus safe-planning framing | Connect result to actual program/workout |
| Google | [AnatomyStudy](https://anatomystudy.ru/povtornyj-maksimum) | «Одноповторный максимум» | calculator/explanation | CTA to related content | Explains RM and variants | Product-led save and exercise catalog links |
| Yandex | [Calc-fit](https://calc-fit.com/1pm) | «Калькулятор одноповторного максимума» | interactive; multiple exercises | product not the main CTA | Direct result for bench/deadlift/squat | Better limitations, result persistence and program bridge |
| Google/Yandex | [Zozhnik](https://zozhnik.ru/calc_1pm/) | «Калькулятор 1ПМ и рабочий вес» | simple calculator | formula explanation | Clear adjacent intent | Modern accessible result and product action |

### B — training volume

| Engine | Competitor | Observed title/H1 | Type / interaction | CTA, app, schema | Strength | YFC utility gap |
| --- | --- | --- | --- | --- | --- | --- |
| Google/Yandex | [AnatomyStudy volume](https://anatomystudy.ru/volume) | «Объём тренировочной нагрузки» | volume dashboard; inputs | CTA to related content | Muscle-group/week interpretation | Define YFC planned vs completed data and link program |
| Google/Yandex | [Start-fit volume](https://start-fit.ru/calc/kalkulyator-obschego-trenirovochnogo-obema-tonnazha/) | tonnage/volume calculator | interactive; many inputs | rich page markup observed | Direct tonnage utility and planning sections | Result tied to saved workout history, not only number |
| Yandex | [OnlyPump volume](https://onlypump.ru/volume) | program assessment / volume calculator | interactive | product/fitness context | Connects volume to program assessment | Explain limits and avoid generic optimal claims |
| Yandex | [Calcal training volume](https://calcal.ru/training-volume-calculator) | training volume calculator | interactive | calculator-first | Fast answer | Better exercise catalog/context and save action |
| Yandex | [Sport-iv volume](https://sport-iv.ru/calc/kalkulyator-trenirovochnogo-obyoma-tonnazha/) | training volume/tonnage calculator | interactive | calculator plus article | Familiar query matching | Use YFC program and progress data |

### C — 3-day/full-body programs

| Engine | Competitor | Observed title/H1 | Type / interaction | CTA, app, schema | Strength | YFC utility gap |
| --- | --- | --- | --- | --- | --- | --- |
| Google | [Fitbar](https://fitbar.ru/articles/podrobnaa-programma-trenirovok-v-zale-dla-muzcin-na-3-raza-v-nedelu-pravila-pitania/) | detailed 3-day gym program | long article/template | form/CTA observed | Complete schedule, sets/reps, nutrition framing | Structured program object and save/inspect flow |
| Google | [Maxler](https://maxler.ru/blog/programma-trenirovok-dlya-zala-3-raza-v-nedelyu/) | «Программа тренировок для зала 3 раза в неделю» | article/template | Article/WebPage schema | Clear beginner 3-day structure | More usable exercise cards and product handoff |
| Google | [InstructorPRO](https://instructorpro.ru/trenirovka-fulbadi/) | «Тренировка фулбади» | educational article | Article/WebPage schema; CTA | Explains full-body concept | A complete schedule with save semantics, not only theory |
| Google | [RT-sport](https://rt-sport.ru/regulyarnost-trenirovok) | regularity and 2–3 day training principles | article | blog/editorial page | Practical frequency guidance | Narrow canonical intent and less generic content |
| Google | [Dzen/Pro Training](https://dzen.ru/a/ZE9Vk0WBmGv0dY-W) | full-body for mass | article/template | platform content | Concrete day-by-day example | Product-owned, editable program and limitations |
| Google | [Reddit discussion](https://www.reddit.com/r/naturalbodybuilding/comments/1iih3pe/experiences_from_doing_full_body_3_times_a_week/?tl=ru) | experiences with full-body 3x | community discussion | UGC | Real objections/questions | Answer objections with sourced, useful program guidance |

### D — trainer / B2B

| Engine | Competitor | Observed title/H1 | Type / interaction | CTA, app, schema | Strength | YFC utility gap |
| --- | --- | --- | --- | --- | --- | --- |
| Google | [Fitness1C](https://www.fitness1c.ru/blog/crm-dlya-trenera/) | «CRM для тренера» | commercial article/landing | form; Article/WebPage/Organization | Explicit feature taxonomy and integrations | Honest narrower promise: programs, progress, invites |
| Google | [Rubitime](https://rubitime.ru/chastnyj-trener) | «Приложение для записи к тренеру» | commercial product | booking/admin UI; form | Booking workflow and automation | Do not imitate booking; show YFC coach-client loop |
| Google | [YCLIENTS](https://www.yclients.com/fitness) | sports-business service | commercial platform | booking/app/analytics CTA | Strong business positioning | Differentiate coach workflow, not club operations |
| Google | [Fitbase](https://fitbase.io/) | fitness clubs/studios growth platform | SaaS landing | lead CTA; Organization data | Broad club product and proof | Focus on individual trainer/client value |
| Google | [Bitrix24 fitness CRM](https://www.bitrix24.ru/solutions/industries/fitness/) | CRM/platform | SaaS landing | lead CTA | Breadth and integrations | YFC should not claim generic CRM breadth |

### E — exercise technique

| Engine | Competitor | Observed title/H1 | Type / interaction | CTA, app, schema | Strength | YFC utility gap |
| --- | --- | --- | --- | --- | --- | --- |
| Google | [Fitness3000](https://fitness3000.ru/blog/zhim-shtangi-lyezha/) | barbell bench press technique | technique article | media/steps; organization data | Detailed setup, breathing, errors | Canonical exercise catalog with product context |
| Google | [NEF](https://nef.fit/blog/zhim-lezha/) | bench press technique and muscles | article | multi-variant explanation; trainer author | Covers incline/decline/close grip and contraindications | Avoid thin variant pages; use verified domain data |
| Google | PlanetaSport / DDX | technique pages | informational/article | media likely important | Broad exercise coverage | YFC can build consistent canonical taxonomy |

### F — KBJU / calorie / protein

| Engine | Competitor | Observed title/H1 | Type / interaction | CTA, app, schema | Strength | YFC utility gap |
| --- | --- | --- | --- | --- | --- | --- |
| Google | [Alena RightFood](https://alena-rightfood.ru/calc) | «Калькулятор норм КБЖУ» | interactive form | 5 inputs; no obvious JSON-LD in check | Direct user flow | YFC must disclose assumptions and connect to diary honestly |
| Google | [Smart Eat](https://smart-eat.ru/calculator) | nutrition calculator | calculator page | WebApplication/HowTo/Offer schema observed | Clear calculator framing | Source/reviewer/limitations and product target history |
| Google | [XFIT](https://xfitnn.ru/calculator_rascheta_bzhy/) | BJU calculator | interactive | calculator page | Simple answer | Avoid duplicate URL; strengthen `/nutrition` |
| Google | [WillFood](https://willfood.pro/kalkulyator-kaloriy) | calorie/BJU calculator | calculator | conversion-oriented nutrition page | Direct calorie target | Do not make individualized medical promise |
| Google | Rospotrebnadzor nutrition project | calculators catalog | public-health framing | official/trust context | Authority/trust signal | YFC needs authoritative review before competing |

### G — pulse zones

| Engine | Competitor | Observed title/H1 | Type / interaction | CTA, app, schema | Strength | YFC utility gap |
| --- | --- | --- | --- | --- | --- | --- |
| Google | [Lifehacker](https://lifehacker.ru/special/heart-rate-calculator-for-runners/) | «Интерактивный калькулятор ЧСС» | interactive runner tool | simple input/result | Accessible explanation and calculator | Safe claims and source boundary; no fat-burning promise |
| Google | [GET.run](https://get.run/info/calc/hr-zones/) | heart-rate zones technical report | interactive/report | form and profile CTA | Technical detail and running context | Explicit limitations, not medical advice |
| Google | [GeneticLab](https://geneticlab.ru/calc/heartrate/) | HR zone calculator | interactive | detailed form/CTA | Multiple methods/zones | Need reviewer/source contract before launch |
| Google | [PaceRun](https://pacerun.ru/pulse) | pulse-zone calculator | interactive | running calculator ecosystem | Narrow job and related tools | Safe YFC cardio context |
| Google | [Velosophy](https://velosophy.ru/calcs/bpm-zones/) | pulse zone calculator | interactive | cycling context | Sport-specific use | Do not create sport/country variants without evidence |

### H — workout diary / app

| Engine | Competitor | Observed title/H1 | Type / interaction | CTA, app, schema | Strength | YFC utility gap |
| --- | --- | --- | --- | --- | --- | --- |
| Google | [GymUp](https://gymup.pro/) | workout diary | product/app landing | download/CTA; MobileApplication data observed | Clear logging and progress value | YFC's integrated program/progress/trainer path |
| Google | [Gymate](https://gymate.ru/plan-trenirovok) | «Дневник тренировок, который ведёт вас сам» | app/product landing | FAQ/MobileApplication data; CTA | Program, checklist, timer, graphs, FAQ | Truthful current YFC feature story, no overclaiming automation |
| Google | [Forma App Store](https://apps.apple.com/ru/app/forma-%D0%B4%D0%BD%D0%B5%D0%B2%D0%BD%D0%B8%D0%BA-%D1%82%D1%80%D0%B5%D0%BD%D0%B8%D1%80%D0%BE%D0%B2%D0%BE%D0%BA/id1506898151) | workout diary app listing | app-store page | app install/rating context | Strong transactional app intent | Web/TMA entry and trainer-client bridge |
| Google | [Lifehacker roundup](https://lifehacker.ru/prilozheniya-dlya-trenirovok/) | apps for program/diary | editorial roundup | Article schema/CTA | Captures comparison intent | A focused product page should show exact job, not list apps |
| Google | [Brite list](https://britetodo.com/articles/ru/dnevnik-trenirovok-prilozhenie) | top workout diary apps | roundup | editorial comparison | Broad discovery | YFC needs activation proof rather than generic feature list |
| Google | [RBC Style](https://style.rbc.ru/health/699eb2a99a79472cdc1407aa) | workout apps | editorial roundup | editorial authority | High trust/discovery | Current `/training` can answer with one clear path |

## Utility gaps YFC can own

1. **Result-to-action continuity:** calculators should lead to a program/workout save, not end at a
   number.
2. **Product truth:** current `/for-trainers` should describe programs, progress and invites, not
   generic CRM/booking/payment functionality.
3. **Canonical catalog:** exercise pages can combine technique, domain data, safety and later add
   action without thin variants.
4. **Russian plain-language boundaries:** nutrition and cardio pages need sources, limitations and
   no guaranteed outcome claims.
5. **Measurement:** use future registry names only after a successful product flow exists; do not
   instrument a page as if it were implemented before 241B.
