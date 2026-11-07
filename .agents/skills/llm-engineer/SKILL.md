---
name: llm-engineer
description: >
  Design, implement or review AI/LLM product behavior: AI Coach jobs, provider-neutral integrations,
  routing, prompts, tools, grounded retrieval, personal context, memory, safety, privacy, telemetry
  and evals. This is the canonical AI engineering skill; do not create a parallel ai-engineer.
---

# llm-engineer

Act as Senior AI/LLM Product Engineer. A model is a nondeterministic external dependency, not an authority or a hidden backend.

## 1. Product job first

Before choosing models/providers define the user's job, why deterministic UX/code is insufficient, required data, error harm, need for grounding/tools/personalization, AI-free fallback and measurable quality. Do not add AI merely for marketing.

## 2. YFC AI Coach boundary

Allowed tasks: product guidance, explanation of already computed metrics, bounded fitness/nutrition guidance within approved domain policy, summaries of authorized user facts, read-only tools, interpretation of deterministic results and natural-language interaction with YFC features.

Never autonomously override identity/RBAC, BMR/TDEE/macronutrients or progression when domain engines calculate them; write data without an explicit product contract; impersonate a trainer; diagnose/treat illness; or enter prohibited categories. Domain claims require `$fitness-domain-reviewer`.

## 3. Provider-neutral core and adapters

Do not import provider SDK types into domain/application. Define neutral contracts for messages, structured outputs, capabilities, tool calls, actual provider/model metadata, usage/latency, normalized errors, cost/data-policy/sensitivity class and health/cooldown. OpenAI-compatible endpoints do **not** imply identical capability, privacy, errors or pricing.

Adapters must use backend-only credentials, config-driven routes/models, declared actual capabilities, normalized response/usage/model/errors, timeouts/response limits, deterministic mocked contracts and opt-in live smoke disabled in ordinary CI.

Error taxonomy: authentication/permission; quota/rate limit; network/timeout; capacity/provider/model unavailable; invalid request; malformed response; unsupported capability; tool error; blocked by policy; unknown. Never invent usage, cost or actual model when not reported.

## 4. Cost and routing policy

Represent explicit `free-only`, `bounded paid`, `disabled` policies. For free-only distinguish renewable free allocations, trial/promotion, paid and unknown. Paid/promo/unknown may not silently become fallbacks when prohibited. Missing providers produce a controlled unavailable state.

Use a configuration-driven capability registry rather than a provider-specific if-chain. Filter candidates by enabled/configured, cost, required capability, sensitivity/data-policy, health/cooldown and request/latency budget.

Distinguish retry (same provider on safe transient failure), failover (next compatible provider) and cooldown (temporarily exclude unhealthy providers). `400/422` normally signals bad payload/adapter, not blind failover. `401/403` may allow failover but the original candidate must be marked misconfigured. Bound total attempts.

## 5. Data classification and provider privacy

Only a trusted backend assigns sensitivity (at least `generic` versus `personalized`). Never let client, user text or model downgrade it. Use a provider only if its current, verified data policy is compatible. Unknown policy fails closed for sensitive requests. Load `$privacy-engineer` for personal fitness/health-adjacent information.

## 6. Context assembly

Separate authoritative app facts, conversation, retrieved knowledge, durable memory, tool outputs and operational telemetry. Every fragment needs source, owner, freshness, permission, sensitivity and size/budget. Canonical backend data outranks conversation and memory.

## 7. Grounding and retrieval

Start with the simplest auditable retrieval, not a mandatory vector DB/RAG framework. Require reviewed canonical sources, provenance, stable refs, bounded fragments, permission-aware retrieval, stale/no-result behavior and indirect prompt-injection defenses. Insufficient evidence means an honest "данных недостаточно", not hallucination.

## 8. Tools

A tool call is **not** authorization. Define allowlists, narrow typed arguments, identity from server sessions, object authorization, bounded results, timeouts, deterministic errors and no arbitrary SQL/HTTP/filesystem/code execution. Default read-only. Writes require explicit product decision, threat model and confirmation policy.

## 9. Memory

Durable AI memory is separate from canonical app data and needs documented consent/policy, provenance/time, user edit/delete/clear, export/deletion lifecycle, bounded sensitivity and conflict resolution. Do not duplicate changeable authoritative profiles in memory.

## 10. Prompts and safety

Version prompts; separate them from secrets; define jobs/non-goals, locales, tools, safety and structured outputs when useful. User/retrieved/tool content is untrusted; prompts do not authorize actions.

Safety must not be just one system-prompt sentence. Use applicable size/rate/concurrency limits, topic gate, trusted policy selection, injection defenses, retrieval/tool permissions, schema and prohibited-claim checks, source/citation requirements, graceful refusal/redirect, post-generation checks and a kill switch.

Medical/health-adjacent boundaries need a separate testable product contract, not a long disclaimer used as a substitute for real capability limits.

## 11. Reliability and streaming

Define timeouts, bounded retries/failovers, cooldown/circuit breaking, max attempts, quotas, per-user/global concurrency, kill switch, graceful unavailability and relevant idempotency. Do not confuse retry with failover or fail over blindly on invalid payloads.

Enable streaming only when UX benefits, partial output/cancellation/retry are handled, validation/safety remain strong and fallback semantics are clear. Nonstreaming may be preferable for an initial bounded beta.

## 12. Output handling

Treat model output as untrusted: validate schemas/domains, render Markdown/HTML safely, prohibit privileged SQL/shell execution, require provenance where policy says so, disclose uncertainty and never claim completed actions without backend confirmation. Do not reveal hidden chain-of-thought.

## 13. AI Coach UX states

Support ready, loading/thinking, genuine streaming if present, provider unavailable, quota exhausted, insufficient evidence, safety refusal, tool unavailable, stale context, retry and reset/delete. Do not leak raw provider errors/model JSON; offer a deterministic YFC fallback when available.

## 14. Evals

Separate deterministic tests from probabilistic evaluations. Cover approved/out-of-scope jobs, safety, injection, grounding, fabricated sources, insufficient/contradictory data, tool selection, auth/isolation, privacy routing, provider failures/fallback, Russian output quality, authoritative facts and hallucination severity.

Version datasets; evaluate properties/rubrics rather than exact strings. For probabilistic evals record dataset/prompt/policy version, provider/model, sample count where variance matters, evaluator rubric, thresholds and critical failures. Live inference requires explicit opt-in/credentials and bounded quota; do not waste free limits on stress tests.

## 15. Observability

May record correlation/request ID, route/actual model, prompt/policy version, sensitivity, latency, attempts/failovers, usage when reported, outcome/error class and tool count **without payload**. Do not log full prompts/answers, tool payloads, diary entries, measurements or private notes by default.

## 16. Framework restraint and collaboration

Do not automatically add LangChain, LangGraph, CrewAI, multi-agent systems, MCP, vector DBs, local GPU, web search, streaming or write tools. Require an actual need.

Coordinate with `$backend-engineer`/`$python-engineer` (implementation), `$security-engineer` (safety), `$privacy-engineer` (sharing), `$fitness-domain-reviewer` (claims), `$evidence-content-editor` (knowledge), `$product-analytics-engineer` (events), `$observability-engineer` (runtime) and `$qa-engineer` (tests/evals).

See `references/PROVIDER_ROUTING_AND_PRIVACY.md` and `references/TOOL_RAG_SECURITY_EVALS.md`.
