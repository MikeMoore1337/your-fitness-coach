# Mobile Web / TMA camera notes

**Версия:** `nutrition-label-camera-notes-v1`
**Дата:** 2026-09-12
**Статус:** feasibility notes only; `128C` не запущена.

## Current state

Текущий mobile camera path — локальный barcode scanner: `getUserMedia` + native
`BarcodeDetector`/lazy local decoder. Video frames остаются в браузере и не отправляются
provider. Manual GTIN entry и controlled permission/error/retry fallback уже являются частью
food-domain contract. Label-photo capture route отсутствует.

Это значит:

- barcode camera evidence не является label Vision evidence;
- `90B` не является physical-camera evidence;
- в этой task не заявляются iOS Safari, Android, Telegram WebView или физическое устройство;
- нельзя отправлять весь camera stream в cloud provider.

## Candidate `128C` capture contract

После owner approval `128C` может исследовать только:

1. явное действие `Сфотографировать этикетку` или выбор still image;
2. preview/crop/retake, где nutrition table читаема целиком;
3. client-side file signature/MIME/dimension/pixel/decode checks до upload;
4. EXIF stripping and orientation normalization before any external call;
5. один bounded image, no continuous video upload, no background camera;
6. progress/timeout/unavailable/manual fallback without losing manually entered values;
7. permission denial, camera absent, WebView restrictions and keyboard/safe-area geometry;
8. explicit confirmation of every extracted value before diary/catalog write.

Предлагаемые starting limits (не runtime facts): max 8 MiB, max 20 megapixels, finite dimensions,
decode timeout and server/provider request timeout. Exact values выбираются в `128B/128C` после
device/resource evidence, а не зашиваются этой discovery task.

## Privacy boundary

- raw upload ephemeral by default; no image in normal logs, analytics, traces or error reports;
- provider payload includes only the image and minimal extraction instruction, never Telegram
  initData, user ID, diary/history, goals or unrelated free text;
- raw image and raw OCR have short TTL and are deleted on cancel/expiry; only user-confirmed
  structured facts persist;
- account deletion/consent revoke must cover pending draft, temporary copies and contributions;
- provider region/retention/training/subprocessors and transfer terms require explicit owner/legal
  review before user photo upload.

## Evidence still required

Physical-device/TMA checks, orientation/EXIF behavior, camera permission UX, upload size/latency,
and crop quality remain unmeasured. They are not blockers for the current read-only packet because
the packet explicitly recommends `DEFER`, but they block any claim that `128C` is production-ready.
