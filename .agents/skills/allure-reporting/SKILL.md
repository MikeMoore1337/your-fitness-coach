---
name: allure-reporting
description: >
  Keep Allure test evidence useful, structured and privacy-safe. Use when adding
  reporting, attachments, failure diagnostics or investigating YFC Allure output.
---

# allure-reporting

Allure is an evidence/reporting layer, not a replacement for assertions.

## Report quality

- Titles and steps must describe user/business behavior.
- Attach evidence only when it helps diagnosis.
- Preserve tracebacks, requests/responses, traces and screenshots according to YFC policy.
- Do not duplicate huge payloads without diagnostic value.
- Redact secrets, tokens, personal data and health information.
- Distinguish product, test and infrastructure failures.
- Do not let retry history conceal the first failure.

Reuse the existing YFC publishing pipeline and artifact paths; never create a second Allure publishing mechanism.
