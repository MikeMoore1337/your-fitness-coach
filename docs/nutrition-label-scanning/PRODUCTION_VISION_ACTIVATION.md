# Nutrition Label Vision production activation

## Purpose

This runbook activates the optional external fallback only after the existing local RapidOCR path
has classified a scan as `vision_candidate`. It does not replace local OCR.

## Manual Groq organization gates

Before changing YFC production configuration, an organization admin must verify both items in the
exact Groq organization used by `GROQ_API_KEY`:

1. **Settings -> Limits**: enable model `qwen/qwen3.8-27b`.
2. **Settings -> Data Controls**: enable **Zero Data Retention** for inference.

YFC cannot read the ZDR switch through the public API. Do not set
`NUTRITION_LABEL_VISION_DATA_POLICY=zdr_verified` from assumption or from successful
authentication alone.

## Pre-activation provider smoke

Use only synthetic/owned fixtures until ZDR is verified. A successful smoke must prove:

- request uses the dedicated Nutrition Vision proxy route;
- HTTP 200 from `qwen/qwen3.8-27b`;
- strict schema parses successfully;
- deterministic canonical validation succeeds;
- no prompt/image/model answer is written to normal logs.

A 401/403/429/5xx is a NO-GO and must not be worked around by weakening validation.

## Activation command

The activation helper is intentionally not called by automatic deploy:

```bash
python3 scripts/configure_production_nutrition_label_vision.py /srv/yfc/fit-mini-app/.env \
  --proxy-url socks5://host.docker.internal:1081 \
  --confirm-zdr \
  --allow-preview
```

The command requires a non-placeholder existing `GROQ_API_KEY`, preserves unrelated env values,
and sets the independent Vision provider/model/proxy/data-policy/kill-switch contract.

## Post-activation acceptance

After the next backend restart/deploy:

- `NUTRITION_LABEL_SCAN_ENABLED=true`;
- `NUTRITION_LABEL_VISION_ENABLED=true`;
- `NUTRITION_LABEL_VISION_KILL_SWITCH=false`;
- provider is `groq`;
- data policy is `zdr_verified`;
- Preview opt-in is true;
- one owner-approved real label that becomes `vision_candidate` is recovered into an editable
  draft;
- draft remains `requires_user_review=true`;
- no automatic diary/catalog mutation occurs;
- `/health/live` and `/health/ready` remain 200.

## Emergency disable

Set `NUTRITION_LABEL_VISION_KILL_SWITCH=true` in the persistent production env and restart the
backend through the normal release procedure. Local RapidOCR/manual review remains available.
