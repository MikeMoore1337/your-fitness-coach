---
name: allure-reporting
description: >
  Keep Allure test evidence useful, structured and privacy-safe. Use when adding
  reporting, attachments, failure diagnostics or investigating YFC Allure output.
---

# allure-reporting

Allure - evidence layer, а не замена assertions.

## Report quality

- title/step должны отражать user/business behavior;
- attachment добавляй только когда он помогает диагностике;
- сохраняй traceback/request/response/trace/screenshot по существующей YFC policy;
- не дублируй гигантские payload без диагностической ценности;
- redact secrets, tokens, personal/health data;
- distinguish product failure, test failure и infrastructure failure;
- retry history не должен скрывать исходное первое падение.

Используй существующий YFC publication pipeline и artifact paths.
Не создавай второй Allure publishing mechanism.
