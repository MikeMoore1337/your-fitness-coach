# Nutrition label Vision provider matrix

**Версия:** `nutrition-label-provider-matrix-v2`
**Дата проверки официальных источников:** 2026-09-25
**Статус:** research only; ни один provider не approved для YFC.

## Текущие кандидаты

| Кандидат | Image / schema | Цена и лимиты | Данные и регион | Решение для YFC |
|---|---|---|---|---|
| **Текущий YFC Groq route** | Существующий YFC adapter обслуживает generic text-only контракт. Он не принимает фотографии; перепрофилировать его под package images нельзя. | Его тариф и лимиты не являются оценкой Vision-запроса. | Текущая generic/free-only политика AI Coach не даёт разрешения на обработку личных фото. | **Не Vision-кандидат в текущей архитектуре.** |
| **Groq Qwen3.8 27B** `qwen/qwen3.8-27b` | Vision docs описывают image input и OCR; документация Structured Outputs содержит strict JSON Schema режим для поддерживаемых моделей. Совместимость этой preview-модели с YFC schema и семантикой не проверялась. Документация указывает 20 MB для URL-image и фиксированный image input 2048 tokens. | Страница модели указывает `$0.80 / 1M input tokens` и `$4.00 / 1M output tokens`; image input — около `$0.00164` на одну картинку до text/output. Страница помечает модель `Preview` и прямо ограничивает её evaluation use. Developer-plan limits: `30 RPM`, `1K RPD`, `8K TPM`, `200K TPD`; действующие лимиты организации не проверены. | Inference content по умолчанию не сохраняется, но abuse/reliability logs могут содержать данные до 30 дней; ZDR требует account setting. Документация указывает хранение customer data в US GCP buckets. Субпроцессоры перечислены Groq отдельно. | **Не годится для production, пока модель Preview.** Допустим только отдельный синтетический evaluation после owner/provider/privacy approval. |
| **OpenAI GPT-4.1** | Image input, text output и Structured Outputs поддерживаются. Изображения поддерживают PNG/JPEG/WEBP/non-animated GIF; image token cost зависит от размера/detail. Семантическая точность для YFC не доказана. | Текущая страница модели указывает `$2 / 1M input tokens`, `$8 / 1M output tokens`; API Free tier отсутствует, account limits зависят от tier. Image tokens оплачиваются по правилам vision guide. | API data не используется для обучения без opt-in; стандартный abuse monitoring может хранить customer content до 30 дней. ZDR/MAM требуют одобрения и имеют редкие исключения для image/file input. Текущий supported-countries list не включает Россию. | **Не использовать из неподдерживаемого региона.** Даже при допустимом регионе нужны account-specific privacy, residency, cost/quota и legal approvals. |
| **Gemini API 3.1 Flash-Lite** | Stable-модель поддерживает image input и structured output; приложение всё равно должно валидировать результат. Поддерживаемые форматы включают PNG/JPEG/WEBP/HEIC/HEIF; inline body ограничен 20 MB, а разрешение влияет на токены/задержку. | Официальная цена: `$0.25 / 1M input tokens`, `$1.50 / 1M output tokens`. Free tier существует; actual project quota зависит от аккаунта и показана в AI Studio. Paid tier требует настроенного billing account. | На free tier input/output может использоваться для улучшения продуктов и просматриваться людьми: личные фото туда отправлять нельзя. Paid tier не использует content для улучшения моделей, но abuse monitoring может хранить его до 55 дней и допускает human review flagged inputs. Документация Developer API перечисляет допустимые регионы, но не Россию. Для data-processing условий нужны актуальные Google Cloud DPA и subprocessor list. | **Free tier запрещён для личных фото; Developer API недоступен из России по опубликованному списку регионов.** Не production route для текущего YFC. |
| **Cloudflare Workers AI** | — | — | — | **Исключён:** внутренний contract резервирует Workers AI для Telegram/news-image flow. |

## Текущая политика и проверенные факты

- Проверены только официальные публичные документы на указанную дату. Ни один аккаунт, billing state,
  organization quota, endpoint, secret или provider request не проверялся.
- В существующем YFC Groq adapter Vision-обработка не реализована. Наличие credentials для другого
  продукта или route не означает право отправлять туда этикетки.
- Ни одна модель не выбрана и не подключена. Vision feature имеет sample default
  `NUTRITION_LABEL_VISION_ENABLED=false`; code contract сам по себе не является разрешением на
  активацию.
- Не отправлять real-user/package photos до отдельного решения владельца, актуальной проверки
  privacy/legal, региона и account-specific data terms. Provider schema validity не подтверждает
  фактическую точность распознавания.
- Local OCR и внешний Vision имеют отдельные бюджеты/метрики. Никакие synthetic или local OCR
  показатели не являются provider quality result.

## Официальные источники

- Groq: [Vision](https://console.groq.com/docs/vision), [Structured Outputs](https://console.groq.com/docs/structured-outputs), [Models and pricing](https://console.groq.com/docs/models), [Rate limits](https://console.groq.com/docs/rate-limits), [Your data](https://console.groq.com/docs/your-data), [DPA](https://console.groq.com/docs/legal/customer-data-processing-addendum), [Subprocessors](https://trust.groq.com/subprocessors).
- OpenAI: [GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1), [Images and vision](https://developers.openai.com/api/docs/guides/images-vision), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Data controls](https://developers.openai.com/api/docs/guides/your-data), [Supported countries](https://developers.openai.com/api/docs/supported-countries), [Subprocessor list](https://openai.com/policies/sub-processor-list/).
- Google: [Gemini 3 developer guide and pricing](https://ai.google.dev/gemini-api/docs/gemini-3), [Gemini 3.1 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite), [Image understanding](https://ai.google.dev/gemini-api/docs/image-understanding), [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [Data use](https://ai.google.dev/gemini-api/docs/your-data), [Terms](https://ai.google.dev/gemini-api/terms), [Available regions](https://ai.google.dev/gemini-api/docs/available-regions), [Google Cloud DPA](https://cloud.google.com/terms/data-processing-addendum), [Subprocessors](https://cloud.google.com/terms/subprocessors).
