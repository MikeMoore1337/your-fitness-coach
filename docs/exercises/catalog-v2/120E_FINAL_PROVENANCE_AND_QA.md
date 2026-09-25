# Task 120E: final provenance и QA exact revision

## Exact revision и owner gates

- Asset version: `120e-v1`.
- Source-set SHA-256: `9116e6ee336a65f385fe61c77f53d7075c96e220e3a4ef84e8ae4edac22e797d`.
- Derivative-set SHA-256: `bd65781a2bcd3ab85765a43968fc0fb180f2638be025eef35ea5a18db7b58005`.
- Gate A: `APPROVE_120E_VISUAL_DIRECTION`, approved 2026-08-31.
- Gate B: `APPROVE_120E_EXACT_ASSET_REVISION`, approved 2026-08-31 для
  указанных version/digests.
- До получения Gate B commit, PR, merge и release не выполнялись; после approval
  применяется canonical task lifecycle.

Machine-readable exact source/derivative hashes, variants и per-phase review
содержатся в `120E_ASSET_REVIEW.json`. Это явно помеченный
  `human_review_exact_revision`; automated semantic approval запрещён. Builder
только сверяет этот lock и не может самостоятельно выставить `pass`.

## Workflow и provenance

- Primary workflow: YFC-controlled OpenAI built-in `image_gen`, text-led
  generation и same-set image edit для pair-lock.
- Provider model version/job/seed: `not_exposed_by_provider_interface`; значения
  не выдумываются.
- Calls: 54 generation/edit calls; 36 accepted source masters. Source masters,
  rejected attempts и provider transcript остаются только в `.artifacts/` и не
  входят в production diff.
- Third-party images, public-figure likeness, узнаваемые реальные лица, чужие
  logos/trademarks и hotlinks не использовались.
- `machine-glute-kickback` source revision 1 отклонена владельцем как непонятное
  упражнение. Exact revision 2 использует читаемую рычажную площадку под всей
  рабочей стопой и truthful variant
  `canonical_unilateral_standing_lever_footplate`; revision 1 исключена из
  accepted set и production assets.

Legal/provenance verdict: `PASS_WITH_LIMITATIONS`. Между provider и пользователем
workflow допускает использование output согласно проверенным 2026-08-31
официальным OpenAI terms; output может быть неуникальным, а human review и права
на inputs остаются ответственностью пользователя. Реальный человек или
идентифицируемая собственность не использовались, поэтому model/property release
отмечены `not_applicable`. Это audit evidence, а не гарантия исключительной
copyright protectability во всех юрисдикциях.

## Coverage и domain/visual QA

Все 18 упражнений имеют две exact phases `eccentric_end` и `concentric_end`, один
фиксированный setup и три local WebP derivatives. Для всех 36 изображений вручную
проверены anatomy, equipment, phase, grip/feet/contact points, pair consistency,
style и mobile readability.

| Exercise | Variant | Domain/visual verdict |
|---|---|---|
| `machine-incline-chest-press` | `canonical_bilateral_selectorized_incline` | `PASS` |
| `independent-lever-chest-press` | `canonical_bilateral_plate_loaded_independent` | `PASS` |
| `lever-high-row` | `canonical_bilateral_plate_loaded_high_row` | `PASS` |
| `lever-low-row` | `canonical_bilateral_plate_loaded_low_row` | `PASS` |
| `independent-lever-lat-pulldown` | `canonical_bilateral_plate_loaded_independent` | `PASS` |
| `machine-pullover` | `canonical_bilateral_selectorized_elbow_pad` | `PASS` |
| `independent-lever-shoulder-press` | `canonical_bilateral_plate_loaded_independent` | `PASS` |
| `machine-decline-chest-press` | `canonical_bilateral_selectorized_decline` | `PASS` |
| `machine-triceps-extension` | `canonical_bilateral_selectorized_elbow_pad` | `PASS` |
| `chest-supported-dumbbell-row` | `canonical_bilateral_incline_bench_dumbbell` | `PASS` |
| `pendulum-squat` | `canonical_bilateral_plate_loaded_pendulum` | `PASS` |
| `plate-loaded-leg-press` | `canonical_bilateral_plate_loaded_sled` | `PASS` |
| `unilateral-leg-press` | `canonical_unilateral_plate_loaded_sled` | `PASS` |
| `machine-hip-thrust` | `canonical_bilateral_plate_loaded_lap_pad` | `PASS` |
| `smith-split-squat` | `canonical_unilateral_smith_floor_rear_foot` | `PASS` |
| `machine-glute-kickback` | `canonical_unilateral_standing_lever_footplate` | `PASS`, owner finding fixed in source revision 2 |
| `v-squat-machine` | `canonical_bilateral_plate_loaded_v_squat` | `PASS` |
| `reverse-hyperextension` | `canonical_bilateral_plate_loaded_reverse_hyper` | `PASS` |

