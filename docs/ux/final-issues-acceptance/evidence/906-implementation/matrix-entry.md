# Coverage entry — Issue #906

| Acceptance criterion                                                         | Evidence                                              | State                          |
| ---------------------------------------------------------------------------- | ----------------------------------------------------- | ------------------------------ |
| Вариант B выбран и реализован для `/for-athletes` и `/for-trainers`          | `frontend/src/pages/landing/landing-v10.css`, PR #906 | `IMPLEMENTED_NEEDS_ACCEPTANCE` |
| Hero получает больше вертикального пространства на QHD                       | CSS `clamp(860px, 100svh, 980px)`; QHD manifest       | `IMPLEMENTED_VERIFIED`         |
| Фокус спортсменов около 65% 27%                                              | computed style и QHD screenshots                      | `IMPLEMENTED_VERIFIED`         |
| Фокус тренеров адаптирован отдельно около 68% 27%                            | computed style и QHD screenshots                      | `IMPLEMENTED_VERIFIED`         |
| Лица, руки и оборудование остаются читаемыми                                 | BEFORE/AFTER QHD comparisons                          | `IMPLEMENTED_NEEDS_ACCEPTANCE` |
| Glass header, CTA, переключатель аудитории, граница Hero и переход сохранены | targeted Playwright assertions                        | `IMPLEMENTED_VERIFIED`         |
| 1440×900, 1920×1080, 2560×1440, 3440×1440 без горизонтального overflow       | `landing-906.spec.ts`, manifests                      | `IMPLEMENTED_VERIFIED`         |
| Mobile 320/390/430px сохраняет существующую композицию и доступный CTA       | `landing-906.spec.ts`, mobile AFTER screenshots       | `IMPLEMENTED_VERIFIED`         |
| Dark/Light и 125% QHD проверены                                              | capture manifests and provenance                      | `IMPLEMENTED_VERIFIED`         |
| Финальная визуальная приёмка владельца                                       | Требуется после просмотра AFTER                       | `BLOCKED_OWNER_INPUT`          |

Issue не закрывается до `OWNER_FINAL_VISUAL_APPROVAL` и отдельного разрешения на выпуск.
