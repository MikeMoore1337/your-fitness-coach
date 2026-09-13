# Provider / OCR privacy-cost matrix

**Версия:** `nutrition-label-provider-matrix-v1`
**Дата проверки official sources:** 2026-09-12
**Статус:** research only; ни один provider не approved для YFC.

## Как читать матрицу

`free` в pricing page не означает `recurring_free + approved_for_user_photos`. Для YFC отдельны
три оси: техническая capability, цена/quota и допустимость data-flow. Любое `unknown` блокирует
production GO до owner/provider/legal decision.

| Кандидат | Image / schema evidence | Cost / quota evidence | Data / region evidence | Current disposition |
|---|---|---|---|---|
| **Current YFC Groq route** `openai/gpt-oss-120b` | Current adapter sends text-only chat completion and strict text schema. No image input in YFC contract. | Groq model page lists $0.15 input / $0.60 output per 1M tokens and developer limits; current YFC policy is `free_only`, account billing not re-verified here. | Existing AI decision keeps generic-only, no personal image route. | **Not Vision-capable in current route.** |
| **Groq Qwen Vision** `qwen/qwen3.6-27b` / `qwen/qwen3.8-27b` | Official Vision page documents image input, OCR-oriented use, JSON mode, 20 MB URL limit, and 5/3 images per request. Structured Outputs page documents strict mode only for supported models; the combination of this Vision model and YFC schema is not live-tested. | Models page lists preview status, Qwen price $0.60/$3.00 and $0.80/$4.00 input/output per 1M tokens. Rate page lists 30 RPM, 1K RPD, 8K TPM, 200K TPD on developer plan. No recurring-free production promise established. | Groq says inference data is not retained by default but reliability/abuse logs can be retained up to 30 days; ZDR is configurable. Customer data location is US GCP buckets. | **Research candidate only; privacy/region/cost/legal gate.** |
| **OpenAI GPT-4o pinned snapshot** | Official model page documents text+image input, text output including Structured Outputs, and snapshots. Image guide documents PNG/JPEG/WEBP/non-animated GIF, payload and detail limits. | Official model page lists $2.50 input / $10 output per 1M text tokens; image-token cost and account limits must be calculated for the selected snapshot. Free tier is not evidenced. | API data guide says API data is not used for training by default, but default abuse monitoring can retain customer content up to 30 days; ZDR/MAM require approval and image/file inputs have rare exceptions. Residency has its own region/endpoint limitations. | **Paid candidate only; owner/legal and cost approval required.** |
| **Google Gemini API** | Official image guide documents PNG/JPEG/WEBP/HEIC/HEIF. Structured output is JSON Schema subset; Google explicitly recommends application validation for semantically incorrect but schema-valid outputs. | Pricing page exposes free and paid tiers; current Gemini 3 Flash Preview example lists free text/image input and paid $0.50 input / $3 output per 1M tokens. Free tier is not a safe YFC data policy. | Current terms say unpaid content and responses can be used to improve/develop products and may be read by human reviewers; paid service does not use prompts/responses to improve products but logs them for limited safety/legal purposes and may process transiently in any country. Public available-region list inspected today contains Kazakhstan and Moldova but no Russia entry; account-specific availability is still unknown. | **Rejected as free/private default; paid/legal candidate only after explicit review.** |
| **PaddleOCR local hybrid** | Official documentation lists Russian and English recognition models and orientation/document pipeline options. It returns OCR/layout data that YFC would still need to parse and validate. | No provider token charge; CPU/GPU, package size, cold start, memory and device/browser feasibility are unmeasured. | Image can remain on the YFC-controlled runtime/device; no third-party upload by default. OSS model/code license and deployment asset review are required before bundling. | **Best privacy direction for a narrow local spike; not quality-approved.** |
| **Tesseract local hybrid** | Official docs expose language data plus hOCR/TSV outputs; table reconstruction and numeric normalization remain YFC work. | No provider token charge; runtime and language-data footprint unmeasured. | Local processing avoids provider data transfer; package/license and deployment footprint still require review. | **Fallback/reference OCR candidate; not quality-approved.** |

## Source links

- Groq: [Vision](https://console.groq.com/docs/vision), [Structured Outputs](https://console.groq.com/docs/structured-outputs), [Models](https://console.groq.com/docs/models), [Rate Limits](https://console.groq.com/docs/rate-limits), [Your Data](https://console.groq.com/docs/your-data).
- OpenAI: [Images and vision](https://developers.openai.com/api/docs/guides/images-vision), [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [GPT-4o model](https://developers.openai.com/api/docs/models/gpt-4o), [Data controls](https://developers.openai.com/api/docs/guides/your-data).
- Google: [Image understanding](https://ai.google.dev/gemini-api/docs/image-understanding), [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), [Pricing](https://ai.google.dev/gemini-api/docs/pricing), [Additional Terms](https://ai.google.dev/gemini-api/terms), [Available regions](https://ai.google.dev/gemini-api/docs/available-regions).
- Local OCR: [PaddleOCR multilingual models](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md), [PaddleOCR pipeline](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html), [Tesseract FAQ](https://tesseract-ocr.github.io/tessdoc/FAQ.html).

## Policy decisions for YFC

- Access check for this bounded run: no `GROQ_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` or
  equivalent Vision credential is available under the current task environment. Current YFC AI
  Coach policy is disabled/generic-only/free-only; an existing credential scoped to the separate
  news flow is not eligible for reuse. No provider request was attempted.
- Local runtime check: Pillow is available for legal synthetic fixture generation, but PaddleOCR,
  Tesseract, `pytesseract` and checked alternative OCR runtimes are absent. Therefore local image
  preflight passed, while local extraction quality remains `NOT_RUN` with blocker
  `LOCAL_OCR_RUNTIME_UNAVAILABLE`.
- Cloudflare Workers AI остаётся вне этой матрицы: текущий contract резервирует его для Telegram
  news image generation; это не Vision fallback.
- Не считать OpenAI-compatible endpoint доказательством image capability: capability проверяется
  конкретной моделью, pinned snapshot и фактическим request schema.
- Не считать free tier достаточным: `recurring_free`, billing state, rate limits, spend limits,
  region, retention/training/analytics and subprocessors должны быть зафиксированы на выбранном
  аккаунте и дате.
- До owner/legal approval не передавать ни real-user photos, ни package photos с user-identifying
  context. Test fixture upload — отдельный explicit gate.

## Exact disposition after the bounded run

No cloud candidate is approved. Owner decision permits implementation of the local-only
OCR/preprocessing route with deterministic parser/validator, zero external token cost and no
provider retention/training/analytics/subprocessors. Its exact TTL, package license and
device-resource budget remain gates before owner-only production validation/public enable.

Any cloud route remains blocked by the combination of missing approved credential, absent
account-specific region/retention/quota proof and missing corpus quality results. It must not be
implemented as an automatic paid fallback.