Structured internal novice-comprehension review подтверждает, что в pair view
видны setup, две позиции, движущаяся часть, руки/ноги и основные опоры. Поскольку
assets создавались и проверялись в одной agent session, это не объявляется
независимым human study. Финальный human/owner novice verdict является частью
обязательного Gate B.

## Performance

| Source | Count | Min/phase | Max/phase | Total |
|---|---:|---:|---:|---:|
| `480w` | 36 | 7 608 B | 16 496 B | 418 844 B |
| `768w` | 36 | 16 342 B | 34 718 B | 885 742 B |
| `1280w` | 36 | 34 912 B | 70 584 B | 1 928 364 B |

- Mobile pair: 15 300–31 596 B при budget 320 KB; каждая phase существенно ниже
  160 KB.
- `srcset/sizes` выбирает 480/768/1280; 1280 source появляется в DOM lightbox
  только после открытия. `loading="lazy"`, `decoding="async"`, dimensions и
  aspect ratio сохранены.
- Local same-origin versioned URLs: `human-v1/<slug>/<phase>-<width>w.webp`.
- Repo-wide `frontend perf:check` фиксирует pre-existing entry CSS overshoot:
  raw `341496 > 335000`, gzip `53164 > 52500`. Task 120E меняет только одно CSS
  grid value и не добавляет CSS; budget не ослаблен. Asset-specific budget и
  manifest validator проходят.

## Automated и runtime evidence

- `python scripts/build_exercise_human_visual_assets.py --source-dir <review-artifacts>`:
  108 exact derivatives, оба set digests совпали.
- `python scripts/validate_exercise_catalog.py`: active schema-3 manifest,
  334 Gym visual assets / 206 canonical exercises, 167 approved animated and
  39 blocked entries — pass.
- `pytest backend/tests/test_exercise_domain.py`: `10 passed`.
- Frontend component tests `ExerciseGuideMedia` + `ExerciseGuideDialog`: `4 passed`.
- Frontend `typecheck`, ESLint и production build: pass.
- Playwright upper/lower targeted matrix: `6 passed`; отдельный recheck трёх
  corrected evidence scenarios: `3 passed`.
- Mobile Web: `360x800`, `390x844`, `430x932`; light/dark на 390.
- Mocked TMA: `360x800`, `390x844`, `430x932` light; `390x844` dark.
- Desktop browser emulation: `1280x900` light/dark.
- Lightbox, slow-loading и image-error fallback проверены. Text technique остаётся
  доступной; schematic fallback отсутствует.
- Real Telegram, physical iOS/Android device и real-user study не выполнялись и
  не заявляются.

## Review/QA verdict

- Full sequential independent-review pass (тот же agent, не отдельный reviewer)
  нашёл `120E-R1 HIGH`: derivative builder мог автоматически записать semantic
  `pass`. Исправлено: builder теперь только валидирует versioned human-review lock;
  negative regression test и targeted recheck проходят.
- QA pass: `PASS`; unresolved `BLOCKER/HIGH/MEDIUM/LOW` текущего diff нет.
- `codex-backlog/bugs/FINDINGS.md`: новых `MEDIUM/LOW` нет. Repo-wide CSS budget
  отмечен как pre-existing `OUT_OF_SCOPE`, без ослабления budget и без нового bug
  task.
